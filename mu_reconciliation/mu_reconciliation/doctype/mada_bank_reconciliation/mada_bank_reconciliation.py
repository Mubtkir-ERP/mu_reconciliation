# -*- coding: utf-8 -*-
# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate
from mu_reconciliation.utils.statement_parser import parse_bank_file


class MadaBankReconciliation(Document):
    def before_insert(self):
        if not self.naming_series or self.naming_series.startswith("MADA-RECON"):
            self.naming_series = "BR-.YY.-.#####"

    def validate(self):
        self.calculate_summary()

    def calculate_summary(self):
        total_dep = 0.0
        total_comm = 0.0
        total_matched = 0.0
        total_unmatched_bank = 0.0

        for row in self.get("statement_rows") or []:
            dep = flt(row.credit_amount)
            comm = flt(row.commission_amount)
            total_dep += dep
            total_comm += comm

            status = row.matched_status or ""
            if "Matched" in status or "مطابق" in status:
                total_matched += dep
            else:
                total_unmatched_bank += dep

        self.total_bank_deposits = total_dep
        self.total_bank_commissions = total_comm
        self.total_matched_amount = total_matched
        self.total_unmatched_in_system = total_unmatched_bank

    @frappe.whitelist()
    def parse_statement(self):
        """Parse and extract MADA transactions from uploaded bank statement file."""
        if not self.bank_statement_file:
            frappe.throw(_("Please attach the bank statement file first (Excel, PDF, or CSV)."))

        file_doc = frappe.get_doc("File", {"file_url": self.bank_statement_file})
        full_path = file_doc.get_full_path()

        records = parse_bank_file(full_path)
        if not records:
            frappe.throw(_("No MADA transactions found in the attached file. Please verify the file format."))

        from_d = getdate(self.from_date) if self.from_date else None
        to_d = getdate(self.to_date) if self.to_date else None

        self.set("statement_rows", [])
        added = 0
        total_in_file = len(records)
        dates_in_file = []

        for rec in records:
            if rec.get("credit", 0) > 0 or rec.get("commission", 0) > 0:
                rec_date_str = rec.get("date")
                rec_date = getdate(rec_date_str) if rec_date_str else None
                if rec_date:
                    dates_in_file.append(rec_date)

                # Filter by date range if transaction date was detected
                if from_d and rec_date and rec_date < from_d:
                    continue
                if to_d and rec_date and rec_date > to_d:
                    continue

                self.append("statement_rows", {
                    "txn_date": rec_date_str or self.from_date or nowdate(),
                    "terminal_id": rec.get("terminal_id") or "",
                    "batch_no": rec.get("batch_no") or "",
                    "credit_amount": rec.get("credit", 0.0),
                    "commission_amount": rec.get("commission", 0.0),
                    "description": rec.get("description") or "",
                    "matched_status": "Pending / Unreconciled 🔴"
                })
                added += 1

        if added == 0 and total_in_file > 0:
            for rec in records:
                if rec.get("credit", 0) > 0 or rec.get("commission", 0) > 0:
                    rec_date_str = rec.get("date")
                    self.append("statement_rows", {
                        "txn_date": rec_date_str or self.from_date or nowdate(),
                        "terminal_id": rec.get("terminal_id") or "",
                        "batch_no": rec.get("batch_no") or "",
                        "credit_amount": rec.get("credit", 0.0),
                        "commission_amount": rec.get("commission", 0.0),
                        "description": rec.get("description") or "",
                        "matched_status": "Pending / Unreconciled 🔴"
                    })
                    added += 1

            min_d = str(min(dates_in_file)) if dates_in_file else _("Unknown")
            max_d = str(max(dates_in_file)) if dates_in_file else _("Unknown")
            frappe.msgprint(
                _("Found {0} transactions in statement, but none match the period {1} to {2}. File transactions date range: {3} to {4}").format(
                    total_in_file, self.from_date, self.to_date, min_d, max_d
                ),
                title=_("Date Range Warning"),
                indicator="orange"
            )

        self.status = "Parsed"
        self.calculate_summary()
        self.save()
        frappe.db.commit()
        return {"status": "success", "rows_added": added, "total_in_file": total_in_file}

    @frappe.whitelist()
    def on_cancel(self):
        self.reset_reconciled_rows()

    def on_trash(self):
        self.reset_reconciled_rows()

    def reset_reconciled_rows(self):
        frappe.db.sql(
            """
            UPDATE `tabMada Settlement Entry Row`
            SET reconciliation_status = 'Pending / Unreconciled 🔴',
                bank_reconciliation = NULL
            WHERE bank_reconciliation = %s
            """,
            (self.name,)
        )

    @frappe.whitelist()
    def run_reconciliation(self):
        """Intelligently reconcile bank statement deposits with system settlement entries."""
        if not self.statement_rows:
            self.parse_statement()

        # Reset any previous matches for this document
        self.reset_reconciled_rows()
        for r in self.statement_rows:
            r.matched_status = "Pending / Unreconciled 🔴"
            r.matched_entry = None

        from_d = getdate(self.from_date) if self.from_date else getdate("2000-01-01")
        to_d = getdate(self.to_date) if self.to_date else getdate("2099-12-31")

        # 1. Fetch system settlements strictly within selected date range and for the selected bank account.
        # Exclude settlements already reconciled in other documents.
        bank_account_cond = ""
        params = {
            "from_date": from_d,
            "to_date": to_d,
            "bank_account": self.bank_account or "",
            "current_doc": self.name
        }

        if self.bank_account:
            bank_account_cond = """
                AND (
                    t.bank_account = %(bank_account)s 
                    OR ba.account = %(bank_account)s
                )
            """

        system_settlements = frappe.db.sql(
            f"""
            SELECT 
                r.name as row_name,
                r.parent as entry_name,
                r.terminal,
                COALESCE(NULLIF(r.terminal_id, ''), t.terminal_id, r.terminal) as terminal_id,
                r.batch_no,
                COALESCE(r.settlement_date, p.entry_date) as settlement_date,
                r.amount,
                r.reconciliation_status,
                r.bank_reconciliation
            FROM `tabMada Settlement Entry Row` r
            INNER JOIN `tabMada Settlement Entry` p ON p.name = r.parent
            LEFT JOIN `tabMada Terminal` t ON t.name = r.terminal
            LEFT JOIN `tabBank Account` ba ON ba.name = t.bank_account
            WHERE p.docstatus < 2
              AND COALESCE(r.settlement_date, p.entry_date) BETWEEN %(from_date)s AND %(to_date)s
              {bank_account_cond}
              AND (
                  r.bank_reconciliation = %(current_doc)s
                  OR (
                      COALESCE(r.reconciliation_status, '') NOT IN ('Reconciled with Bank 🟢', 'مطابق بالبنك 🟢')
                      AND (r.bank_reconciliation IS NULL OR r.bank_reconciliation = '')
                  )
              )
            ORDER BY COALESCE(r.settlement_date, p.entry_date) ASC
            """,
            params,
            as_dict=True
        )

        total_system = sum(flt(s.amount) for s in system_settlements)
        self.total_system_settlements = total_system

        matched_system_rows = set()
        matched_count = 0

        def tid_matches(s_tid, b_tid, s_term):
            if not b_tid:
                return False
            b_s = str(b_tid).strip()
            s_s = str(s_tid or "").strip()
            term_s = str(s_term or "").strip()
            if s_s:
                if s_s == b_s or s_s.startswith(b_s) or b_s.startswith(s_s):
                    return True
                if b_s in s_s or s_s in b_s:
                    return True
            if term_s and term_s == b_s:
                return True
            return False

        # 2. Multi-tier Intelligent Matching
        for bank_row in self.statement_rows:
            b_tid = str(bank_row.terminal_id or "").strip()
            b_date = getdate(bank_row.txn_date) if bank_row.txn_date else None
            b_amt = flt(bank_row.credit_amount)
            b_comm = flt(bank_row.commission_amount)
            b_net = b_amt - b_comm if b_comm > 0 else b_amt
            b_batch = str(bank_row.batch_no or "").strip()

            if b_amt <= 0:
                continue

            match = None

            # Priority 1: Batch No match + TID match (when batch numbers are recorded)
            if b_batch:
                for s in system_settlements:
                    if s.row_name in matched_system_rows:
                        continue
                    s_batch = str(s.batch_no or "").strip()
                    s_amt = flt(s.amount)
                    amt_ok = (abs(s_amt - b_amt) < 0.05) or (abs(s_amt - b_net) < 0.05)
                    tid_ok = tid_matches(s.terminal_id, b_tid, s.terminal)
                    if s_batch and s_batch == b_batch and amt_ok:
                        if not b_tid or tid_ok:
                            match = s
                            break

            # Priority 2: TID match + Exact Amount + Exact Date
            if not match and b_tid:
                for s in system_settlements:
                    if s.row_name in matched_system_rows:
                        continue
                    s_amt = flt(s.amount)
                    s_date = getdate(s.settlement_date) if s.settlement_date else None
                    amt_ok = (abs(s_amt - b_amt) < 0.05) or (abs(s_amt - b_net) < 0.05)
                    if amt_ok and tid_matches(s.terminal_id, b_tid, s.terminal) and b_date and s_date and b_date == s_date:
                        match = s
                        break

            # Priority 3: TID match + Exact Amount + Date Proximity (<= 2 days)
            if not match and b_tid:
                for s in system_settlements:
                    if s.row_name in matched_system_rows:
                        continue
                    s_amt = flt(s.amount)
                    s_date = getdate(s.settlement_date) if s.settlement_date else None
                    days_diff = abs((b_date - s_date).days) if (b_date and s_date) else 999
                    amt_ok = (abs(s_amt - b_amt) < 0.05) or (abs(s_amt - b_net) < 0.05)
                    if amt_ok and tid_matches(s.terminal_id, b_tid, s.terminal) and days_diff <= 2:
                        match = s
                        break

            # Priority 4: TID match + Exact Amount within statement period
            if not match and b_tid:
                for s in system_settlements:
                    if s.row_name in matched_system_rows:
                        continue
                    s_amt = flt(s.amount)
                    amt_ok = (abs(s_amt - b_amt) < 0.05) or (abs(s_amt - b_net) < 0.05)
                    if amt_ok and tid_matches(s.terminal_id, b_tid, s.terminal):
                        match = s
                        break

            # Priority 5 (Only when TID is not present in bank row): Exact Amount + Exact Date
            if not match and not b_tid:
                for s in system_settlements:
                    if s.row_name in matched_system_rows:
                        continue
                    s_amt = flt(s.amount)
                    s_date = getdate(s.settlement_date) if s.settlement_date else None
                    amt_ok = (abs(s_amt - b_amt) < 0.05) or (abs(s_amt - b_net) < 0.05)
                    if amt_ok and b_date and s_date and b_date == s_date:
                        match = s
                        break

            if match:
                bank_row.matched_status = "Matched 🟢"
                bank_row.matched_entry = match.entry_name
                matched_system_rows.add(match.row_name)
                matched_count += 1
                frappe.db.set_value("Mada Settlement Entry Row", match.row_name, {
                    "reconciliation_status": "Reconciled with Bank 🟢",
                    "bank_reconciliation": self.name
                })
            else:
                bank_row.matched_status = "Unmatched Deposit 🟡"

        # 3. Calculate missing in bank (recorded in system but not deposited in bank statement)
        missing_total = 0.0
        missing_list = []
        for s in system_settlements:
            if s.row_name not in matched_system_rows:
                missing_total += flt(s.amount)
                missing_list.append(s)
                frappe.db.set_value("Mada Settlement Entry Row", s.row_name, {
                    "reconciliation_status": "Pending / Unreconciled 🔴",
                    "bank_reconciliation": None
                })

        self.total_missing_in_bank = missing_total
        self.status = "Reconciled"
        self.calculate_summary()
        self.save()
        frappe.db.commit()

        return {
            "status": "success",
            "matched_count": matched_count,
            "missing_in_bank_count": len(missing_list),
            "missing_total": missing_total
        }

    @frappe.whitelist()
    def create_commission_journal_entry(self):
        """Create and submit a Journal Entry for bank commissions."""
        if self.commission_journal_entry and frappe.db.exists("Journal Entry", self.commission_journal_entry):
            frappe.throw(_("Commission Journal Entry already exists: {0}").format(self.commission_journal_entry))

        total_comm = flt(self.total_bank_commissions)
        if total_comm <= 0:
            frappe.throw(_("No commission amounts to create Journal Entry."))

        settings = frappe.get_single("Mada Reconciliation Settings")
        expense_acc = settings.commission_expense_account
        bank_acc = self.bank_account or settings.default_bank_account
        vat_acc = settings.commission_vat_account
        vat_rate = flt(settings.vat_rate_on_commission or 15.0)

        if not expense_acc:
            frappe.throw(_("Please specify MADA Commission Expense Account in Mada Reconciliation Settings."))
        if not bank_acc:
            frappe.throw(_("Please select Bank Account first."))

        company = frappe.db.get_value("Account", bank_acc, "company")
        vat_amount = 0.0
        net_expense = total_comm

        if vat_acc and vat_rate > 0:
            net_expense = flt(total_comm / (1.0 + (vat_rate / 100.0)), 2)
            vat_amount = flt(total_comm - net_expense, 2)

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Bank Entry"
        je.company = company
        je.posting_date = self.to_date or nowdate()
        je.cheque_no = self.name
        je.cheque_date = self.to_date or nowdate()
        je.user_remark = f"قيد إثبات عمولات شبكة مدى للفترة من {self.from_date} إلى {self.to_date} - مرجع: {self.name}"

        je.append("accounts", {
            "account": expense_acc,
            "debit_in_account_currency": net_expense,
            "credit_in_account_currency": 0,
            "cost_center": frappe.db.get_value("Company", company, "cost_center")
        })

        if vat_acc and vat_amount > 0:
            je.append("accounts", {
                "account": vat_acc,
                "debit_in_account_currency": vat_amount,
                "credit_in_account_currency": 0,
                "cost_center": frappe.db.get_value("Company", company, "cost_center")
            })

        je.append("accounts", {
            "account": bank_acc,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": total_comm,
            "cost_center": frappe.db.get_value("Company", company, "cost_center")
        })

        je.insert(ignore_permissions=True)
        je.submit()

        self.commission_journal_entry = je.name
        self.status = "Commission Created"
        self.save()
        frappe.db.commit()

        return {"status": "success", "journal_entry": je.name}

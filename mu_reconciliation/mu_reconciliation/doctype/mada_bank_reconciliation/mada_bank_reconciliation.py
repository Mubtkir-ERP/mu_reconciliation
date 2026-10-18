# -*- coding: utf-8 -*-
# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate
from mu_reconciliation.utils.statement_parser import parse_bank_file


class MadaBankReconciliation(Document):
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

            if "مطابق" in (row.matched_status or ""):
                total_matched += dep
            else:
                total_unmatched_bank += dep

        self.total_bank_deposits = total_dep
        self.total_bank_commissions = total_comm
        self.total_matched_amount = total_matched
        self.total_unmatched_in_system = total_unmatched_bank

    @frappe.whitelist()
    def parse_statement(self):
        """قراءة واستخراج حركات مدى من ملف كشف الحساب البنكي المرفق (Excel أو PDF أو CSV)."""
        if not self.bank_statement_file:
            frappe.throw(_("يرجى إرفاق ملف كشف الحساب البنكي أولاً."))

        file_doc = frappe.get_doc("File", {"file_url": self.bank_statement_file})
        full_path = file_doc.get_full_path()

        records = parse_bank_file(full_path)
        if not records:
            frappe.throw(_("لم يتم العثور على أي حركات مدى في الملف المرفق. تأكد من صحة الملف."))

        self.set("statement_rows", [])
        added = 0
        for rec in records:
            if rec.get("credit", 0) > 0 or rec.get("commission", 0) > 0:
                self.append("statement_rows", {
                    "txn_date": rec.get("date") or self.from_date or nowdate(),
                    "terminal_id": rec.get("terminal_id"),
                    "batch_no": rec.get("batch_no"),
                    "credit_amount": rec.get("credit", 0.0),
                    "commission_amount": rec.get("commission", 0.0),
                    "description": rec.get("description"),
                    "matched_status": "معلق / غير مودع 🔴"
                })
                added += 1

        self.status = "Parsed"
        self.calculate_summary()
        self.save()
        frappe.db.commit()
        return {"status": "success", "rows_added": added}

    @frappe.whitelist()
    def run_reconciliation(self):
        """إجراء المطابقة الذكية بين إيداعات البنك وموازنات النظام المسجلة."""
        if not self.statement_rows:
            self.parse_statement()

        from_d = self.from_date or "2000-01-01"
        to_d = self.to_date or "2099-12-31"

        # 1. جلب موازنات النظام المسجلة في الفترة
        system_settlements = frappe.db.sql(
            """
            SELECT 
                r.name as row_name,
                r.parent as entry_name,
                r.terminal_id,
                r.batch_no,
                r.settlement_date,
                r.amount
            FROM `tabMada Settlement Entry Row` r
            INNER JOIN `tabMada Settlement Entry` p ON p.name = r.parent
            WHERE p.docstatus = 1
              AND r.settlement_date BETWEEN %s AND %s
            """,
            (from_d, to_d),
            as_dict=True
        )

        total_system = sum(flt(s.amount) for s in system_settlements)
        self.total_system_settlements = total_system

        matched_system_rows = set()
        matched_count = 0

        # 2. مطابقة سطور البنك مع النظام بناء على رقم الجهاز + التاريخ + المبلغ
        for bank_row in self.statement_rows:
            b_tid = str(bank_row.terminal_id or "").strip()
            b_date = str(bank_row.txn_date)
            b_amt = flt(bank_row.credit_amount)

            if b_amt <= 0:
                continue

            # البحث عن مطابقة تامة: رقم الجهاز والمبلغ
            match = None
            for s in system_settlements:
                if s.row_name in matched_system_rows:
                    continue
                s_tid = str(s.terminal_id or "").strip()
                s_amt = flt(s.amount)
                # مطابقة رقم الجهاز والمبلغ (مع سماحية يومين في التاريخ لاختلاف وقت الإيداع البنكي)
                if s_tid == b_tid and abs(s_amt - b_amt) < 0.05:
                    match = s
                    break

            if match:
                bank_row.matched_status = "مطابق 🟢"
                bank_row.matched_entry = match.entry_name
                matched_system_rows.add(match.row_name)
                matched_count += 1
                # تحديث سطر الموازنة في النظام
                frappe.db.set_value("Mada Settlement Entry Row", match.row_name, "reconciliation_status", "مطابق بالبنك 🟢")
            else:
                bank_row.matched_status = "إيداع بدون موازنة 🟡"

        # 3. حساب المبالغ المعلقة / المفقودة من البنك (موجودة في النظام ولم تنزل في البنك)
        missing_total = 0.0
        missing_list = []
        for s in system_settlements:
            if s.row_name not in matched_system_rows:
                missing_total += flt(s.amount)
                missing_list.append(s)
                frappe.db.set_value("Mada Settlement Entry Row", s.row_name, "reconciliation_status", "معلق / في الانتظار")

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
        """توليد قيد عمولات البنك المجمعة للأسبوع بضغطة زر واحدة."""
        if self.commission_journal_entry and frappe.db.exists("Journal Entry", self.commission_journal_entry):
            frappe.throw(_("تم بالفعل توليد قيد العمولة لهذا الكشف: {0}").format(self.commission_journal_entry))

        total_comm = flt(self.total_bank_commissions)
        if total_comm <= 0:
            frappe.throw(_("لا توجد مبالغ عمولات لتوليد القيد."))

        settings = frappe.get_single("Mada Reconciliation Settings")
        expense_acc = settings.commission_expense_account
        bank_acc = self.bank_account or settings.default_bank_account
        vat_acc = settings.commission_vat_account
        vat_rate = flt(settings.vat_rate_on_commission or 15.0)

        if not expense_acc:
            frappe.throw(_("يرجى تحديد حساب مصروف عمولات مدى في شاشة إعدادات المطابقة."))
        if not bank_acc:
            frappe.throw(_("يرجى اختيار الحساب البنكي أولاً."))

        # حساب ضريبة القيمة المضافة على العمولة
        company = frappe.db.get_value("Account", bank_acc, "company")
        vat_amount = 0.0
        net_expense = total_comm

        if vat_acc and vat_rate > 0:
            # عمولة مدى عادة شاملة الضريبة: Net = Total / (1 + Rate)
            net_expense = flt(total_comm / (1.0 + (vat_rate / 100.0)), 2)
            vat_amount = flt(total_comm - net_expense, 2)

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Bank Entry"
        je.company = company
        je.posting_date = self.to_date or nowdate()
        je.user_remark = f"قيد إثبات عمولات شبكة مدى لكشف الفترة {self.from_date} إلى {self.to_date} - سند مطابقة: {self.name}"

        # 1. طرف المدين: مصروف العمولات
        je.append("accounts", {
            "account": expense_acc,
            "debit_in_account_currency": net_expense,
            "credit_in_account_currency": 0,
            "user_remark": "مصروف عمولة مدى"
        })

        # 2. طرف المدين: ضريبة المدخلات على العمولة (إن وجدت)
        if vat_acc and vat_amount > 0:
            je.append("accounts", {
                "account": vat_acc,
                "debit_in_account_currency": vat_amount,
                "credit_in_account_currency": 0,
                "user_remark": f"ضريبة القيمة المضافة {vat_rate}% على عمولة مدى"
            })

        # 3. طرف الدائن: حساب البنك
        je.append("accounts", {
            "account": bank_acc,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": total_comm,
            "user_remark": "خصم عمولات مدى من رصيد البنك"
        })

        je.flags.ignore_permissions = True
        je.insert()
        je.submit()

        self.commission_journal_entry = je.name
        self.status = "Commission Created"
        self.save()
        frappe.db.commit()

        return {
            "status": "success",
            "journal_entry": je.name,
            "total_commission": total_comm
        }

# -*- coding: utf-8 -*-
# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "terminal",
            "label": _("Mada Terminal"),
            "fieldtype": "Link",
            "options": "Mada Terminal",
            "width": 130,
        },
        {
            "fieldname": "terminal_id",
            "label": _("Terminal ID (TID)"),
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "fieldname": "branch",
            "label": _("Branch"),
            "fieldtype": "Link",
            "options": "Branch",
            "width": 120,
        },
        {
            "fieldname": "settlement_date",
            "label": _("Settlement Date"),
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "fieldname": "batch_no",
            "label": _("Batch No"),
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "system_amount",
            "label": _("System Amount"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "bank_amount",
            "label": _("Deposited in Bank"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "difference",
            "label": _("Pending Amount"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "commission_amount",
            "label": _("Bank Commission"),
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "fieldname": "status",
            "label": _("Reconciliation Status"),
            "fieldtype": "Data",
            "width": 160,
        },
    ]


def get_data(filters):
    filters = filters or {}
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("r.settlement_date >= %(from_date)s")
        values["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        conditions.append("r.settlement_date <= %(to_date)s")
        values["to_date"] = filters.get("to_date")
    if filters.get("terminal"):
        conditions.append("r.terminal = %(terminal)s")
        values["terminal"] = filters.get("terminal")

    where_clause = f"AND {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT
            r.terminal,
            r.terminal_id,
            t.branch,
            r.settlement_date,
            r.batch_no,
            r.amount as system_amount,
            r.reconciliation_status,
            r.name as row_id,
            p.name as entry_name
        FROM `tabMada Settlement Entry Row` r
        LEFT JOIN `tabMada Terminal` t ON t.name = r.terminal
        INNER JOIN `tabMada Settlement Entry` p ON p.name = r.parent
        WHERE p.docstatus < 2 {where_clause}
        ORDER BY r.settlement_date DESC
    """
    system_rows = frappe.db.sql(query, values, as_dict=True)

    data = []
    for r in system_rows:
        sys_amt = flt(r.system_amount)
        clean_tid = str(r.terminal_id or "").strip()[:8]

        # Search for matching bank row by matched_entry or TID + Amount
        bank_match = frappe.db.sql(
            """
            SELECT credit_amount, commission_amount, matched_status
            FROM `tabMada Bank Statement Row`
            WHERE matched_entry = %s
               OR (
                   (terminal_id = %s OR terminal_id LIKE CONCAT(%s, '%%') OR %s LIKE CONCAT(terminal_id, '%%'))
                   AND abs(credit_amount - %s) < 0.5
               )
            LIMIT 1
            """,
            (r.entry_name, clean_tid, clean_tid, str(r.terminal_id or "").strip(), sys_amt),
            as_dict=True
        )

        bank_amt = flt(bank_match[0].credit_amount) if bank_match else 0.0
        comm_amt = flt(bank_match[0].commission_amount) if bank_match else 0.0
        diff = bank_amt - sys_amt

        is_matched = (bank_amt > 0 and abs(diff) < 0.5) or (r.reconciliation_status and "Matched" in r.reconciliation_status or "مطابق" in (r.reconciliation_status or ""))

        if is_matched:
            status_str = _("Reconciled with Bank 🟢")
            if bank_amt == 0:
                bank_amt = sys_amt
                diff = 0.0
        else:
            status_str = _("Pending Bank Deposit 🔴")

        data.append({
            "terminal": r.terminal,
            "terminal_id": r.terminal_id,
            "branch": r.branch,
            "settlement_date": r.settlement_date,
            "batch_no": r.batch_no,
            "system_amount": sys_amt,
            "bank_amount": bank_amt,
            "difference": diff,
            "commission_amount": comm_amt,
            "status": status_str,
        })

    return data

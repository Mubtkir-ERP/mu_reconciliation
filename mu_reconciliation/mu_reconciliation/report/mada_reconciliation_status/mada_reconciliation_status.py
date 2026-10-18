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
            "fieldname": "terminal_id",
            "label": _("رقم الجهاز (TID)"),
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "terminal_name",
            "label": _("اسم الجهاز / السائق"),
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "fieldname": "branch",
            "label": _("الفرع"),
            "fieldtype": "Link",
            "options": "Branch",
            "width": 120,
        },
        {
            "fieldname": "settlement_date",
            "label": _("تاريخ الموازنة"),
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "fieldname": "batch_no",
            "label": _("رقم الموازنة"),
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "system_amount",
            "label": _("المبلغ بالنظام"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "bank_amount",
            "label": _("المودع بالبنك"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "difference",
            "label": _("الفرق / معلق"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "commission_amount",
            "label": _("عمولة البنك"),
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "fieldname": "status",
            "label": _("حالة المطابقة"),
            "fieldtype": "Data",
            "width": 140,
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

    # استخراج موازنات النظام وحالات مطابقتها
    query = f"""
        SELECT
            r.terminal_id,
            t.terminal_name,
            t.branch,
            r.settlement_date,
            r.batch_no,
            r.amount as system_amount,
            r.reconciliation_status,
            r.name as row_id
        FROM `tabMada Settlement Entry Row` r
        LEFT JOIN `tabMada Terminal` t ON t.name = r.terminal
        INNER JOIN `tabMada Settlement Entry` p ON p.name = r.parent
        WHERE p.docstatus = 1 {where_clause}
        ORDER BY r.settlement_date DESC
    """
    system_rows = frappe.db.sql(query, values, as_dict=True)

    data = []
    for r in system_rows:
        sys_amt = flt(r.system_amount)
        # البحث عن مطابقة في أسطر كشوفات البنك
        bank_match = frappe.db.sql(
            """
            SELECT credit_amount, commission_amount, matched_status
            FROM `tabMada Bank Statement Row`
            WHERE terminal_id = %s AND abs(credit_amount - %s) < 0.05
            LIMIT 1
            """,
            (r.terminal_id, sys_amt),
            as_dict=True
        )

        bank_amt = flt(bank_match[0].credit_amount) if bank_match else 0.0
        comm_amt = flt(bank_match[0].commission_amount) if bank_match else 0.0
        diff = bank_amt - sys_amt

        status_str = "مطابق بالبنك 🟢" if (bank_amt > 0 and abs(diff) < 0.05) else "معلق / مفقود بالبنك 🔴"

        data.append({
            "terminal_id": r.terminal_id,
            "terminal_name": r.terminal_name,
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

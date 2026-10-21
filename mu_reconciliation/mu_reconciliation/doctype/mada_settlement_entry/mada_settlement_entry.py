# -*- coding: utf-8 -*-
# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint


class MadaSettlementEntry(Document):
    def validate(self):
        self.calculate_totals()

    def calculate_totals(self):
        total_amount = 0.0
        total_txns = 0
        for row in self.get("settlement_rows") or []:
            total_amount += flt(row.amount)
            total_txns += cint(row.transaction_count)
            if not row.settlement_date:
                row.settlement_date = self.entry_date
            if row.terminal:
                if not row.terminal_id:
                    row.terminal_id = frappe.db.get_value("Mada Terminal", row.terminal, "terminal_id") or row.terminal
                if not row.employee:
                    row.employee = frappe.db.get_value("Mada Terminal", row.terminal, "current_employee")

        self.total_settlement_amount = total_amount
        self.total_transactions = total_txns

# -*- coding: utf-8 -*-
# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class MadaTerminal(Document):
    def validate(self):
        if self.terminal_id:
            self.terminal_id = str(self.terminal_id).strip()

    @frappe.whitelist()
    def reassign_terminal(self, employee=None, user=None, reason=None, notes=None):
        """تسليم أو تغيير السائق/الموظف المسؤول عن الجهاز وتوثيق ذلك في سجل الحركات."""
        now = now_datetime()
        # إغلاق آخر عملية تسليم مفتوحة
        for row in reversed(self.get("assignment_history") or []):
            if not row.returned_date:
                row.returned_date = now
                break

        # إضافة سطر التسليم الجديد
        self.append("assignment_history", {
            "assigned_employee": employee or None,
            "assigned_user": user or None,
            "assigned_date": now,
            "reason": reason or _("تغيير الموظف المسؤول"),
            "notes": notes or None,
        })

        self.current_employee = employee or None
        self.current_user = user or None
        self.flags.ignore_permissions = True
        self.save()
        return {"status": "success", "message": _("تم تسليم الجهاز وتحديث السجل بنجاح")}

# -*- coding: utf-8 -*-
import frappe

def after_migrate():
    """Cleanup legacy workspace and ensure new Bank Reconciliation workspace is active."""
    for old_name in ["Mada Reconciliation", "mada_reconciliation", "مطابقة مدى"]:
        if frappe.db.exists("Workspace", old_name):
            try:
                frappe.delete_doc("Workspace", old_name, force=1, ignore_permissions=True)
            except Exception:
                pass
    frappe.db.commit()

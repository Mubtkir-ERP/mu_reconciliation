# -*- coding: utf-8 -*-
import frappe


def after_migrate():
    """Cleanup legacy workspaces and ensure Bank Reconciliation workspace is active and clean."""
    try:
        # 1. Delete all old workspaces by known names
        old_workspaces = [
            "Mada Reconciliation", "mada_reconciliation", "مطابقة مدى",
            "Mu Reconciliation", "mu_reconciliation", "mu-reconciliation"
        ]
        for name in old_workspaces:
            frappe.db.sql("DELETE FROM `tabWorkspace` WHERE name=%s OR label=%s OR title=%s", (name, name, name))

        # 2. Delete any workspace belonging to 'Mu Reconciliation' module that is not 'Bank Reconciliation'
        frappe.db.sql(
            "DELETE FROM `tabWorkspace` WHERE module='Mu Reconciliation' AND name != 'Bank Reconciliation'"
        )

        # 3. Ensure Bank Reconciliation workspace exists and has clean label
        if frappe.db.exists("Workspace", "Bank Reconciliation"):
            frappe.db.sql(
                "UPDATE `tabWorkspace` SET label='Bank Reconciliation', title='Bank Reconciliation' WHERE name='Bank Reconciliation'"
            )
        frappe.db.commit()
    except Exception:
        pass

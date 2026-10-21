# -*- coding: utf-8 -*-
import frappe


def after_migrate():
    """Cleanup legacy workspaces, ensure Bank Reconciliation workspace is clean, and enforce naming series."""
    try:
        # 1. Update naming series in tabDocField directly
        frappe.db.sql("""
            UPDATE `tabDocField`
            SET `default` = 'BR-.YY.-.#####', `options` = 'BR-.YY.-.#####'
            WHERE `parent` = 'Mada Bank Reconciliation' AND `fieldname` = 'naming_series'
        """)
        frappe.db.sql("""
            UPDATE `tabDocField`
            SET `default` = 'MADA-.YY.-.MM.-.####', `options` = 'MADA-.YY.-.MM.-.####'
            WHERE `parent` = 'Mada Settlement Entry' AND `fieldname` = 'naming_series'
        """)
        frappe.db.sql("""
            UPDATE `tabDocField`
            SET `default` = 'M-.####', `options` = 'M-.####'
            WHERE `parent` = 'Mada Terminal' AND `fieldname` = 'naming_series'
        """)

        # 2. Delete any conflicting property setters
        frappe.db.sql("""
            DELETE FROM `tabProperty Setter`
            WHERE `doc_type` IN ('Mada Bank Reconciliation', 'Mada Settlement Entry', 'Mada Terminal')
              AND `field_name` = 'naming_series'
        """)

        # 3. Clean up legacy workspaces permanently
        old_workspaces = [
            "Mada Reconciliation", "mada_reconciliation", "مطابقة مدى",
            "Mu Reconciliation", "mu_reconciliation", "mu-reconciliation"
        ]
        for name in old_workspaces:
            frappe.db.sql("DELETE FROM `tabWorkspace` WHERE name=%s OR label=%s OR title=%s", (name, name, name))

        frappe.db.sql(
            "DELETE FROM `tabWorkspace` WHERE module='Mu Reconciliation' AND name != 'Bank Reconciliation'"
        )

        # 4. Ensure Bank Reconciliation workspace exists and has clean Arabic label
        frappe.db.sql("""
            UPDATE `tabWorkspace` 
            SET label='مطابقة البنوك', title='مطابقة البنوك' 
            WHERE name='Bank Reconciliation'
        """)
        frappe.db.commit()
    except Exception:
        pass

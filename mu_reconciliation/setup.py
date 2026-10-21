# -*- coding: utf-8 -*-
import csv
import os
import frappe


def after_migrate():
    """
    1. Cleanup legacy workspaces
    2. Ensure Bank Reconciliation workspace is clean with English label/title (translated via ar.csv/tabTranslation)
    3. Update naming series in tabDocField
    4. Sync translations into tabTranslation for language 'ar'
    """
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
            "Mu Reconciliation", "mu_reconciliation", "mu-reconciliation", "مطابقة البنوك"
        ]
        for name in old_workspaces:
            frappe.db.sql("DELETE FROM `tabWorkspace` WHERE name=%s OR label=%s OR title=%s", (name, name, name))

        frappe.db.sql(
            "DELETE FROM `tabWorkspace` WHERE module='Mu Reconciliation' AND name != 'Bank Reconciliation'"
        )

        # 4. Ensure Bank Reconciliation workspace has standard English name/label/title
        frappe.db.sql("""
            UPDATE `tabWorkspace` 
            SET label='Bank Reconciliation', title='Bank Reconciliation' 
            WHERE name='Bank Reconciliation'
        """)

        # 5. Populate/Sync tabTranslation for Arabic
        csv_path = os.path.join(os.path.dirname(__file__), "translations", "ar.csv")
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2 and row[0].strip() and row[1].strip():
                        src = row[0].strip()
                        dst = row[1].strip()
                        # Use frappe Translation doctype or direct SQL
                        frappe.db.sql("""
                            INSERT INTO `tabTranslation` (`name`, `language`, `source_text`, `translated_text`, `docstatus`)
                            VALUES (%s, 'ar', %s, %s, 0)
                            ON DUPLICATE KEY UPDATE `translated_text` = %s
                        """, (f"ar:{src}"[:140], src, dst, dst))

        frappe.db.commit()
    except Exception:
        pass

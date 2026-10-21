# -*- coding: utf-8 -*-
# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

app_name = "mu_reconciliation"
app_title = "مطابقة البنوك"
app_publisher = "Mubtkir"
app_description = "نظام مطابقة مبيعات شبكة مدى وموازنات الأجهزة مع كشوف الحسابات البنكية"
app_email = "info@mubtkir.com"
app_license = "mit"
required_apps = ["erpnext"]

after_migrate = "mu_reconciliation.setup.after_migrate"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/mu_reconciliation/css/mu_reconciliation.css"
# app_include_js = "/assets/mu_reconciliation/js/mu_reconciliation.js"

# Document Events
# ---------------
# Hook on POS Closing Shift or Sales Invoice if needed
# doc_events = {
# 	"POS Closing Shift": {
# 		"on_submit": "mu_reconciliation.mu_reconciliation.doctype.mada_settlement_entry.mada_settlement_entry.on_closing_shift_submit"
# 	}
# }

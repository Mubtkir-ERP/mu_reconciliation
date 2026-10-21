// Copyright (c) 2026, Mubtkir and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mada Bank Reconciliation", {
    refresh(frm) {
        if (!frm.is_new()) {
            // Button 1: Parse Statement
            frm.add_custom_button(__("1. Parse Statement"), () => {
                if (!frm.doc.bank_statement_file) {
                    frappe.msgprint(__("Please attach the bank statement file first (Excel, PDF, or CSV)"));
                    return;
                }
                frm.call({
                    method: "parse_statement",
                    doc: frm.doc,
                    freeze: true,
                    freeze_message: __("Parsing bank statement and extracting MADA transactions..."),
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.show_alert({ 
                                message: __("Extracted {0} MADA transaction(s) within selected date range.", [r.message.rows_added]), 
                                indicator: "green" 
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }).addClass("btn-secondary");

            // Button 2: Reconcile
            frm.add_custom_button(__("2. Reconcile Transactions"), () => {
                frm.call({
                    method: "run_reconciliation",
                    doc: frm.doc,
                    freeze: true,
                    freeze_message: __("Reconciling system settlements with bank statement deposits..."),
                    callback: function(r) {
                        if (!r.exc) {
                            let msg = __("Reconciliation completed! Matched: {0} | Pending in Bank: {1}", 
                                [r.message.matched_count, format_currency(r.message.missing_total)]);
                            frappe.msgprint({
                                title: __("Reconciliation Result"),
                                message: msg,
                                indicator: r.message.missing_total > 0 ? "orange" : "green"
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }).addClass("btn-primary");

            // Button 3: Create Commission Journal Entry
            if (frm.doc.total_bank_commissions > 0 && !frm.doc.commission_journal_entry) {
                frm.add_custom_button(__("3. Create Commission Entry"), () => {
                    frappe.confirm(
                        __("Are you sure you want to create and submit a Journal Entry for bank commissions of {0}?", 
                            [format_currency(frm.doc.total_bank_commissions)]),
                        () => {
                            frm.call({
                                method: "create_commission_journal_entry",
                                doc: frm.doc,
                                freeze: true,
                                freeze_message: __("Creating and submitting Journal Entry..."),
                                callback: function(r) {
                                    if (!r.exc) {
                                        frappe.show_alert({
                                            message: __("Journal Entry created successfully: {0}", [r.message.journal_entry]),
                                            indicator: "green"
                                        });
                                        frm.reload_doc();
                                    }
                                }
                            });
                        }
                    );
                }).addClass("btn-warning");
            }

            // Dashboard summary headline
            if (frm.doc.status === "Reconciled" || frm.doc.status === "Commission Created") {
                let matched = format_currency(frm.doc.total_matched_amount);
                let missing = format_currency(frm.doc.total_missing_in_bank);
                let comm = format_currency(frm.doc.total_bank_commissions);

                let banner = `
                    <div style="display:flex; gap:16px; padding:12px; background:#f8fafc; border-radius:8px; margin-bottom:15px; border:1px solid #e2e8f0;">
                        <div style="flex:1; border-left:4px solid #22c55e; padding-left:10px;">
                            <div style="font-size:12px; color:#64748b;">${__("Matched & Deposited in Bank 🟢")}</div>
                            <div style="font-size:18px; font-weight:bold; color:#166534;">${matched}</div>
                        </div>
                        <div style="flex:1; border-left:4px solid #ef4444; padding-left:10px;">
                            <div style="font-size:12px; color:#64748b;">${__("Missing / Pending in Bank 🔴")}</div>
                            <div style="font-size:18px; font-weight:bold; color:#991b1b;">${missing}</div>
                        </div>
                        <div style="flex:1; border-left:4px solid #3b82f6; padding-left:10px;">
                            <div style="font-size:12px; color:#64748b;">${__("Bank Commissions Deducted 💳")}</div>
                            <div style="font-size:18px; font-weight:bold; color:#1e40af;">${comm}</div>
                        </div>
                    </div>
                `;
                frm.dashboard.set_headline(banner);
            }
        }
    }
});

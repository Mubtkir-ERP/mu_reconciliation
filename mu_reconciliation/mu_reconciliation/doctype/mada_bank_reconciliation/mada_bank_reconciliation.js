// Copyright (c) 2026, Mubtkir and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mada Bank Reconciliation", {
    refresh(frm) {
        if (!frm.is_new()) {
            // زر قراءة وتحليل الكشف
            frm.add_custom_button(__("1. قراءة وتحليل الكشف"), () => {
                if (!frm.doc.bank_statement_file) {
                    frappe.msgprint(__("يرجى إرفاق ملف كشف الحساب البنكي أولاً (Excel أو PDF أو CSV)"));
                    return;
                }
                frm.call({
                    method: "parse_statement",
                    doc: frm.doc,
                    freeze: true,
                    freeze_message: __("جاري قراءة وتحليل ملف البنك واستخراج حركات مدى..."),
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.show_alert({ message: __("تم استخراج حركات مدى بنجاح"), indicator: "green" });
                            frm.reload_doc();
                        }
                    }
                });
            }).addClass("btn-secondary");

            // زر إجراء المطابقة
            frm.add_custom_button(__("2. إجراء المطابقة الذكية"), () => {
                frm.call({
                    method: "run_reconciliation",
                    doc: frm.doc,
                    freeze: true,
                    freeze_message: __("جاري مطابقة موازنات الأجهزة مع إيداعات البنك..."),
                    callback: function(r) {
                        if (!r.exc) {
                            let msg = __("تمت المطابقة بنجاح! المطابق: {0} حركة | مبالغ معلقة بالبنك: {1} ريال", 
                                [r.message.matched_count, format_currency(r.message.missing_total)]);
                            frappe.msgprint({
                                title: __("نتيجة المطابقة"),
                                message: msg,
                                indicator: r.message.missing_total > 0 ? "orange" : "green"
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }).addClass("btn-primary");

            // زر توليد قيد العمولة
            if (frm.doc.total_bank_commissions > 0 && !frm.doc.commission_journal_entry) {
                frm.add_custom_button(__("3. توليد قيد العمولة البنكية"), () => {
                    frappe.confirm(
                        __("هل أنت متأكد من إنشاء وترحيل قيد اليومية لعمولات مدى بمبلغ {0} ريال؟", [frm.doc.total_bank_commissions]),
                        () => {
                            frm.call({
                                method: "create_commission_journal_entry",
                                doc: frm.doc,
                                freeze: true,
                                freeze_message: __("جاري إنشاء وترحيل قيد اليومية للعمولات..."),
                                callback: function(r) {
                                    if (!r.exc) {
                                        frappe.show_alert({
                                            message: __("تم إنشاء وترحيل قيد اليومية: {0}", [r.message.journal_entry]),
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

            // شريط إحصائي أنيق في أعلى المستند
            if (frm.doc.status === "Reconciled" || frm.doc.status === "Commission Created") {
                let matched = format_currency(frm.doc.total_matched_amount);
                let missing = format_currency(frm.doc.total_missing_in_bank);
                let comm = format_currency(frm.doc.total_bank_commissions);

                let banner = `
                    <div style="display:flex; gap:16px; padding:12px; background:#f8fafc; border-radius:8px; margin-bottom:15px; border:1px solid #e2e8f0;">
                        <div style="flex:1; border-left:4px solid #22c55e; padding-left:10px;">
                            <div style="font-size:12px; color:#64748b;">المطابق والمودع بالبنك 🟢</div>
                            <div style="font-size:18px; font-weight:bold; color:#166534;">${matched}</div>
                        </div>
                        <div style="flex:1; border-left:4px solid #ef4444; padding-left:10px;">
                            <div style="font-size:12px; color:#64748b;">المبالغ المفقودة / المعلقة بالبنك 🔴</div>
                            <div style="font-size:18px; font-weight:bold; color:#991b1b;">${missing}</div>
                        </div>
                        <div style="flex:1; border-left:4px solid #3b82f6; padding-left:10px;">
                            <div style="font-size:12px; color:#64748b;">عمولات البنك المحسومة 💳</div>
                            <div style="font-size:18px; font-weight:bold; color:#1e40af;">${comm}</div>
                        </div>
                    </div>
                `;
                frm.dashboard.set_headline(banner);
            }
        }
    }
});

// Copyright (c) 2026, Mubtkir and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mada Terminal", {
    onload(frm) {
        frm.set_df_property("naming_series", "options", ["M-.####"]);
        if (frm.is_new() && !frm.doc.naming_series) {
            frm.set_value("naming_series", "M-.####");
        }
    },
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("تسليم جهاز لسائق / موظف"), () => {
                let d = new frappe.ui.Dialog({
                    title: __("تسليم جهاز مدى {0}", [frm.doc.terminal_id]),
                    fields: [
                        {
                            label: __("السائق / الموظف الجديد"),
                            fieldname: "employee",
                            fieldtype: "Link",
                            options: "Employee",
                            reqd: 1,
                        },
                        {
                            label: __("حساب المستخدم"),
                            fieldname: "user",
                            fieldtype: "Link",
                            options: "User",
                        },
                        {
                            label: __("سبب الاستبدال / التسليم"),
                            fieldname: "reason",
                            fieldtype: "Data",
                            reqd: 1,
                            default: __("عطل بالجهاز السابق / استلام عهدة"),
                        },
                        {
                            label: __("ملاحظات"),
                            fieldname: "notes",
                            fieldtype: "Small Text",
                        },
                    ],
                    primary_action_label: __("تأكيد التسليم"),
                    primary_action(values) {
                        d.hide();
                        frappe.call({
                            method: "reassign_terminal",
                            doc: frm.doc,
                            args: values,
                            freeze: true,
                            callback: function(r) {
                                if (!r.exc) {
                                    frappe.show_alert({
                                        message: __("تم تسليم الجهاز وتحديث السائق الحالي"),
                                        indicator: "green"
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                });
                d.show();
            }).addClass("btn-primary");
        }
    }
});

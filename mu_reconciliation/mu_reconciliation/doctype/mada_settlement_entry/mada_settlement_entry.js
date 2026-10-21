// Copyright (c) 2026, Mubtkir and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mada Settlement Entry", {
    refresh(frm) {
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("جلب أجهزة مدى النشطة"), () => {
                let filters = { status: "Active" };
                if (frm.doc.branch) {
                    filters.branch = frm.doc.branch;
                }
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Mada Terminal",
                        filters: filters,
                        fields: ["name", "terminal_id", "current_employee"]
                    },
                    callback: function(r) {
                        if (r.message && r.message.length > 0) {
                            r.message.forEach(term => {
                                let existing = (frm.doc.settlement_rows || []).find(d => d.terminal === term.name);
                                if (!existing) {
                                    let row = frm.add_child("settlement_rows");
                                    row.terminal = term.name;
                                    row.terminal_id = term.terminal_id;
                                    row.employee = term.current_employee;
                                    row.settlement_date = frm.doc.entry_date || frappe.datetime.nowdate();
                                }
                            });
                            frm.refresh_field("settlement_rows");
                            frappe.show_alert({ message: __("تم إضافة أجهزة مدى بنجاح"), indicator: "green" });
                        } else {
                            frappe.msgprint(__("لا توجد أجهزة مدى نشطة مسجلة"));
                        }
                    }
                });
            });
        }
    },
    branch(frm) {
        if (frm.doc.branch && (!frm.doc.settlement_rows || frm.doc.settlement_rows.length === 0)) {
            frm.trigger("refresh");
        }
    }
});

frappe.ui.form.on("Mada Settlement Entry Row", {
    amount(frm) {
        let total = 0;
        (frm.doc.settlement_rows || []).forEach(r => {
            total += flt(r.amount);
        });
        frm.set_value("total_settlement_amount", total);
    },
    terminal(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.terminal) {
            frappe.db.get_value("Mada Terminal", row.terminal, ["terminal_id", "current_employee"]).then(r => {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, "terminal_id", r.message.terminal_id);
                    frappe.model.set_value(cdt, cdn, "employee", r.message.current_employee);
                }
            });
        }
    }
});

// Copyright (c) 2026, Mubtkir and contributors
// For license information, please see license.txt

frappe.query_reports["Mada Reconciliation Status"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.nowdate(), -1),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.nowdate(),
        },
        {
            fieldname: "terminal",
            label: __("Mada Terminal"),
            fieldtype: "Link",
            options: "Mada Terminal",
        },
    ],
    formatter(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname === "status") {
            if (data && data.status && (data.status.includes("Reconciled") || data.status.includes("مطابق"))) {
                value = `<span style="color:green; font-weight:bold;">${value}</span>`;
            } else if (data && data.status && (data.status.includes("Pending") || data.status.includes("معلق"))) {
                value = `<span style="color:red; font-weight:bold;">${value}</span>`;
            }
        }
        return value;
    }
};

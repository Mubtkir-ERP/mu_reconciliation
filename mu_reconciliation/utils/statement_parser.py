# -*- coding: utf-8 -*-
# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

import csv
import io
import os
import re
from datetime import datetime
import frappe
from frappe.utils import flt, getdate

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def clean_number(val):
    """Normalize and convert text to float, supporting Arabic numbers and comma decimals."""
    if val is None or val == "":
        return 0.0
    s = str(val).translate(ARABIC_DIGITS).replace("٬", "").replace(",", "").strip()
    try:
        return flt(s)
    except Exception:
        return 0.0


def parse_date_str(val):
    """Parse various bank date formats into standard YYYY-MM-DD."""
    if not val:
        return None
    if isinstance(val, (datetime,)):
        return val.strftime("%Y-%m-%d")
    s = str(val).translate(ARABIC_DIGITS).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        return str(getdate(s))
    except Exception:
        return None


def parse_bank_file(file_path):
    """
    Universal bank statement parser supporting:
    - Excel: .xls (BIFF8), .xlsx
    - Delimited: .csv, .txt
    - Documents: .pdf
    
    Returns a list of dicts:
    [
        {
            "terminal_id": "15691146",
            "date": "2026-10-12",
            "credit": 703.00,
            "commission": 5.25,
            "batch_no": "000149",
            "description": "..."
        },
        ...
    ]
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv" or ext == ".txt":
        return parse_csv(file_path)
    elif ext == ".xlsx":
        return parse_xlsx(file_path)
    elif ext == ".xls":
        return parse_xls(file_path)
    elif ext == ".pdf":
        return parse_pdf(file_path)
    else:
        # Fallback trial
        try:
            return parse_xlsx(file_path)
        except Exception:
            return parse_xls(file_path)


def parse_csv(file_path):
    with open(file_path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "utf-8", "windows-1256", "latin1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader]
    return extract_mada_records_from_table(rows)


def parse_xlsx(file_path):
    import openpyxl
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    ws = wb.active
    rows = []
    for r in ws.iter_rows(values_only=True):
        rows.append([str(c) if c is not None else "" for c in r])
    wb.close()
    return extract_mada_records_from_table(rows)


def parse_xls(file_path):
    """Parse legacy .xls using xlrd, or fallback to ole/string scanner."""
    try:
        import xlrd
        wb = xlrd.open_workbook(file_path)
        ws = wb.sheet_by_index(0)
        rows = []
        for rx in range(ws.nrows):
            rows.append([str(ws.cell_value(rx, cx)) for cx in range(ws.ncols)])
        return extract_mada_records_from_table(rows)
    except Exception:
        # Fallback parser using regex on text streams
        return parse_text_stream(file_path)


def parse_pdf(file_path):
    """Extract text from PDF and parse MADA batches."""
    text = ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
    except Exception:
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text += (page.extract_text() or "") + "\n"
        except Exception as e:
            frappe.throw(f"PDF extraction failed: {e}")

    return parse_text_lines(text.splitlines())


def parse_text_stream(file_path):
    with open(file_path, "rb") as f:
        content = f.read()
    # Extract readable strings
    strings = re.findall(rb"[\x20-\x7E\xA0-\xFF]{4,}", content)
    lines = [s.decode("latin1", errors="ignore") for s in strings]
    return parse_text_lines(lines)


def extract_mada_records_from_table(rows):
    """
    Parses structured tabular data (from Excel/CSV).
    Pairs Batch Deposits with their corresponding Commission rows.
    """
    records = []
    # Key: (TID, Date, BatchNo) -> {credit, commission, description}
    batch_map = {}

    for row in rows:
        if not row:
            continue
        row_str = " ".join(str(c) for c in row)
        match_tid = re.search(r"Term\s*(\d{8})", row_str, re.IGNORECASE)
        if not match_tid:
            continue

        tid = match_tid.group(1)
        is_commission = "commission" in row_str.lower() or "عمولة" in row_str

        # Search for date in row
        txn_date = None
        for cell in row:
            d = parse_date_str(cell)
            if d:
                txn_date = d
                break

        # Extract batch number if present (6 digits sequence)
        batch_no = None
        batch_match = re.search(r"\b(\d{6})\b", row_str)
        if batch_match:
            batch_no = batch_match.group(1)

        # Extract numbers from row (potential amounts)
        amounts = []
        for cell in row:
            val = clean_number(cell)
            if val != 0.0:
                amounts.append(val)

        # Identify credit / debit
        amount = abs(amounts[-1]) if amounts else 0.0

        key = (tid, txn_date, batch_no or "ALL")
        if key not in batch_map:
            batch_map[key] = {
                "terminal_id": tid,
                "date": txn_date,
                "batch_no": batch_no or "",
                "credit": 0.0,
                "commission": 0.0,
                "description": row_str[:120]
            }

        if is_commission:
            batch_map[key]["commission"] = amount
        else:
            if amount > 0:
                batch_map[key]["credit"] = amount

    return list(batch_map.values())


def parse_text_lines(lines):
    """Parse unstructured text lines (from PDF or string extraction)."""
    rows = [[line] for line in lines if line.strip()]
    return extract_mada_records_from_table(rows)

# -*- coding: utf-8 -*-
# Copyright (c) 2026, Mubtkir and contributors
# For license information, please see license.txt

import csv
import io
import os
import re
from datetime import datetime, timedelta
import frappe
from frappe.utils import flt, getdate

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def clean_number(val):
    """Normalize and convert text to float, supporting Arabic numbers and comma decimals."""
    if val is None or val == "":
        return 0.0
    s = str(val).translate(ARABIC_DIGITS).replace("٬", "").replace(",", "").replace(" ", "").strip()
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
    
    # Try excel serial float
    try:
        f = float(s)
        if 35000 < f < 65000:
            return (datetime(1899, 12, 30) + timedelta(days=int(f))).strftime("%Y-%m-%d")
    except Exception:
        pass

    # Standard date formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Regex search for YYYY-MM-DD inside text
    m = re.search(r"\b(202\d[-/]\d{1,2}[-/]\d{1,2})\b", s)
    if m:
        try:
            return str(getdate(m.group(1).replace("/", "-")))
        except Exception:
            pass

    # Regex search for DD/MM/YYYY
    m = re.search(r"\b(\d{1,2}/\d{1,2}/202\d)\b", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d/%m/%Y").strftime("%Y-%m-%d")
        except Exception:
            pass

    return None


def parse_bank_file(file_path):
    """
    Universal bank statement parser supporting:
    - Excel: .xls (BIFF8), .xlsx
    - Delimited: .csv, .txt
    - Documents: .pdf
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext in (".csv", ".txt"):
        return parse_csv(file_path)
    elif ext == ".xlsx":
        return parse_xlsx(file_path)
    elif ext == ".xls":
        return parse_xls(file_path)
    elif ext == ".pdf":
        return parse_pdf(file_path)
    else:
        try:
            return parse_xls(file_path)
        except Exception:
            return parse_xlsx(file_path)


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
    rows = [[str(c).strip() for c in r] for r in reader]
    return extract_mada_records_from_table(rows)


def parse_xlsx(file_path):
    import openpyxl
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    ws = wb.active
    rows = []
    for r in ws.iter_rows(values_only=True):
        row_vals = []
        for c in r:
            if isinstance(c, (datetime,)):
                row_vals.append(c.strftime("%Y-%m-%d"))
            elif isinstance(c, float) and 35000 < c < 65000:
                dt_str = parse_date_str(c)
                row_vals.append(dt_str or str(c))
            elif c is not None:
                row_vals.append(str(c).strip())
            else:
                row_vals.append("")
        rows.append(row_vals)
    wb.close()
    return extract_mada_records_from_table(rows)


def parse_xls(file_path):
    """Parse legacy .xls using xlrd with proper Excel date decoding."""
    try:
        import xlrd
        wb = xlrd.open_workbook(file_path)
        ws = wb.sheet_by_index(0)
        rows = []
        for rx in range(ws.nrows):
            row_vals = []
            for cx in range(ws.ncols):
                val = ws.cell_value(rx, cx)
                c_type = ws.cell_type(rx, cx)
                if c_type == xlrd.XL_CELL_DATE or (isinstance(val, float) and 35000 < val < 65000):
                    try:
                        dt = xlrd.xldate_as_datetime(val, wb.datemode).strftime("%Y-%m-%d")
                        row_vals.append(dt)
                        continue
                    except Exception:
                        pass
                row_vals.append(str(val).strip())
            rows.append(row_vals)
        return extract_mada_records_from_table(rows)
    except Exception:
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
    strings = re.findall(rb"[\x20-\x7E\xA0-\xFF]{4,}", content)
    lines = [s.decode("latin1", errors="ignore") for s in strings]
    return parse_text_lines(lines)


def extract_mada_records_from_table(rows):
    """
    Parses structured tabular data (from Excel/CSV).
    Pairs Batch Deposits with their corresponding Commission rows.
    """
    # Key: (TID, Date, BatchNo) -> dict
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

        # Fallback date search in entire row_str
        if not txn_date:
            date_m = re.search(r"\b(202\d-\d{2}-\d{2})\b", row_str)
            if date_m:
                txn_date = date_m.group(1)

        # Extract batch number if present (6 digits sequence)
        batch_no = ""
        batch_match = re.search(r"\b(\d{6})\b", row_str)
        if batch_match:
            batch_no = batch_match.group(1)

        # Extract amounts: find numbers in cells
        amounts = []
        for cell in row:
            val = clean_number(cell)
            if val != 0.0:
                amounts.append(abs(val))

        # Amount is typically in the last numeric columns
        amount = amounts[-1] if amounts else 0.0

        key = (tid, txn_date, batch_no or "ALL")
        if key not in batch_map:
            batch_map[key] = {
                "terminal_id": tid,
                "date": txn_date,
                "batch_no": batch_no,
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

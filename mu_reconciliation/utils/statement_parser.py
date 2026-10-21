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
    """
    Parse various bank date formats into standard YYYY-MM-DD.
    Strictly accepts Gregorian dates (2000 <= year <= 2099) and rejects Hijri years (e.g. 1448).
    Supports DD/MM/YYYY, MM/DD/YYYY, and YYYY-MM-DD.
    """
    if not val:
        return None
    if isinstance(val, (datetime,)):
        if 2000 <= val.year <= 2099:
            return val.strftime("%Y-%m-%d")
        return None

    s = str(val).translate(ARABIC_DIGITS).strip()
    if not s:
        return None

    # Must contain date separators (prevents converting amounts to dates)
    if not any(sep in s for sep in ("-", "/", ".")):
        return None

    # Standard formats
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            if 2000 <= dt.year <= 2099:
                return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Regex search for YYYY-MM-DD or YYYY/MM/DD or YYYY.MM.DD
    m = re.search(r"\b(20[2-9]\d)[-/.](\d{1,2})[-/.](\d{1,2})\b", s)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if 2000 <= dt.year <= 2099:
                return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    # Regex search for DD/MM/YYYY or MM/DD/YYYY
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20[2-9]\d)\b", s)
    if m:
        p1, p2, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # If p1 > 12, then p1 must be day, p2 is month (DD/MM/YYYY)
        if p1 > 12 and 1 <= p2 <= 12:
            try:
                return datetime(yr, p2, p1).strftime("%Y-%m-%d")
            except Exception:
                pass
        # If p2 > 12, then p2 must be day, p1 is month (MM/DD/YYYY)
        elif p2 > 12 and 1 <= p1 <= 12:
            try:
                return datetime(yr, p1, p2).strftime("%Y-%m-%d")
            except Exception:
                pass
        else:
            # Both <= 12: try DD/MM/YYYY first, valid Gregorian
            try:
                return datetime(yr, p2, p1).strftime("%Y-%m-%d")
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
                if c_type == xlrd.XL_CELL_DATE:
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
    strings = re.findall(b"[\\x20-\\x7E\\xA0-\\xFF]{4,}", content)
    lines = [s.decode("latin1", errors="ignore") for s in strings]
    return parse_text_lines(lines)


def extract_mada_records_from_table(rows):
    """
    Parses structured tabular data (from Excel/CSV).
    Pairs Batch Deposits with their corresponding Commission rows.
    """
    batch_map = {}

    for row in rows:
        if not row:
            continue
        row_str = " ".join(str(c) for c in row)
        
        # Match terminal ID with flexible labels (Term, Terminal, TID, جهاز, رقم الجهاز, POS)
        match_tid = re.search(r"(?:Term|Terminal|TID|جهاز|رقم\s*الجهاز|POS)\s*[:#-]?\s*(\d{8,16})", row_str, re.IGNORECASE)
        tid = ""
        if match_tid:
            tid = match_tid.group(1)
        else:
            # Fallback: check if row mentions MADA / POS / Settlement and contains an 8-16 digit number
            if any(k in row_str.lower() for k in ("mada", "مدى", "pos", "point of sale", "عمولة", "تسوية", "شبكة", "deposit", "settlement")):
                fallback_tid = re.search(r"\b(\d{8,16})\b", row_str)
                if fallback_tid:
                    tid = fallback_tid.group(1)

        if not tid:
            continue

        is_commission = "commission" in row_str.lower() or "عمولة" in row_str

        # Search for valid Gregorian date in row cells first (ignores Hijri dates like 1448-xx-xx)
        txn_date = None
        for cell in row:
            d = parse_date_str(cell)
            if d:
                txn_date = d
                break

        # Fallback date search in entire row_str
        if not txn_date:
            date_m = re.search(r"\b(20[2-9]\d[-/.]\d{1,2}[-/.]\d{1,2})\b", row_str)
            if date_m:
                txn_date = parse_date_str(date_m.group(1))
            if not txn_date:
                date_m2 = re.search(r"\b(\d{1,2}[-/.]\d{1,2}[-/.]20[2-9]\d)\b", row_str)
                if date_m2:
                    txn_date = parse_date_str(date_m2.group(1))

        # Extract batch number if present (6 digits sequence)
        batch_no = ""
        batch_match = re.search(r"\b(\d{6})\b", row_str)
        if batch_match:
            batch_no = batch_match.group(1)

        # Extract amounts from row
        numbers = []
        for cell in row:
            val_clean = clean_number(cell)
            if val_clean != 0:
                numbers.append(val_clean)

        key = f"{tid}_{batch_no}_{txn_date}" if batch_no else f"{tid}_{txn_date}_{len(batch_map)}"

        if key not in batch_map:
            batch_map[key] = {
                "terminal_id": tid,
                "date": txn_date,
                "batch_no": batch_no,
                "credit": 0.0,
                "commission": 0.0,
                "description": row_str[:135]
            }

        for n in numbers:
            if is_commission:
                # Commissions are negative or debit amounts
                batch_map[key]["commission"] = abs(n)
            else:
                # Deposits are positive amounts (exclude terminal IDs or batch numbers from amounts)
                if abs(n) > 0.01 and n != float(tid) and (not batch_no or n != float(batch_no)):
                    batch_map[key]["credit"] = abs(n)

    return list(batch_map.values())


def parse_text_lines(lines):
    rows = [[col.strip() for col in line.split() if col.strip()] for line in lines]
    return extract_mada_records_from_table(rows)

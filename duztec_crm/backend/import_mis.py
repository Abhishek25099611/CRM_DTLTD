"""One-time importer: MIS 2026-27.xlsx (Offer / Order sheets) -> CRM database as opening data."""
from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from . import db
from .config import LOGGER, SETTINGS

DATE_RE = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$")


def _date(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    m = DATE_RE.match(str(v or "").strip())
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return ""


def _num(v) -> float:
    try:
        f = float(str(v).replace(",", ""))
        return f if f == f else 0.0     # NaN -> 0
    except (TypeError, ValueError):
        return 0.0


def _status(prob: str) -> tuple[str, str]:
    p = str(prob or "").strip().lower()
    if p.startswith("won"):
        return "won", ""
    if p.startswith("lost") or p == "0":
        return "lost", "Marked LOST in MIS"
    if p.startswith("cold"):
        return "cold", ""
    return "sent", ""


def _find_header(df: pd.DataFrame, key: str) -> int:
    for i in range(min(10, len(df))):
        if key in [str(c).strip() for c in df.iloc[i].tolist()]:
            return i
    return -1


def _customer(con, name: str) -> int:
    name = re.sub(r"\s+", " ", str(name or "")).strip() or "(Unknown)"
    r = con.execute("SELECT id FROM customers WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    if r:
        return r["id"]
    cur = con.execute("INSERT INTO customers(name,created_at) VALUES(?,?)", (name, db.now()))
    return cur.lastrowid


def _contact(con, customer_id: int, blob: str) -> int | None:
    blob = str(blob or "").strip()
    if not blob:
        return None
    name = blob.splitlines()[0]
    name = re.sub(r"^(name|n)\s*:\s*", "", name, flags=re.I).strip()[:80] or blob[:80]
    phone = ""
    m = re.search(r"(?:\+?\d[\d \-]{8,})", blob)
    if m:
        phone = m.group(0).strip()
    r = con.execute("SELECT id FROM contacts WHERE customer_id=? AND name=? COLLATE NOCASE", (customer_id, name)).fetchone()
    if r:
        return r["id"]
    cur = con.execute("INSERT INTO contacts(customer_id,name,phone) VALUES(?,?,?)", (customer_id, name, phone))
    return cur.lastrowid


def run(force: bool = False) -> dict:
    db.init()
    con = db.connect()
    if con.execute("SELECT value FROM meta WHERE key='mis_imported'").fetchone() and not force:
        con.close()
        return {"skipped": True, "reason": "already imported"}
    path = SETTINGS.mis_file
    if not path.exists():
        con.close()
        return {"skipped": True, "reason": f"MIS file not found: {path}"}

    xl = pd.ExcelFile(path)
    off_sheet = next((s for s in xl.sheet_names if "offer" in s.lower()), None)
    ord_sheet = next((s for s in xl.sheet_names if "order" in s.lower()), None)
    n_q = n_o = 0

    if off_sheet:
        raw = pd.read_excel(path, sheet_name=off_sheet, header=None)
        h = _find_header(raw, "Offer no.")
        df = pd.read_excel(path, sheet_name=off_sheet, header=h)
        df = df[df["Offer no."].notna()]
        for _, r in df.iterrows():
            qno = str(r["Offer no."]).strip()
            if con.execute("SELECT 1 FROM quotations WHERE quote_no=?", (qno,)).fetchone():
                continue
            cid = _customer(con, r.get("Customer"))
            pid = _contact(con, cid, r.get("Contact Person Details"))
            status, reason = _status(r.get("Probability %"))
            cur = con.execute(
                """INSERT INTO quotations(quote_no,rev,customer_id,contact_id,date,status,lost_reason,
                   legacy_probability,month,type,notes,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (qno, "", cid, pid, _date(r.get("Date of offer")) or "2026-04-01", status, reason,
                 str(r.get("Probability %") or "").strip(), str(r.get("Month ") or r.get("Month") or "").strip(),
                 str(r.get("Type of offer") or "").strip(), "Imported from MIS 2026-27", db.now(), db.now()))
            qty = _num(r.get("Qty")) or 1
            rate = _num(r.get("Unit Price"))
            if not rate and _num(r.get("Total Price")):
                rate = _num(r.get("Total Price")) / qty
            con.execute("""INSERT INTO quotation_items(quotation_id,sr,description,qty,unit,rate,gst_pct)
                           VALUES(?,?,?,?,?,?,?)""",
                        (cur.lastrowid, 1, str(r.get("System Proposed") or "As per offer").strip(), qty, "Nos.", rate, 18))
            n_q += 1

    if ord_sheet:
        raw = pd.read_excel(path, sheet_name=ord_sheet, header=None)
        h = _find_header(raw, "Offer no.")
        df = pd.read_excel(path, sheet_name=ord_sheet, header=h)
        df = df[df["Offer no."].notna()]
        for _, r in df.iterrows():
            po_no = str(r.get("Purchase Order No.") or "").strip()
            so_no = str(r.get("Sales Order No") or "").strip()
            if so_no and con.execute("SELECT 1 FROM orders WHERE so_no=?", (so_no,)).fetchone():
                continue
            cid = _customer(con, r.get("Customer"))
            qref = str(r["Offer no."]).strip()
            q = con.execute("SELECT id FROM quotations WHERE quote_no=?", (qref,)).fetchone()
            if q:
                con.execute("UPDATE quotations SET status='won', updated_at=? WHERE id=?", (db.now(), q["id"]))
            con.execute("""INSERT INTO orders(quotation_id,customer_id,po_no,so_no,po_date,value,month,
                           responsible,system,payment_terms,delivery_date,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (q["id"] if q else None, cid, po_no, so_no, _date(r.get("PO Date")),
                         _num(r.get("PO Total Price")), str(r.get("Month ") or "").strip(),
                         str(r.get("Responsible") or "").strip(), str(r.get(" Application System") or "").strip(),
                         str(r.get("Payment Terms") or "").strip(), _date(r.get("PO Delivery date")), db.now()))
            n_o += 1

    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('mis_imported',?)", (db.now(),))
    db.log_activity(con, "system", None, "mis_import", f"{n_q} quotations, {n_o} orders from {path.name}")
    con.commit(); con.close()
    LOGGER.info("MIS import: %d quotations, %d orders", n_q, n_o)
    return {"skipped": False, "quotations": n_q, "orders": n_o}

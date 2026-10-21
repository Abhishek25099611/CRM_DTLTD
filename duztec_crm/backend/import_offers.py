"""Importer for an offer/quotation history spreadsheet -> CRM quotations.

Handles varied layouts (it matches columns by name and finds the header row even with blank rows
above), so it works for both the "Offer updation CRM" sheet (Quotation No / Date of Quotation /
Project Type / Value (INR) / sent / Assign) and the older "MIS 2025-26" sheet (Offer no. / Date of
offer / Probability % / Responsible / dated follow-up columns).

Safe on live data:
  * SKIPS any quotation number that already exists (never overwrites/duplicates a live quote),
  * --dry-run writes nothing,
  * --undo removes ONLY rows this/earlier offer-imports created (notes tag), NEVER the base import.

Usage (from the duztec_crm folder, venv active):
    python -m backend.import_offers "Offer updation CRM.xlsx" --dry-run
    python -m backend.import_offers "Offer updation CRM.xlsx"
    python -m backend.import_offers --undo --dry-run      # preview what a cleanup would remove
    python -m backend.import_offers --undo                # remove all prior offer-imports (not the base)
"""
from __future__ import annotations

import difflib
import re
import sys
from datetime import datetime

import pandas as pd

from . import db
from .config import LOGGER, SETTINGS

DEFAULT_SOURCE = "Imported from Offer updation CRM"
# Tags that --undo must NEVER remove (the original opening-data import that seeded the live quotes).
PROTECTED_TAGS = {"Imported from MIS 2026-27"}

# canonical field -> accepted header names (compared lowercased / stripped)
ALIASES = {
    "quote_no": ["quotation no", "offer no.", "offer no", "quote no", "quotation no."],
    "customer": ["customer"],
    "end_customer": ["end customers", "end customer"],
    "date": ["date of quotation", "date of offer", "date"],
    "system": ["system", "offer for application", "system proposed"],
    "ptype": ["project type", "type of offer", "category"],
    "value": ["value (inr)", "unit price", "value"],
    "qty": ["qty", "quantity"],
    "total": ["total amount (inr)", "total price", "total"],
    "status": ["sent", "status", "probability %"],
    "rkz": ["assign", "responsible"],
    "contact": ["contact person details"],
}
_DATE = re.compile(r"^\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\s*$")


def _d(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    m = _DATE.match(str(v or "").strip())
    if not m:
        return ""
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _num(v) -> float:
    try:
        f = float(str(v).replace(",", "").strip())
        return f if f == f else 0.0
    except (TypeError, ValueError):
        return 0.0


def _ptype(v) -> str:
    """Normalise the project type to a configured quotation type, fixing common typos; fallback Normal."""
    s = re.sub(r"\s+", " ", str(v or "").strip())
    low = s.lower()
    valid = list(SETTINGS.quotation_types) or ["Normal", "Tender", "Technical", "Budgetary", "Supporting", "Repeat Order"]
    for t in valid:
        if t.lower() == low:
            return t
    if low.startswith("tech"):
        return "Technical"
    if low.startswith(("norm", "niorm", "nomr", "nmor", "nor")):
        return "Normal"
    if low.startswith("budg"):
        return "Budgetary"
    if low.startswith("tend"):
        return "Tender"
    if low.startswith("supp"):
        return "Supporting"
    if "repeat" in low:
        return "Repeat Order"
    m = difflib.get_close_matches(s.title(), valid, n=1, cutoff=0.7)
    return m[0] if m else "Normal"


def _status(v) -> tuple[str, str]:
    s = str(v or "").strip().lower()
    if "won" in s or "order" in s:
        return "won", ""
    if s.startswith("lost"):
        return "lost", "Marked LOST in import"
    if s.startswith("cold"):
        return "cold", ""
    try:
        n = float(s)
        if n >= 100:
            return "won", ""
        if n <= 0:
            return "lost", "Marked LOST in import"
        return "sent", ""
    except ValueError:
        pass
    return "sent", ""   # e.g. the "sent" column in the Offer-updation sheet


def _contact(con, cid: int, blob: str):
    blob = str(blob or "").strip()
    if not blob or blob.lower() == "nan":
        return None
    name = re.sub(r"^(name|n)\s*:\s*", "", blob.splitlines()[0], flags=re.I).strip()[:80] or blob[:80]
    phone = (re.search(r"(?:\+?\d[\d \-]{8,})", blob) or [None])
    phone = phone.group(0).strip() if hasattr(phone, "group") else ""
    r = con.execute("SELECT id FROM contacts WHERE customer_id=? AND name=? COLLATE NOCASE", (cid, name)).fetchone()
    if r:
        return r["id"]
    return con.execute("INSERT INTO contacts(customer_id,name,phone) VALUES(?,?,?)", (cid, name, phone)).lastrowid


def _customer(con, name: str) -> int:
    name = re.sub(r"\s+", " ", str(name or "")).strip() or "(Unknown)"
    r = con.execute("SELECT id FROM customers WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    if r:
        return r["id"]
    return con.execute("INSERT INTO customers(name,created_at) VALUES(?,?)", (name, db.now())).lastrowid


def _load(path: str):
    """Return (sheet, dataframe, column-map, dated-follow-up-columns)."""
    xl = pd.ExcelFile(path)
    for sheet in xl.sheet_names:
        raw = pd.read_excel(path, sheet_name=sheet, header=None)
        for hrow in range(min(10, len(raw))):
            names = [str(c).strip().lower() for c in raw.iloc[hrow].tolist()]
            if any(a in names for a in ALIASES["quote_no"]):
                df = pd.read_excel(path, sheet_name=sheet, header=hrow)
                df.columns = [str(c).strip() for c in df.columns]
                lower = {c.lower(): c for c in df.columns}
                cmap = {canon: next((lower[a] for a in al if a in lower), None) for canon, al in ALIASES.items()}
                dated = [c for c in df.columns if _DATE.match(str(c))]
                return sheet, df, cmap, dated
    raise ValueError("Could not find a header row with a 'Quotation No' / 'Offer no.' column in any sheet.")


def run(path: str, source: str = DEFAULT_SOURCE, dry_run: bool = False) -> dict:
    sheet, df, c, dated = _load(path)
    if not c["quote_no"]:
        raise ValueError("No quotation-number column found.")
    con = db.connect()
    seen: set[str] = set()
    created = skipped = followups = 0
    ex_new, ex_skip = [], []
    g = lambda r, k: r.get(c[k]) if c[k] else None

    for _, r in df.iterrows():
        qno = re.sub(r"\s+", " ", str(g(r, "quote_no") or "").strip())
        if not qno or qno.lower() == "nan":
            continue
        if con.execute("SELECT 1 FROM quotations WHERE quote_no=? COLLATE NOCASE", (qno,)).fetchone() or qno.lower() in seen:
            skipped += 1
            if len(ex_skip) < 8:
                ex_skip.append(qno)
            continue
        seen.add(qno.lower())
        status, reason = _status(g(r, "status"))
        ptype = _ptype(g(r, "ptype"))
        cid = _customer(con, g(r, "customer"))
        pid = _contact(con, cid, g(r, "contact")) if c["contact"] else None
        date = _d(g(r, "date")) or "2025-04-01"
        rkz = str(g(r, "rkz") or "").strip().upper()
        endc = re.sub(r"\s+", " ", str(g(r, "end_customer") or "").strip())
        endc = "" if endc.lower() == "nan" else endc
        system = re.sub(r"\s+", " ", str(g(r, "system") or "").strip())
        qty = _num(g(r, "qty")) or 1
        rate = _num(g(r, "value")) or (_num(g(r, "total")) / qty if _num(g(r, "total")) else 0)
        if len(ex_new) < 8:
            ex_new.append(f"{qno} [{status}/{ptype}] {str(g(r, 'customer') or '')[:20]}")
        row_fu = sum(1 for d in dated if str(r.get(d) or "").strip() and str(r.get(d)).strip().lower() != "nan")
        if dry_run:
            created += 1
            followups += row_fu
            continue
        cur = con.execute(
            """INSERT INTO quotations(quote_no,rev,customer_id,contact_id,date,status,lost_reason,
               salesperson,month,type,end_customer,notes,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (qno, "", cid, pid, date, status, reason, rkz, "", ptype, endc, source, db.now(), db.now()))
        qid = cur.lastrowid
        con.execute("""INSERT INTO quotation_items(quotation_id,sr,description,qty,unit,rate,gst_pct)
                       VALUES(?,?,?,?,?,?,?)""", (qid, 1, system or "As per offer", qty, "Nos.", rate, 18))
        for d in dated:
            note = str(r.get(d) or "").strip()
            if note and note.lower() != "nan":
                con.execute("""INSERT INTO followups(entity_type,entity_id,due_date,channel,note,done,created_at)
                               VALUES('quotation',?,?,?,?,1,?)""", (qid, _d(d) or date, "Offer update", note, db.now()))
                followups += 1
        created += 1

    if not dry_run:
        con.commit()
        LOGGER.info("Offer import (%s): created %d quotation(s), %d follow-up(s), skipped %d existing",
                    source, created, followups, skipped)
    con.close()
    return {"dry_run": dry_run, "sheet": sheet, "source": source, "created": created,
            "skipped_existing": skipped, "followups": followups, "new_examples": ex_new, "skipped_examples": ex_skip,
            "column_map": {k: v for k, v in c.items() if v}}


def undo(dry_run: bool = False) -> dict:
    """Remove every quotation created by an offer-import (its notes tag starts with 'Imported from '),
    EXCEPT the protected base import, plus their line items and follow-ups. Hand-entered quotes (no such
    tag) are untouched."""
    con = db.connect()
    marks = ",".join("?" * len(PROTECTED_TAGS))
    rows = con.execute(
        f"SELECT id, notes FROM quotations WHERE notes LIKE 'Imported from %' AND notes NOT IN ({marks})",
        tuple(PROTECTED_TAGS)).fetchall()
    ids = [r["id"] for r in rows]
    by_tag: dict[str, int] = {}
    for r in rows:
        by_tag[r["notes"]] = by_tag.get(r["notes"], 0) + 1
    if not dry_run and ids:
        m = ",".join("?" * len(ids))
        con.execute(f"DELETE FROM followups WHERE entity_type='quotation' AND entity_id IN ({m})", ids)
        con.execute(f"DELETE FROM quotation_items WHERE quotation_id IN ({m})", ids)
        con.execute(f"DELETE FROM orders WHERE quotation_id IN ({m})", ids)
        con.execute(f"DELETE FROM quotations WHERE id IN ({m})", ids)
        con.execute("DELETE FROM meta WHERE key IN ('mis_2025_imported')")
        db.log_activity(con, "quotation", None, "offer_import_undone", f"{len(ids)} imported quotation(s)")
        con.commit()
        LOGGER.info("Undid offer imports: removed %d quotation(s) — %s", len(ids), by_tag)
    con.close()
    return {"dry_run": dry_run, "quotations": len(ids), "by_tag": by_tag, "protected": sorted(PROTECTED_TAGS)}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    dry = "--dry-run" in flags
    if "--undo" in flags:
        u = undo(dry_run=dry)
        print("Offer import undo —", "DRY RUN (nothing written)" if dry else "DONE")
        print(f"  {'would remove' if dry else 'removed'}: {u['quotations']} quotation(s)")
        for tag, n in u["by_tag"].items():
            print(f"      {n:4}  {tag}")
        print(f"  protected (never removed): {', '.join(u['protected'])}")
        return 0
    if not args:
        print('Usage: python -m backend.import_offers "<file.xlsx>" [--dry-run]')
        print('       python -m backend.import_offers --undo [--dry-run]')
        return 2
    res = run(args[0], dry_run=dry)
    print("Offer import —", "DRY RUN (nothing written)" if dry else "DONE")
    print(f"  sheet            : {res['sheet']}")
    print(f"  mapped columns   : {res['column_map']}")
    print(f"  {'would create' if dry else 'created':<16} : {res['created']}")
    print(f"  skipped (exists) : {res['skipped_existing']}")
    print(f"  follow-ups       : {res['followups']}")
    if res["new_examples"]:
        print("  new examples     :", "; ".join(res["new_examples"]))
    if res["skipped_examples"]:
        print("  skipped examples :", ", ".join(res["skipped_examples"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

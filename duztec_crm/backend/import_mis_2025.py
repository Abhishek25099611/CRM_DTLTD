"""One-time importer for a historical MIS "Offer YYYY-YY" workbook (e.g. MIS 2025-26.xlsx).

Each row is one offer -> a quotation (+ one line item + the dated status columns as follow-ups).
Safe to run against live data:
  * it SKIPS any offer number that already exists (never overwrites or duplicates a live quotation),
  * --dry-run previews counts and writes nothing,
  * a meta flag makes a real run one-time (re-running does nothing unless --force).

Usage (from the duztec_crm folder, venv active):
    python -m backend.import_mis_2025 "MIS 2025-26.xlsx" --dry-run
    python -m backend.import_mis_2025 "MIS 2025-26.xlsx"
"""
from __future__ import annotations

import re
import sys
from datetime import datetime

import pandas as pd

from . import db
from .config import LOGGER
from .import_mis import _contact, _customer, _num

META_KEY = "mis_2025_imported"
SOURCE = "Imported from MIS 2025-26"
_DATE_COL = re.compile(r"^\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\s*$")


def _d(v) -> str:
    """Parse a date that may be a datetime, dd.mm.yyyy or dd.mm.yy -> YYYY-MM-DD ('' if unparseable)."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    m = _DATE_COL.match(str(v or "").strip())
    if not m:
        return ""
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _status(prob) -> tuple[str, str]:
    """100% (or 'won'/'order') -> won; 0% (or 'lost') -> lost; anything else -> sent (open)."""
    s = str(prob or "").strip().lower()
    if "won" in s or "order" in s:
        return "won", ""
    if s.startswith("lost"):
        return "lost", "Marked LOST in MIS 2025-26"
    if s.startswith("cold"):
        return "cold", ""
    n = _num(prob)
    if n >= 100:
        return "won", ""
    if n <= 0 and s in ("0", "0.0", "0%", "nan", ""):
        # only treat a genuine 0 as lost; a blank probability stays 'sent'
        return ("lost", "Marked LOST in MIS 2025-26") if s in ("0", "0.0", "0%") else ("sent", "")
    return "sent", ""


def run(path: str, dry_run: bool = False, force: bool = False) -> dict:
    xl = pd.ExcelFile(path)
    sheet = next((s for s in xl.sheet_names if "offer" in s.lower()), xl.sheet_names[0])
    # header is the row carrying "Offer no."
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    hrow = next((i for i in range(min(8, len(raw)))
                 if "Offer no." in [str(c).strip() for c in raw.iloc[i].tolist()]), 0)
    df = pd.read_excel(path, sheet_name=sheet, header=hrow)
    df.columns = [str(c).strip() for c in df.columns]
    dated_cols = [c for c in df.columns if _DATE_COL.match(str(c))]

    con = db.connect()
    done_before = con.execute("SELECT value FROM meta WHERE key=?", (META_KEY,)).fetchone()
    if done_before and not force and not dry_run:
        con.close()
        return {"skipped": True, "reason": f"already imported ({done_before['value']}); use --force to repeat"}

    seen: set[str] = set()
    created, skipped, followups = 0, 0, 0
    examples_new, examples_skip = [], []

    for _, r in df.iterrows():
        qno = re.sub(r"\s+", " ", str(r.get("Offer no.") or "").strip())
        if not qno or qno.lower() == "nan":
            continue
        exists = con.execute("SELECT 1 FROM quotations WHERE quote_no=? COLLATE NOCASE", (qno,)).fetchone()
        if exists or qno.lower() in seen:
            skipped += 1
            if len(examples_skip) < 8:
                examples_skip.append(qno)
            continue
        seen.add(qno.lower())
        status, reason = _status(r.get("Probability %"))
        cid = _customer(con, r.get("Customer"))
        pid = _contact(con, cid, r.get("Contact Person Details"))
        date = _d(r.get("Date of offer")) or "2025-04-01"
        rkz = str(r.get("Responsible") or "").strip().upper()
        system = re.sub(r"\s+", " ", str(r.get("offer for Application") or r.get("System Proposed") or "").strip())
        qty = _num(r.get("Qty")) or 1
        rate = _num(r.get("Unit Price")) or (_num(r.get("Total Price")) / qty if _num(r.get("Total Price")) else 0)
        if len(examples_new) < 8:
            examples_new.append(f"{qno} [{status}] {str(r.get('Customer') or '')[:22]}")
        if dry_run:
            created += 1
            followups += sum(1 for c in dated_cols if str(r.get(c) or "").strip() and str(r.get(c)).strip().lower() != "nan")
            continue
        cur = con.execute(
            """INSERT INTO quotations(quote_no,rev,customer_id,contact_id,date,status,lost_reason,
               salesperson,month,type,notes,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (qno, "", cid, pid, date, status, reason, rkz,
             str(r.get("Month ") or r.get("Month") or "").strip(), "", SOURCE, db.now(), db.now()))
        qid = cur.lastrowid
        con.execute("""INSERT INTO quotation_items(quotation_id,sr,description,qty,unit,rate,gst_pct)
                       VALUES(?,?,?,?,?,?,?)""",
                    (qid, 1, system or "As per offer", qty, "Nos.", rate, 18))
        for c in dated_cols:
            note = str(r.get(c) or "").strip()
            if not note or note.lower() == "nan":
                continue
            con.execute("""INSERT INTO followups(entity_type,entity_id,due_date,channel,note,done,created_at)
                           VALUES('quotation',?,?,?,?,1,?)""",
                        (qid, _d(c) or date, "MIS update", note, db.now()))
            followups += 1
        created += 1

    result = {"dry_run": dry_run, "sheet": sheet, "created": created, "skipped_existing": skipped,
              "followups": followups, "new_examples": examples_new, "skipped_examples": examples_skip}
    if not dry_run:
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (META_KEY, db.now()))
        con.commit()
        LOGGER.info("MIS 2025-26 import: created %d quotation(s), %d follow-up(s), skipped %d existing",
                    created, followups, skipped)
    con.close()
    return result


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print('Usage: python -m backend.import_mis_2025 "MIS 2025-26.xlsx" [--dry-run] [--force]')
        return 2
    res = run(args[0], dry_run="--dry-run" in flags, force="--force" in flags)
    print("MIS 2025-26 import —", "DRY RUN (nothing written)" if res.get("dry_run") else "DONE")
    if res.get("skipped"):
        print("  ", res["reason"]); return 0
    print(f"  sheet            : {res['sheet']}")
    print(f"  would create     : {res['created']}" if res["dry_run"] else f"  created          : {res['created']}")
    print(f"  skipped (exists) : {res['skipped_existing']}")
    print(f"  follow-ups       : {res['followups']}")
    if res["new_examples"]:
        print("  new examples     :", "; ".join(res["new_examples"]))
    if res["skipped_examples"]:
        print("  skipped examples :", ", ".join(res["skipped_examples"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

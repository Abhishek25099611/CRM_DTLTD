"""SQLite schema + helpers. One file DB, WAL mode, nightly-copy friendly."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from typing import Any

from .config import LOGGER, SETTINGS

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, gstin TEXT DEFAULT '', address TEXT DEFAULT '',
  state TEXT DEFAULT '', pincode TEXT DEFAULT '', segment TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS contacts(
  id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
  name TEXT NOT NULL, phone TEXT DEFAULT '', email TEXT DEFAULT '', role TEXT DEFAULT '',
  designation TEXT DEFAULT '', department TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS enquiries(
  id INTEGER PRIMARY KEY, enq_no TEXT NOT NULL UNIQUE, date TEXT NOT NULL, source TEXT DEFAULT '',
  customer_id INTEGER NOT NULL REFERENCES customers(id), contact_id INTEGER REFERENCES contacts(id),
  requirement TEXT DEFAULT '', system TEXT DEFAULT '', expected_value REAL DEFAULT 0,
  salesperson TEXT DEFAULT '', priority TEXT DEFAULT 'Normal',
  status TEXT NOT NULL DEFAULT 'new',   -- new/qualified/quoted/won/lost/dropped
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quotations(
  id INTEGER PRIMARY KEY, quote_no TEXT NOT NULL, rev TEXT NOT NULL DEFAULT '',
  enquiry_id INTEGER REFERENCES enquiries(id), customer_id INTEGER NOT NULL REFERENCES customers(id),
  contact_id INTEGER REFERENCES contacts(id), date TEXT NOT NULL,
  validity_days INTEGER DEFAULT 30, delivery_terms TEXT DEFAULT '', payment_terms TEXT DEFAULT '',
  notes TEXT DEFAULT '', gst_mode TEXT DEFAULT 'intra',  -- intra => CGST+SGST, inter => IGST
  discount_pct REAL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft', -- draft/sent/won/lost/cold/superseded
  lost_reason TEXT DEFAULT '', salesperson TEXT DEFAULT '',
  legacy_probability TEXT DEFAULT '', month TEXT DEFAULT '', type TEXT DEFAULT '',
  introduction TEXT DEFAULT '', scope TEXT DEFAULT '', warranty TEXT DEFAULT '', guarantee TEXT DEFAULT '',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(quote_no, rev));
CREATE TABLE IF NOT EXISTS quotation_items(
  id INTEGER PRIMARY KEY, quotation_id INTEGER NOT NULL REFERENCES quotations(id) ON DELETE CASCADE,
  sr INTEGER NOT NULL, description TEXT NOT NULL, hsn TEXT DEFAULT '', qty REAL DEFAULT 1,
  unit TEXT DEFAULT 'Nos.', rate REAL DEFAULT 0, gst_pct REAL DEFAULT 18);
CREATE TABLE IF NOT EXISTS followups(
  id INTEGER PRIMARY KEY, entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL,
  due_date TEXT NOT NULL, channel TEXT DEFAULT 'Call', note TEXT DEFAULT '',
  done INTEGER NOT NULL DEFAULT 0, outcome TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY, quotation_id INTEGER REFERENCES quotations(id),
  customer_id INTEGER NOT NULL REFERENCES customers(id), po_no TEXT DEFAULT '', so_no TEXT DEFAULT '',
  po_date TEXT DEFAULT '', value REAL DEFAULT 0, month TEXT DEFAULT '',
  responsible TEXT DEFAULT '', system TEXT DEFAULT '', payment_terms TEXT DEFAULT '',
  delivery_date TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activity(
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id INTEGER,
  action TEXT NOT NULL, detail TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY, entity_type TEXT NOT NULL,   -- customer / enquiry / quotation / order
  entity_id INTEGER NOT NULL, category TEXT DEFAULT '', filename TEXT NOT NULL,
  stored_name TEXT NOT NULL, size INTEGER DEFAULT 0, mime TEXT DEFAULT '', note TEXT DEFAULT '',
  uploaded_by TEXT DEFAULT '', uploaded_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_documents_entity ON documents(entity_type, entity_id);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, hsn TEXT DEFAULT '',
  unit TEXT DEFAULT 'Nos.', rate REAL DEFAULT 0, specification TEXT DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS targets(
  id INTEGER PRIMARY KEY, email TEXT NOT NULL, rkz TEXT DEFAULT '',
  measure TEXT NOT NULL DEFAULT 'order_value',        -- order_value / order_count / quotation_value / quotation_count / enquiry_count
  period_type TEXT NOT NULL DEFAULT 'monthly',        -- monthly / quarterly / yearly
  period_start TEXT NOT NULL, period_end TEXT NOT NULL, amount REAL NOT NULL DEFAULT 0,
  note TEXT DEFAULT '', created_by TEXT DEFAULT '', created_at TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect() -> sqlite3.Connection:
    SETTINGS.db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(SETTINGS.db)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


# Columns added after the first release; applied idempotently at startup so `git pull` + restart migrates.
MIGRATIONS = [
    ("customers", "pincode", "TEXT DEFAULT ''"),
    ("contacts", "designation", "TEXT DEFAULT ''"),
    ("contacts", "department", "TEXT DEFAULT ''"),
    ("quotations", "introduction", "TEXT DEFAULT ''"),
    ("quotations", "scope", "TEXT DEFAULT ''"),
    ("quotations", "warranty", "TEXT DEFAULT ''"),
    ("quotations", "guarantee", "TEXT DEFAULT ''"),
    ("quotations", "sent_at", "TEXT DEFAULT ''"),        # first time the quotation was marked Sent (48-h SLA)
    ("customers", "end_customer", "TEXT DEFAULT ''"),    # e.g. LIPL supplying JSW Dolvi
    ("users", "last_seen", "TEXT DEFAULT ''"),           # browser heartbeat for Active / Idle / Out
    ("quotation_items", "product_id", "INTEGER"),        # link to the Products master (specifications on print)
]


def seed_products() -> int:
    """Insert the config product list once, only while the master is empty."""
    con = connect()
    if con.execute("SELECT COUNT(*) FROM products").fetchone()[0] or not SETTINGS.products_seed:
        con.close(); return 0
    n = 0
    for p in SETTINGS.products_seed:
        code = str(p.get("code", "")).strip().upper()
        if not code:
            continue
        con.execute("""INSERT OR IGNORE INTO products(code,name,hsn,unit,rate,specification,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (code, str(p.get("name") or code), str(p.get("hsn") or ""), str(p.get("unit") or "Nos."),
                     float(p.get("rate") or 0), str(p.get("specification") or ""), now()))
        n += 1
    con.commit(); con.close()
    LOGGER.info("Seeded %d products from config", n)
    return n


def init() -> None:
    con = connect()
    con.executescript(SCHEMA)
    for table, col, ddl in MIGRATIONS:
        if col not in [r[1] for r in con.execute(f"PRAGMA table_info({table})")]:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            LOGGER.info("Migration: added %s.%s", table, col)
    con.commit(); con.close()


def rows(cur) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def log_activity(con, entity_type: str, entity_id: int | None, action: str, detail: str = "") -> None:
    con.execute("INSERT INTO activity(at,entity_type,entity_id,action,detail) VALUES(?,?,?,?,?)",
                (now(), entity_type, entity_id, action, detail[:500]))


def next_enq_no(con) -> str:
    pre = SETTINGS.numbering.get("enquiry_prefix", "ENQ-")
    r = con.execute("SELECT enq_no FROM enquiries WHERE enq_no LIKE ? ORDER BY id DESC LIMIT 1", (pre + "%",)).fetchone()
    n = int(r["enq_no"][len(pre):]) + 1 if r and r["enq_no"][len(pre):].isdigit() else 1
    return f"{pre}{n:03d}"


def next_quote_no(con) -> str:
    pre = SETTINGS.numbering.get("quote_prefix", "Q")
    pad = int(SETTINGS.numbering.get("quote_pad", 5))
    best = 0
    for r in con.execute("SELECT quote_no FROM quotations WHERE quote_no LIKE ?", (pre + "%",)):
        tail = r["quote_no"][len(pre):]
        if tail.isdigit():
            best = max(best, int(tail))
    return f"{pre}{best + 1:0{pad}d}"


def guess_state(name: str) -> str:
    low = str(name or "").lower()
    for kw, st in SETTINGS.state_keywords.items():
        if kw in low:
            return st
    return ""


import re as _re

_PIN_RE = _re.compile(r"\b([1-8]\d{5})\b")


def guess_pincode(name: str, address: str = "") -> str:
    m = _PIN_RE.search(str(address or ""))
    if m:
        return m.group(1)
    low = str(name or "").lower()
    for kw, pin in SETTINGS.pincode_keywords.items():
        if kw in low:
            return pin
    return ""


def backfill_states() -> int:
    """Fill blank customer states/pincodes from name keywords (per startup; manual edits win)."""
    con = connect()
    n = p = 0
    for r in con.execute("SELECT id, name FROM customers WHERE state='' OR state IS NULL"):
        st = guess_state(r["name"])
        if st:
            con.execute("UPDATE customers SET state=? WHERE id=?", (st, r["id"]))
            n += 1
    for r in con.execute("SELECT id, name, address FROM customers WHERE pincode='' OR pincode IS NULL"):
        pin = guess_pincode(r["name"], r["address"])
        if pin:
            con.execute("UPDATE customers SET pincode=? WHERE id=?", (pin, r["id"]))
            p += 1
    con.commit(); con.close()
    if n or p:
        LOGGER.info("Backfilled state for %d and pincode for %d customers", n, p)
    return n + p


def backup() -> str:
    SETTINGS.backup.mkdir(parents=True, exist_ok=True)
    dst = SETTINGS.backup / f"crm_{datetime.now():%Y%m%d_%H%M%S}.db"
    con = connect()
    bck = sqlite3.connect(dst)
    con.backup(bck)
    bck.close(); con.close()
    LOGGER.info("Backup written: %s", dst)
    return str(dst)

"""Enquiries: punch-in, kanban statuses."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from . import auth, db, print_quote
from .config import LOGGER, SETTINGS
from .schemas import (AssignRkzIn, ContactIn, CustomerIn, EnquiryIn, FollowupIn, ItemIn, QuotationIn, StatusIn)
from .services import _check_quote_access, _geo_state, _q_totals, _quote_row, _scope

router = APIRouter()

@router.get("/api/enquiries")
def enquiries(request: Request, status: str = "", customer_id: int | None = None):
    sc = _scope(request)
    con = db.connect()
    sql = """SELECT e.*, c.name customer, ct.name contact,
             (SELECT COUNT(*) FROM quotations q WHERE q.enquiry_id=e.id AND q.status!='superseded') quote_count,
             (SELECT MIN(due_date) FROM followups f WHERE f.entity_type='enquiry' AND f.entity_id=e.id AND f.done=0) next_followup
             FROM enquiries e JOIN customers c ON c.id=e.customer_id
             LEFT JOIN contacts ct ON ct.id=e.contact_id WHERE 1=1"""
    args: list = []
    if sc:
        sql += " AND e.salesperson=?"; args.append(sc)
    if status:
        sql += " AND e.status=?"; args.append(status)
    if customer_id:
        sql += " AND e.customer_id=?"; args.append(customer_id)
    out = db.rows(con.execute(sql + " ORDER BY e.id DESC", args))
    con.close()
    return out


@router.post("/api/enquiries")
def add_enquiry(e: EnquiryIn, request: Request):
    sc = _scope(request)
    if sc:
        if sc == "__UNASSIGNED__":
            raise HTTPException(403, {"error_type": "no_rkz", "detail": "You have no RKZ code yet — ask an admin to assign one in the Users tab."})
        e.salesperson = sc
    con = db.connect()
    dup = con.execute("""SELECT enq_no FROM enquiries WHERE customer_id=? AND system=? COLLATE NOCASE
                         AND date >= date('now','-60 day')""", (e.customer_id, e.system.strip())).fetchone()
    no = db.next_enq_no(con)
    cur = con.execute("""INSERT INTO enquiries(enq_no,date,source,customer_id,contact_id,requirement,system,
                         expected_value,salesperson,priority,status,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?, 'new', ?, ?)""",
                      (no, e.date or date.today().isoformat(), e.source, e.customer_id, e.contact_id,
                       e.requirement, e.system.strip(), e.expected_value, e.salesperson, e.priority,
                       db.now(), db.now()))
    db.log_activity(con, "enquiry", cur.lastrowid, "created", f"{no} · {e.system}")
    con.commit(); nid = cur.lastrowid; con.close()
    return {"id": nid, "enq_no": no,
            "duplicate_warning": f"Similar enquiry {dup['enq_no']} exists for this customer in the last 60 days" if dup else ""}


@router.post("/api/enquiries/{eid}/status")
def enquiry_status(eid: int, s: StatusIn):
    if s.status not in ("new", "qualified", "quoted", "won", "lost", "dropped"):
        raise HTTPException(422, {"error_type": "bad_status", "detail": s.status})
    con = db.connect()
    con.execute("UPDATE enquiries SET status=?, updated_at=? WHERE id=?", (s.status, db.now(), eid))
    db.log_activity(con, "enquiry", eid, "status", s.status + (" · " + s.reason if s.reason else ""))
    con.commit(); con.close()
    return {"ok": True}

"""Quotations: builder, revisions, statuses, letterhead print."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from . import auth, db, print_quote
from .config import LOGGER, SETTINGS
from .schemas import (AssignRkzIn, ContactIn, CustomerIn, EnquiryIn, FollowupIn, ItemIn, QuotationIn, StatusIn)
from .services import _check_quote_access, _geo_state, _q_totals, _quote_row, _scope

router = APIRouter()

@router.get("/api/quotations")
def quotations(request: Request, status: str = "", customer_id: int | None = None):
    sc = _scope(request)
    con = db.connect()
    sql = """SELECT q.*, c.name customer, ct.name contact FROM quotations q
             JOIN customers c ON c.id=q.customer_id LEFT JOIN contacts ct ON ct.id=q.contact_id
             WHERE q.status!='superseded'"""
    args: list = []
    if sc:
        sql += " AND q.salesperson=?"; args.append(sc)
    if status:
        sql += " AND q.status=?"; args.append(status)
    if customer_id:
        sql += " AND q.customer_id=?"; args.append(customer_id)
    out = [_quote_row(con, r) for r in db.rows(con.execute(sql + " ORDER BY q.id DESC", args))]
    con.close()
    return out


@router.get("/api/quotations/{qid}")
def quotation(qid: int, request: Request):
    con = db.connect()
    r = con.execute("""SELECT q.*, c.name customer, ct.name contact FROM quotations q
                       JOIN customers c ON c.id=q.customer_id LEFT JOIN contacts ct ON ct.id=q.contact_id
                       WHERE q.id=?""", (qid,)).fetchone()
    if not r:
        con.close()
        raise HTTPException(404, {"error_type": "not_found", "detail": f"quotation {qid}"})
    _check_quote_access(request, r)
    out = _quote_row(con, dict(r))
    out["items"] = db.rows(con.execute("SELECT * FROM quotation_items WHERE quotation_id=? ORDER BY sr", (qid,)))
    con.close()
    return out


def _save_items(con, qid: int, items: list[ItemIn]):
    con.execute("DELETE FROM quotation_items WHERE quotation_id=?", (qid,))
    for i, it in enumerate(items, 1):
        con.execute("""INSERT INTO quotation_items(quotation_id,sr,description,hsn,qty,unit,rate,gst_pct)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (qid, i, it.description.strip(), it.hsn, it.qty, it.unit, it.rate, it.gst_pct))


@router.post("/api/quotations")
def add_quotation(q: QuotationIn, request: Request):
    sc = _scope(request)
    if sc:
        if sc == "__UNASSIGNED__":
            raise HTTPException(403, {"error_type": "no_rkz", "detail": "You have no RKZ code yet — ask an admin to assign one in the Users tab."})
        q.salesperson = sc
    d = SETTINGS.quotation_defaults
    con = db.connect()
    no = db.next_quote_no(con)
    cur = con.execute("""INSERT INTO quotations(quote_no,rev,enquiry_id,customer_id,contact_id,date,validity_days,
                         delivery_terms,payment_terms,notes,gst_mode,discount_pct,salesperson,status,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?, 'draft', ?, ?)""",
                      (no, "", q.enquiry_id, q.customer_id, q.contact_id, q.date or date.today().isoformat(),
                       q.validity_days or int(d.get("validity_days", 30)),
                       q.delivery_terms or d.get("delivery_terms", ""), q.payment_terms or d.get("payment_terms", ""),
                       q.notes or d.get("notes", ""), q.gst_mode, q.discount_pct, q.salesperson, db.now(), db.now()))
    qid = cur.lastrowid
    _save_items(con, qid, q.items)
    if q.enquiry_id:
        con.execute("UPDATE enquiries SET status='quoted', updated_at=? WHERE id=?", (db.now(), q.enquiry_id))
    db.log_activity(con, "quotation", qid, "created", no)
    con.commit(); con.close()
    return {"id": qid, "quote_no": no}


@router.put("/api/quotations/{qid}")
def edit_quotation(qid: int, q: QuotationIn, request: Request):
    sc = _scope(request)
    con = db.connect()
    ex = con.execute("SELECT status, salesperson FROM quotations WHERE id=?", (qid,)).fetchone()
    if ex:
        _check_quote_access(request, ex)
    if sc:
        q.salesperson = sc
    if not ex:
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"quotation {qid}"})
    if ex["status"] not in ("draft", "sent"):
        con.close(); raise HTTPException(422, {"error_type": "locked", "detail": f"Cannot edit a {ex['status']} quotation — create a revision instead"})
    con.execute("""UPDATE quotations SET customer_id=?,contact_id=?,date=?,validity_days=?,delivery_terms=?,
                   payment_terms=?,notes=?,gst_mode=?,discount_pct=?,salesperson=?,updated_at=? WHERE id=?""",
                (q.customer_id, q.contact_id, q.date or date.today().isoformat(), q.validity_days,
                 q.delivery_terms, q.payment_terms, q.notes, q.gst_mode, q.discount_pct, q.salesperson, db.now(), qid))
    _save_items(con, qid, q.items)
    db.log_activity(con, "quotation", qid, "edited", "")
    con.commit(); con.close()
    return {"ok": True}


@router.post("/api/quotations/{qid}/revise")
def revise(qid: int, request: Request):
    con = db.connect()
    r = con.execute("SELECT * FROM quotations WHERE id=?", (qid,)).fetchone()
    if not r:
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"quotation {qid}"})
    _check_quote_access(request, r)
    rev = chr(ord(r["rev"]) + 1) if r["rev"] else "B"
    cur = con.execute("""INSERT INTO quotations(quote_no,rev,enquiry_id,customer_id,contact_id,date,validity_days,
                         delivery_terms,payment_terms,notes,gst_mode,discount_pct,salesperson,status,created_at,updated_at)
                         SELECT quote_no,?,enquiry_id,customer_id,contact_id,?,validity_days,delivery_terms,
                         payment_terms,notes,gst_mode,discount_pct,salesperson,'draft',?,? FROM quotations WHERE id=?""",
                      (rev, date.today().isoformat(), db.now(), db.now(), qid))
    nid = cur.lastrowid
    con.execute("""INSERT INTO quotation_items(quotation_id,sr,description,hsn,qty,unit,rate,gst_pct)
                   SELECT ?,sr,description,hsn,qty,unit,rate,gst_pct FROM quotation_items WHERE quotation_id=?""",
                (nid, qid))
    con.execute("UPDATE quotations SET status='superseded', updated_at=? WHERE id=?", (db.now(), qid))
    db.log_activity(con, "quotation", nid, "revised", f"{r['quote_no']}-{rev}")
    con.commit(); con.close()
    return {"id": nid, "rev": rev}


@router.post("/api/quotations/{qid}/status")
def quote_status(qid: int, s: StatusIn, request: Request):
    if s.status not in ("draft", "sent", "won", "lost", "cold"):
        raise HTTPException(422, {"error_type": "bad_status", "detail": s.status})
    con = db.connect()
    r = con.execute("SELECT * FROM quotations WHERE id=?", (qid,)).fetchone()
    if not r:
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"quotation {qid}"})
    _check_quote_access(request, r)
    if s.status == "lost" and not s.reason.strip():
        con.close(); raise HTTPException(422, {"error_type": "reason_required", "detail": "A lost reason is required"})
    con.execute("UPDATE quotations SET status=?, lost_reason=?, updated_at=? WHERE id=?",
                (s.status, s.reason if s.status == "lost" else r["lost_reason"], db.now(), qid))
    order_id = None
    if s.status == "won":
        t = _q_totals(con, qid)
        cur = con.execute("""INSERT INTO orders(quotation_id,customer_id,po_no,po_date,value,month,responsible,created_at)
                             VALUES(?,?,?,?,?,?,?,?)""",
                          (qid, r["customer_id"], s.po_no, s.po_date or date.today().isoformat(),
                           s.value or t["total"], date.today().strftime("%B"), (r["salesperson"] or "").upper(), db.now()))
        order_id = cur.lastrowid
        if r["enquiry_id"]:
            con.execute("UPDATE enquiries SET status='won', updated_at=? WHERE id=?", (db.now(), r["enquiry_id"]))
    if s.status == "lost" and r["enquiry_id"]:
        con.execute("UPDATE enquiries SET status='lost', updated_at=? WHERE id=?", (db.now(), r["enquiry_id"]))
    db.log_activity(con, "quotation", qid, "status", f"{s.status}" + (f" · {s.reason}" if s.reason else ""))
    con.commit(); con.close()
    return {"ok": True, "order_id": order_id}


@router.get("/api/quotations/{qid}/print", response_class=HTMLResponse)
def print_quotation(qid: int, request: Request):
    con = db.connect()
    q = con.execute("SELECT * FROM quotations WHERE id=?", (qid,)).fetchone()
    if not q:
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"quotation {qid}"})
    _check_quote_access(request, q)
    items = db.rows(con.execute("SELECT * FROM quotation_items WHERE quotation_id=? ORDER BY sr", (qid,)))
    cust = dict(con.execute("SELECT * FROM customers WHERE id=?", (q["customer_id"],)).fetchone())
    ct = con.execute("SELECT * FROM contacts WHERE id=?", (q["contact_id"],)).fetchone() if q["contact_id"] else None
    con.close()
    return HTMLResponse(print_quote.render(dict(q), items, cust, dict(ct) if ct else None))

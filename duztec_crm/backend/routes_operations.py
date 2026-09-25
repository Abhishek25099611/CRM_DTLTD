"""Orders, follow-ups, RKZ assignment, Excel export, backup."""
from __future__ import annotations

import io
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import auth, db
from .schemas import AssignRkzIn, FollowupIn, OrderEditIn, StatusIn
from .services import _is_admin, _scope

router = APIRouter()

@router.post("/api/assign-rkz")
def assign_rkz(body: AssignRkzIn, request: Request):
    auth.require_admin(request)
    rkz = body.rkz.strip().upper()
    if rkz and not re.fullmatch(r"[A-Z0-9]{1,6}", rkz):
        raise HTTPException(422, {"error_type": "bad_rkz", "detail": "RKZ must be 1-6 letters/digits (e.g. RV)."})
    table_col = {"enquiry": ("enquiries", "salesperson"), "quotation": ("quotations", "salesperson"),
                 "order": ("orders", "responsible")}.get(body.entity_type)
    if not table_col or not body.ids:
        raise HTTPException(422, {"error_type": "bad_request", "detail": "entity_type must be enquiry/quotation/order with ids."})
    table, col = table_col
    con = db.connect()
    known = {r["rkz"] for r in con.execute("SELECT DISTINCT rkz FROM users WHERE rkz!=''")}
    marks = ",".join("?" * len(body.ids))
    con.execute(f"UPDATE {table} SET {col}=? WHERE id IN ({marks})", (rkz, *body.ids))
    if table == "quotations":
        # keep matching orders in sync so scoping stays consistent
        con.execute(f"UPDATE orders SET responsible=? WHERE quotation_id IN ({marks})", (rkz, *body.ids))
    db.log_activity(con, body.entity_type, body.ids[0] if len(body.ids) == 1 else None,
                    "rkz_assigned", f"{rkz or '(cleared)'} on {len(body.ids)} {body.entity_type}(s)")
    con.commit(); con.close()
    return {"ok": True, "updated": len(body.ids),
            "warning": "" if (not rkz or rkz in known) else f"No user currently has RKZ {rkz} — assign it to a user in the Users tab too."}


@router.get("/api/rkz-overview")
def rkz_overview(request: Request):
    auth.require_admin(request)
    con = db.connect()
    users = db.rows(con.execute("SELECT email,name,rkz,role,active FROM users ORDER BY active DESC, email"))
    unassigned = {
        "enquiries": con.execute("SELECT COUNT(*) n FROM enquiries WHERE salesperson='' OR salesperson IS NULL").fetchone()["n"],
        "quotations": con.execute("SELECT COUNT(*) n FROM quotations WHERE (salesperson='' OR salesperson IS NULL) AND status!='superseded'").fetchone()["n"],
        "orders": con.execute("SELECT COUNT(*) n FROM orders WHERE responsible='' OR responsible IS NULL").fetchone()["n"],
    }
    by_rkz = db.rows(con.execute("""SELECT s.rkz, SUM(s.e) enquiries, SUM(s.q) quotations, SUM(s.o) orders FROM (
        SELECT UPPER(salesperson) rkz, COUNT(*) e, 0 q, 0 o FROM enquiries WHERE salesperson!='' GROUP BY 1
        UNION ALL SELECT UPPER(salesperson), 0, COUNT(*), 0 FROM quotations WHERE salesperson!='' AND status!='superseded' GROUP BY 1
        UNION ALL SELECT UPPER(responsible), 0, 0, COUNT(*) FROM orders WHERE responsible!='' GROUP BY 1) s GROUP BY s.rkz ORDER BY s.rkz"""))
    con.close()
    return {"users": users, "unassigned": unassigned, "by_rkz": by_rkz}


@router.get("/api/followups")
def followups(request: Request, all: int = 0):
    sc = _scope(request)
    con = db.connect()
    sql = """SELECT f.*, CASE f.entity_type WHEN 'enquiry' THEN (SELECT enq_no||' · '||c.name FROM enquiries e JOIN customers c ON c.id=e.customer_id WHERE e.id=f.entity_id)
             ELSE (SELECT q.quote_no||' · '||c.name FROM quotations q JOIN customers c ON c.id=q.customer_id WHERE q.id=f.entity_id) END ref
             FROM followups f"""
    conds = []
    args2: list = []
    if not all:
        conds.append("f.done=0")
    if sc:
        conds.append("""((f.entity_type='enquiry' AND EXISTS(SELECT 1 FROM enquiries e WHERE e.id=f.entity_id AND e.salesperson=?))
                      OR (f.entity_type='quotation' AND EXISTS(SELECT 1 FROM quotations q WHERE q.id=f.entity_id AND q.salesperson=?)))""")
        args2 += [sc, sc]
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    out = db.rows(con.execute(sql + " ORDER BY f.done, f.due_date", args2))
    con.close()
    return out


@router.post("/api/followups")
def add_followup(f: FollowupIn):
    con = db.connect()
    cur = con.execute("INSERT INTO followups(entity_type,entity_id,due_date,channel,note,created_at) VALUES(?,?,?,?,?,?)",
                      (f.entity_type, f.entity_id, f.due_date, f.channel, f.note, db.now()))
    con.commit(); nid = cur.lastrowid; con.close()
    return {"id": nid}


@router.post("/api/followups/{fid}/done")
def followup_done(fid: int, s: StatusIn):
    con = db.connect()
    con.execute("UPDATE followups SET done=1, outcome=? WHERE id=?", (s.reason, fid))
    con.commit(); con.close()
    return {"ok": True}


@router.get("/api/orders")
def orders(request: Request):
    sc = _scope(request)
    con = db.connect()
    w = " WHERE (o.responsible=? OR q.salesperson=?)" if sc else ""
    out = db.rows(con.execute(f"""SELECT o.*, c.name customer, q.quote_no, q.rev quote_rev,
                                 q.delivery_terms quote_delivery_terms FROM orders o
                                 JOIN customers c ON c.id=o.customer_id
                                 LEFT JOIN quotations q ON q.id=o.quotation_id{w} ORDER BY o.id DESC""",
                              (sc, sc) if sc else ()))
    con.close()
    return out


@router.put("/api/orders/{oid}")
def edit_order(oid: int, body: OrderEditIn, request: Request):
    """SO number, PO details and payment terms are editable by an admin or the order's own RKZ."""
    sc = _scope(request)
    con = db.connect()
    o = con.execute("""SELECT o.responsible, q.salesperson FROM orders o LEFT JOIN quotations q ON q.id=o.quotation_id
                       WHERE o.id=?""", (oid,)).fetchone()
    if not o:
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"order {oid}"})
    if sc and sc not in ((o["responsible"] or "").upper(), (o["salesperson"] or "").upper()):
        con.close(); raise HTTPException(403, {"error_type": "forbidden", "detail": "This order belongs to another RKZ code."})
    con.execute("""UPDATE orders SET po_no=?, so_no=?, po_date=?, value=COALESCE(NULLIF(?,0), value),
                   payment_terms=?, delivery_date=? WHERE id=?""",
                (body.po_no.strip(), body.so_no.strip(), body.po_date.strip(), body.value,
                 body.payment_terms.strip(), body.delivery_date.strip(), oid))
    db.log_activity(con, "order", oid, "edited", f"SO {body.so_no.strip() or '-'} · PO {body.po_no.strip() or '-'}")
    con.commit(); con.close()
    return {"ok": True}


@router.get("/api/export/{register}.xlsx")
def export(register: str, request: Request):
    import openpyxl
    sc = _scope(request)
    con = db.connect()
    E = " AND e.salesperson=?" if sc else ""
    Q = " AND q.salesperson=?" if sc else ""
    O = " AND (o.responsible=? OR q.salesperson=?)" if sc else ""
    queries = {
        "enquiries": (f"SELECT e.enq_no,e.date,e.source,c.name customer,e.system,e.requirement,e.expected_value,e.salesperson,e.priority enquiry_type,e.status FROM enquiries e JOIN customers c ON c.id=e.customer_id WHERE 1=1{E} ORDER BY e.id", (sc,) if sc else ()),
        "quotations": (f"SELECT q.quote_no,q.rev,q.date,c.name customer,q.type,q.status,q.lost_reason,q.salesperson,q.payment_terms FROM quotations q JOIN customers c ON c.id=q.customer_id WHERE q.status!='superseded'{Q} ORDER BY q.id", (sc,) if sc else ()),
        "orders": (f"SELECT o.po_no,o.so_no,o.po_date,c.name customer,q.quote_no,o.system,o.value,o.responsible,o.payment_terms,o.delivery_date FROM orders o JOIN customers c ON c.id=o.customer_id LEFT JOIN quotations q ON q.id=o.quotation_id WHERE 1=1{O} ORDER BY o.id", (sc, sc) if sc else ()),
        "customers": ("SELECT name,gstin,address,state,pincode,segment FROM customers ORDER BY name", ()),
        "contacts": ("SELECT c.name customer,ct.name,ct.designation,ct.department,ct.phone,ct.email FROM contacts ct JOIN customers c ON c.id=ct.customer_id ORDER BY c.name, ct.name", ()),
    }
    if register == "logins":
        if not _is_admin(request):
            con.close(); raise HTTPException(403, {"error_type": "forbidden", "detail": "Admin access required."})
        queries["logins"] = ("SELECT at, action, detail FROM activity WHERE entity_type='user' AND action IN ('login','logout','session_expired') ORDER BY id DESC", ())
    if register not in queries:
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": register})
    sql2, args3 = queries[register]
    data = db.rows(con.execute(sql2, args3))
    con.close()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = register
    if data:
        ws.append(list(data[0].keys()))
        for r in data:
            ws.append(list(r.values()))
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{register}_{datetime.now():%Y-%m-%d}.xlsx"'})


@router.post("/api/backup")
def do_backup():
    return {"path": db.backup()}

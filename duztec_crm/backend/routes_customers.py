"""Customers and contacts."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from . import auth, db, print_quote
from .config import LOGGER, SETTINGS
from .schemas import (AssignRkzIn, ContactIn, CustomerIn, EnquiryIn, FollowupIn, ItemIn, QuotationIn, StatusIn)
from .services import _check_quote_access, _geo_state, _q_totals, _quote_row, _scope

router = APIRouter()

@router.get("/api/customers")
def customers(q: str = ""):
    con = db.connect()
    sql = """SELECT c.*, (SELECT COUNT(*) FROM enquiries e WHERE e.customer_id=c.id) enquiries,
             (SELECT COUNT(*) FROM quotations x WHERE x.customer_id=c.id AND x.status!='superseded') quotes,
             (SELECT COALESCE(SUM(value),0) FROM orders o WHERE o.customer_id=c.id) order_value
             FROM customers c"""
    args: tuple = ()
    if q:
        sql += " WHERE c.name LIKE ?"; args = (f"%{q}%",)
    out = db.rows(con.execute(sql + " ORDER BY c.name COLLATE NOCASE", args))
    con.close()
    return out


@router.post("/api/customers")
def add_customer(c: CustomerIn):
    con = db.connect()
    ex = con.execute("SELECT id FROM customers WHERE name=? COLLATE NOCASE", (c.name.strip(),)).fetchone()
    if ex:
        con.close()
        raise HTTPException(409, {"error_type": "duplicate", "detail": f"Customer already exists (id {ex['id']})"})
    cur = con.execute("INSERT INTO customers(name,gstin,address,state,pincode,segment,created_at) VALUES(?,?,?,?,?,?,?)",
                      (c.name.strip(), c.gstin, c.address, c.state, c.pincode.strip(), c.segment, db.now()))
    db.log_activity(con, "customer", cur.lastrowid, "created", c.name)
    con.commit(); nid = cur.lastrowid; con.close()
    return {"id": nid}


@router.put("/api/customers/{cid}")
def edit_customer(cid: int, c: CustomerIn):
    con = db.connect()
    con.execute("UPDATE customers SET name=?,gstin=?,address=?,state=?,pincode=?,segment=? WHERE id=?",
                (c.name.strip(), c.gstin, c.address, c.state, c.pincode.strip(), c.segment, cid))
    con.commit(); con.close()
    return {"ok": True}


@router.get("/api/contacts")
def contacts(customer_id: int):
    con = db.connect()
    out = db.rows(con.execute("SELECT * FROM contacts WHERE customer_id=? ORDER BY name", (customer_id,)))
    con.close()
    return out


@router.post("/api/contacts")
def add_contact(c: ContactIn):
    con = db.connect()
    cur = con.execute("INSERT INTO contacts(customer_id,name,phone,email,role) VALUES(?,?,?,?,?)",
                      (c.customer_id, c.name.strip(), c.phone, c.email, c.role))
    con.commit(); nid = cur.lastrowid; con.close()
    return {"id": nid}

"""Customers and contacts (many contacts per customer)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from . import db
from .schemas import ContactIn, CustomerIn

router = APIRouter()

@router.get("/api/customers")
def customers(q: str = ""):
    con = db.connect()
    sql = """SELECT c.*, (SELECT COUNT(*) FROM enquiries e WHERE e.customer_id=c.id) enquiries,
             (SELECT COUNT(*) FROM quotations x WHERE x.customer_id=c.id AND x.status!='superseded') quotes,
             (SELECT COALESCE(SUM(value),0) FROM orders o WHERE o.customer_id=c.id) order_value,
             (SELECT COUNT(*) FROM contacts ct WHERE ct.customer_id=c.id) contact_count
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
    cur = con.execute("""INSERT INTO contacts(customer_id,name,phone,email,role,designation,department)
                         VALUES(?,?,?,?,?,?,?)""",
                      (c.customer_id, c.name.strip(), c.phone.strip(), c.email.strip(), c.role.strip(),
                       c.designation.strip(), c.department.strip()))
    db.log_activity(con, "customer", c.customer_id, "contact_added", c.name)
    con.commit(); nid = cur.lastrowid; con.close()
    return {"id": nid}


@router.put("/api/contacts/{cid}")
def edit_contact(cid: int, c: ContactIn):
    con = db.connect()
    if not con.execute("SELECT 1 FROM contacts WHERE id=?", (cid,)).fetchone():
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"contact {cid}"})
    con.execute("UPDATE contacts SET name=?,phone=?,email=?,role=?,designation=?,department=? WHERE id=?",
                (c.name.strip(), c.phone.strip(), c.email.strip(), c.role.strip(),
                 c.designation.strip(), c.department.strip(), cid))
    con.commit(); con.close()
    return {"ok": True}


@router.delete("/api/contacts/{cid}")
def delete_contact(cid: int):
    con = db.connect()
    used = con.execute("""SELECT (SELECT COUNT(*) FROM enquiries WHERE contact_id=?) +
                                 (SELECT COUNT(*) FROM quotations WHERE contact_id=?)""", (cid, cid)).fetchone()[0]
    if used:
        con.close()
        raise HTTPException(409, {"error_type": "in_use",
                                  "detail": f"This contact is used on {used} enquiry/quotation record(s) and cannot be deleted."})
    con.execute("DELETE FROM contacts WHERE id=?", (cid,))
    con.commit(); con.close()
    return {"ok": True}

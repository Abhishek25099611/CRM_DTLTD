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
             (SELECT COUNT(*) FROM contacts ct WHERE ct.customer_id=c.id) contact_count,
             (SELECT COUNT(*) FROM documents d WHERE d.entity_type='customer' AND d.entity_id=c.id) document_count
             FROM customers c"""
    args: tuple = ()
    if q.strip():
        like = f"%{q.strip()}%"
        sql += """ WHERE c.name LIKE ? OR c.end_customer LIKE ? OR c.vendor_code LIKE ?
                   OR c.gstin LIKE ? OR c.state LIKE ? OR c.pincode LIKE ? OR c.segment LIKE ?"""
        args = (like, like, like, like, like, like, like)
    out = db.rows(con.execute(sql + " ORDER BY c.name COLLATE NOCASE", args))
    con.close()
    return out


def _check_vendor_code(con, code: str, exclude_id: int | None = None) -> None:
    """Duztec's vendor code is unique per customer (blank is allowed for customers without one yet)."""
    code = code.strip()
    if not code:
        return
    row = con.execute("SELECT id, name FROM customers WHERE vendor_code=? COLLATE NOCASE AND id IS NOT ?",
                      (code, exclude_id)).fetchone()
    if row:
        con.close()
        raise HTTPException(409, {"error_type": "duplicate_vendor_code",
                                  "detail": f"Vendor code '{code}' is already used by {row['name']}."})


@router.post("/api/customers")
def add_customer(c: CustomerIn):
    con = db.connect()
    ex = con.execute("SELECT id FROM customers WHERE name=? COLLATE NOCASE", (c.name.strip(),)).fetchone()
    if ex:
        con.close()
        raise HTTPException(409, {"error_type": "duplicate", "detail": f"Customer already exists (id {ex['id']})"})
    _check_vendor_code(con, c.vendor_code)
    cur = con.execute("""INSERT INTO customers(name,gstin,address,state,pincode,segment,end_customer,vendor_code,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                      (c.name.strip(), c.gstin, c.address, c.state, c.pincode.strip(), c.segment,
                       c.end_customer.strip(), c.vendor_code.strip(), db.now()))
    db.log_activity(con, "customer", cur.lastrowid, "created", c.name)
    con.commit(); nid = cur.lastrowid; con.close()
    return {"id": nid}


@router.put("/api/customers/{cid}")
def edit_customer(cid: int, c: CustomerIn):
    con = db.connect()
    if not con.execute("SELECT 1 FROM customers WHERE id=?", (cid,)).fetchone():
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"customer {cid}"})
    _check_vendor_code(con, c.vendor_code, exclude_id=cid)
    con.execute("""UPDATE customers SET name=?,gstin=?,address=?,state=?,pincode=?,segment=?,end_customer=?,vendor_code=?
                   WHERE id=?""",
                (c.name.strip(), c.gstin, c.address, c.state, c.pincode.strip(), c.segment,
                 c.end_customer.strip(), c.vendor_code.strip(), cid))
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

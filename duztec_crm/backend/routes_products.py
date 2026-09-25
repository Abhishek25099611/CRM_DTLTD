"""Products master: code, name, HSN, unit, default rate, specification text (printed on quotations)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from . import auth, db
from .schemas import ProductIn

router = APIRouter()


@router.get("/api/products")
def products(active_only: int = 0):
    con = db.connect()
    sql = """SELECT p.*, (SELECT COUNT(*) FROM quotation_items i WHERE i.product_id=p.id) used_on
             FROM products p"""
    if active_only:
        sql += " WHERE p.active=1"
    out = db.rows(con.execute(sql + " ORDER BY p.active DESC, p.code"))
    con.close()
    return out


@router.post("/api/products")
def add_product(p: ProductIn, request: Request):
    auth.require_admin(request)
    code = p.code.strip().upper()
    con = db.connect()
    if con.execute("SELECT 1 FROM products WHERE code=?", (code,)).fetchone():
        con.close(); raise HTTPException(409, {"error_type": "duplicate", "detail": f"Product code {code} already exists."})
    cur = con.execute("""INSERT INTO products(code,name,hsn,unit,rate,specification,active,created_at) VALUES(?,?,?,?,?,?,?,?)""",
                      (code, p.name.strip(), p.hsn.strip(), p.unit.strip() or "Nos.", p.rate, p.specification.strip(),
                       1 if p.active else 0, db.now()))
    db.log_activity(con, "product", cur.lastrowid, "created", code)
    con.commit(); nid = cur.lastrowid; con.close()
    return {"id": nid}


@router.put("/api/products/{pid}")
def edit_product(pid: int, p: ProductIn, request: Request):
    auth.require_admin(request)
    code = p.code.strip().upper()
    con = db.connect()
    if not con.execute("SELECT 1 FROM products WHERE id=?", (pid,)).fetchone():
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"product {pid}"})
    if con.execute("SELECT 1 FROM products WHERE code=? AND id!=?", (code, pid)).fetchone():
        con.close(); raise HTTPException(409, {"error_type": "duplicate", "detail": f"Product code {code} already exists."})
    con.execute("""UPDATE products SET code=?,name=?,hsn=?,unit=?,rate=?,specification=?,active=? WHERE id=?""",
                (code, p.name.strip(), p.hsn.strip(), p.unit.strip() or "Nos.", p.rate, p.specification.strip(),
                 1 if p.active else 0, pid))
    db.log_activity(con, "product", pid, "edited", code)
    con.commit(); con.close()
    return {"ok": True}


@router.delete("/api/products/{pid}")
def retire_product(pid: int, request: Request):
    """Products are never hard-deleted (quotation lines may reference them); this deactivates."""
    auth.require_admin(request)
    con = db.connect()
    con.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
    con.commit(); con.close()
    return {"ok": True}

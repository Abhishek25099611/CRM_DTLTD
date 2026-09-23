"""Dashboard: health, config, KPI summary, region heat map."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from . import auth, db, print_quote
from .config import LOGGER, SETTINGS
from .schemas import (AssignRkzIn, ContactIn, CustomerIn, EnquiryIn, FollowupIn, ItemIn, QuotationIn, StatusIn)
from .services import _check_quote_access, _geo_state, _q_totals, _quote_row, _scope, pincode_coords

router = APIRouter()

@router.get("/api/health")
def health():
    return {"status": "ok", "db": str(SETTINGS.db), "company": SETTINGS.company_name}


@router.get("/api/config")
def config():
    return {"company_name": SETTINGS.company_name, "tagline": SETTINGS.tagline,
            "quotation_defaults": SETTINGS.quotation_defaults, "company": SETTINGS.company}


@router.get("/api/summary")
def summary(request: Request):
    sc = _scope(request)
    E = " AND salesperson=?" if sc else ""
    Q = " AND q.salesperson=?" if sc else ""
    a = (sc,) if sc else ()
    con = db.connect()
    today = date.today().isoformat()
    enq = db.rows(con.execute(f"SELECT status, COUNT(*) n, SUM(expected_value) v FROM enquiries WHERE 1=1{E} GROUP BY status", a))
    stale = con.execute(f"""SELECT COUNT(*) n FROM enquiries WHERE status IN ('new','qualified')
                           AND updated_at < datetime('now','-7 day'){E}""", a).fetchone()["n"]
    quotes = db.rows(con.execute(f"SELECT status, COUNT(*) n FROM quotations q WHERE status!='superseded'{Q} GROUP BY status", a))
    pipeline = 0.0
    for r in con.execute(f"SELECT id FROM quotations q WHERE status IN ('sent','draft'){Q}", a):
        pipeline += _q_totals(con, r["id"])["total"]
    won = con.execute(f"SELECT COUNT(*) n FROM quotations q WHERE status='won'{Q}", a).fetchone()["n"]
    lost = con.execute(f"SELECT COUNT(*) n FROM quotations q WHERE status='lost'{Q}", a).fetchone()["n"]
    o_where = " WHERE (o.responsible=? OR q.salesperson=?)" if sc else ""
    orders = con.execute(f"""SELECT COUNT(*) n, COALESCE(SUM(o.value),0) v FROM orders o
                             LEFT JOIN quotations q ON q.id=o.quotation_id{o_where}""",
                         (sc, sc) if sc else ()).fetchone()
    fu_due = con.execute("SELECT COUNT(*) n FROM followups WHERE done=0 AND due_date<=?", (today,)).fetchone()["n"]
    monthly = db.rows(con.execute(f"""SELECT substr(date,1,7) m, COUNT(*) n FROM quotations q
                                     WHERE status!='superseded'{Q} GROUP BY m ORDER BY m""", a))
    recent = db.rows(con.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 12"))
    con.close()
    return {"enquiries": enq, "enquiries_stale": stale, "quotes": quotes, "pipeline_value": round(pipeline, 2),
            "won": won, "lost": lost, "orders": dict(orders), "followups_due": fu_due,
            "monthly_quotes": monthly, "recent": recent, "today": today,
            "scope_rkz": sc}


@router.get("/api/geo")
def geo(request: Request):
    sc = _scope(request)
    con = db.connect()
    out: dict[str, dict[str, dict[str, float]]] = {"enquiries": {}, "offers": {}, "won": {}}

    def add(metric: str, state_raw: str, value: float):
        st = _geo_state(state_raw) or "(No state set)"
        d = out[metric].setdefault(st, {"n": 0, "value": 0.0})
        d["n"] += 1
        d["value"] += value or 0.0

    E = " AND e.salesperson=?" if sc else ""
    Q = " AND q.salesperson=?" if sc else ""
    a = (sc,) if sc else ()
    for r in con.execute(f"""SELECT e.expected_value v, c.state FROM enquiries e JOIN customers c ON c.id=e.customer_id WHERE 1=1{E}""", a):
        add("enquiries", r["state"], r["v"])
    for r in con.execute(f"""SELECT q.id, c.state FROM quotations q JOIN customers c ON c.id=q.customer_id
                            WHERE q.status!='superseded'{Q}""", a):
        add("offers", r["state"], _q_totals(con, r["id"])["total"])
    o_and = " AND (o.responsible=? OR q.salesperson=?)" if sc else ""
    for r in con.execute(f"""SELECT o.value v, c.state FROM orders o JOIN customers c ON c.id=o.customer_id
                             LEFT JOIN quotations q ON q.id=o.quotation_id WHERE 1=1{o_and}""",
                         (sc, sc) if sc else ()):
        add("won", r["state"], r["v"])
    # ---- pincode-level points (exact locations) ----
    coords = pincode_coords()
    points: dict[str, dict[str, dict]] = {"enquiries": {}, "offers": {}, "won": {}}
    no_pin = {"enquiries": 0, "offers": 0, "won": 0}

    def addp(metric: str, pin: str, cust: str, value: float):
        if not pin or pin not in coords:
            no_pin[metric] += 1
            return
        d = points[metric].setdefault(pin, {"pin": pin, "lat": coords[pin][0], "lon": coords[pin][1],
                                            "n": 0, "value": 0.0, "customers": []})
        d["n"] += 1
        d["value"] += value or 0.0
        if cust and cust not in d["customers"]:
            d["customers"].append(cust)

    for r in con.execute(f"""SELECT e.expected_value v, c.pincode pin, c.name FROM enquiries e
                             JOIN customers c ON c.id=e.customer_id WHERE 1=1{E}""", a):
        addp("enquiries", r["pin"], r["name"], r["v"])
    for r in con.execute(f"""SELECT q.id, c.pincode pin, c.name FROM quotations q JOIN customers c ON c.id=q.customer_id
                             WHERE q.status!='superseded'{Q}""", a):
        addp("offers", r["pin"], r["name"], _q_totals(con, r["id"])["total"])
    for r in con.execute(f"""SELECT o.value v, c.pincode pin, c.name FROM orders o JOIN customers c ON c.id=o.customer_id
                             LEFT JOIN quotations q ON q.id=o.quotation_id WHERE 1=1{o_and}""",
                         (sc, sc) if sc else ()):
        addp("won", r["pin"], r["name"], r["v"])
    con.close()
    for m in out.values():
        for d in m.values():
            d["value"] = round(d["value"], 2)
    for m in points.values():
        for d in m.values():
            d["value"] = round(d["value"], 2)
            d["customers"] = d["customers"][:4]
    return {**out, "points": {k: list(v.values()) for k, v in points.items()}, "no_pincode": no_pin}

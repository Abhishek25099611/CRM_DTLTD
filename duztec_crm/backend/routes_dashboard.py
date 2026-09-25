"""Dashboard: health, config, KPI summary, region heat map."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from . import auth, db, print_quote
from .config import LOGGER, SETTINGS
from .schemas import (AssignRkzIn, ContactIn, CustomerIn, EnquiryIn, FollowupIn, ItemIn, QuotationIn, StatusIn)
from .services import INDIAN_STATES, _check_quote_access, _geo_state, _q_totals, _quote_row, _scope, pincode_coords, sla_for

router = APIRouter()

@router.get("/api/health")
def health():
    return {"status": "ok", "db": str(SETTINGS.db), "company": SETTINGS.company_name}


@router.get("/api/config")
def config():
    return {"company_name": SETTINGS.company_name, "tagline": SETTINGS.tagline,
            "quotation_defaults": SETTINGS.quotation_defaults, "company": SETTINGS.company,
            "enquiry_types": SETTINGS.enquiry_types, "states": INDIAN_STATES}


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
    # Lost deals have no order, so their value is the quoted total (GST-inclusive, same basis as pipeline).
    lost_value = sum(_q_totals(con, r["id"])["total"]
                     for r in con.execute(f"SELECT id FROM quotations q WHERE status='lost'{Q}", a))
    o_where = " WHERE (o.responsible=? OR q.salesperson=?)" if sc else ""
    orders = con.execute(f"""SELECT COUNT(*) n, COALESCE(SUM(o.value),0) v FROM orders o
                             LEFT JOIN quotations q ON q.id=o.quotation_id{o_where}""",
                         (sc, sc) if sc else ()).fetchone()
    fu_due = con.execute("SELECT COUNT(*) n FROM followups WHERE done=0 AND due_date<=?", (today,)).fetchone()["n"]
    monthly = db.rows(con.execute(f"""SELECT substr(date,1,7) m, COUNT(*) n FROM quotations q
                                     WHERE status!='superseded'{Q} GROUP BY m ORDER BY m""", a))
    recent = db.rows(con.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 12"))
    # 48-hour SLA: enquiry punch-in -> first quotation sent, in working hours
    sla = {"in_time": 0, "late": 0, "open_breach": 0, "open_warn": 0, "limit": float(SETTINGS.sla.get("quote_within_hours", 48))}
    for r in con.execute(f"""SELECT e.created_at, e.status,
                             (SELECT MIN(q.sent_at) FROM quotations q WHERE q.enquiry_id=e.id AND q.sent_at!='') fs
                             FROM enquiries e WHERE 1=1{E}""", a):
        st = sla_for(r["created_at"], r["fs"], r["status"])["sla"]
        if st == "ok": sla["in_time"] += 1
        elif st == "late": sla["late"] += 1
        elif st == "breach": sla["open_breach"] += 1
        elif st == "warn": sla["open_warn"] += 1
    quoted = sla["in_time"] + sla["late"]
    sla["pct_in_time"] = round(100 * sla["in_time"] / quoted, 1) if quoted else None
    # Month-wise series for the last 12 months: enquiries -> quotations (+value, won) -> orders (+value)
    y, m, keys = today[:4], int(today[5:7]), []
    yy, mm = int(y), m
    for _ in range(12):
        keys.append(f"{yy:04d}-{mm:02d}")
        mm -= 1
        if mm == 0:
            mm, yy = 12, yy - 1
    series = {k: {"m": k, "enquiries": 0, "quotations": 0, "quotation_value": 0.0, "won": 0, "orders": 0, "order_value": 0.0}
              for k in reversed(keys)}
    for r in con.execute(f"SELECT substr(date,1,7) m FROM enquiries WHERE 1=1{E}", a):
        if r["m"] in series:
            series[r["m"]]["enquiries"] += 1
    for r in con.execute(f"SELECT id, substr(date,1,7) m, status FROM quotations q WHERE status!='superseded'{Q}", a):
        if r["m"] in series:
            series[r["m"]]["quotations"] += 1
            series[r["m"]]["quotation_value"] += _q_totals(con, r["id"])["total"]
            if r["status"] == "won":
                series[r["m"]]["won"] += 1
    for r in con.execute(f"""SELECT o.value v, substr(COALESCE(NULLIF(o.po_date,''), o.created_at),1,7) m FROM orders o
                             LEFT JOIN quotations q ON q.id=o.quotation_id{o_where}""", (sc, sc) if sc else ()):
        if r["m"] in series:
            series[r["m"]]["orders"] += 1
            series[r["m"]]["order_value"] += float(r["v"] or 0)
    monthly_series = [{**v, "quotation_value": round(v["quotation_value"], 2), "order_value": round(v["order_value"], 2)}
                      for v in series.values()]
    con.close()
    won_value = float(orders["v"] or 0)
    decided_n = int(orders["n"]) + lost
    return {"enquiries": enq, "enquiries_stale": stale, "quotes": quotes, "pipeline_value": round(pipeline, 2),
            "won": won, "lost": lost, "orders": dict(orders), "followups_due": fu_due,
            "won_value": round(won_value, 2), "lost_value": round(lost_value, 2),
            "win_rate_count": round(100 * orders["n"] / decided_n, 1) if decided_n else 0.0,
            "win_rate_value": round(100 * won_value / (won_value + lost_value), 1) if (won_value + lost_value) else 0.0,
            "monthly_quotes": monthly, "monthly": monthly_series, "recent": recent, "today": today, "sla": sla,
            "scope_rkz": sc}


@router.get("/api/geo")
def geo(request: Request):
    sc = _scope(request)
    con = db.connect()
    out: dict[str, dict[str, dict[str, float]]] = {"enquiries": {}, "offers": {}, "won": {}}

    def add(metric: str, state_raw: str, value: float, cust: str = ""):
        st = _geo_state(state_raw) or "(No state set)"
        d = out[metric].setdefault(st, {"n": 0, "value": 0.0, "customers": []})
        d["n"] += 1
        d["value"] += value or 0.0
        if cust and cust not in d["customers"]:
            d["customers"].append(cust)

    E = " AND e.salesperson=?" if sc else ""
    Q = " AND q.salesperson=?" if sc else ""
    a = (sc,) if sc else ()
    for r in con.execute(f"""SELECT e.expected_value v, c.state, c.name FROM enquiries e JOIN customers c ON c.id=e.customer_id WHERE 1=1{E}""", a):
        add("enquiries", r["state"], r["v"], r["name"])
    for r in con.execute(f"""SELECT q.id, c.state, c.name FROM quotations q JOIN customers c ON c.id=q.customer_id
                            WHERE q.status!='superseded'{Q}""", a):
        add("offers", r["state"], _q_totals(con, r["id"])["total"], r["name"])
    o_and = " AND (o.responsible=? OR q.salesperson=?)" if sc else ""
    for r in con.execute(f"""SELECT o.value v, c.state, c.name FROM orders o JOIN customers c ON c.id=o.customer_id
                             LEFT JOIN quotations q ON q.id=o.quotation_id WHERE 1=1{o_and}""",
                         (sc, sc) if sc else ()):
        add("won", r["state"], r["v"], r["name"])
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

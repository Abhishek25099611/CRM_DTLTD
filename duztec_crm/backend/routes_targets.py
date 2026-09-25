"""Sales targets per user: admin sets them; achievement is computed live from RKZ-scoped records."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request

from . import auth, db
from .config import SETTINGS
from .schemas import TargetIn
from .services import _is_admin, _q_totals

router = APIRouter()

MEASURES = {
    "order_value": "Order value (₹)",
    "order_count": "Orders booked",
    "quotation_value": "Quotation value sent (₹)",
    "quotation_count": "Quotations sent",
    "enquiry_count": "Enquiries logged",
}
PERIODS = ("monthly", "quarterly", "yearly")


def _add_months(d: date, n: int) -> date:
    y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    return date(y, m, 1)


def period_bounds(period_type: str, start: str) -> tuple[str, str]:
    """Start is normalised to the 1st of its month; the end is the last day of the period."""
    try:
        s = date.fromisoformat(start).replace(day=1)
    except ValueError:
        raise HTTPException(422, {"error_type": "bad_date", "detail": "period_start must be YYYY-MM-DD"})
    months = {"monthly": 1, "quarterly": 3, "yearly": 12}[period_type]
    return s.isoformat(), (_add_months(s, months) - timedelta(days=1)).isoformat()


def achieved(con, rkz: str, measure: str, ps: str, pe: str) -> float:
    rkz = (rkz or "").upper()
    if not rkz:
        return 0.0
    if measure in ("order_value", "order_count"):
        r = con.execute("""SELECT COUNT(*) n, COALESCE(SUM(o.value),0) v FROM orders o
                           LEFT JOIN quotations q ON q.id=o.quotation_id
                           WHERE (UPPER(o.responsible)=? OR UPPER(q.salesperson)=?)
                             AND COALESCE(NULLIF(o.po_date,''), substr(o.created_at,1,10)) BETWEEN ? AND ?""",
                        (rkz, rkz, ps, pe)).fetchone()
        return float(r["v"]) if measure == "order_value" else float(r["n"])
    if measure in ("quotation_value", "quotation_count"):
        ids = [r["id"] for r in con.execute("""SELECT id FROM quotations WHERE UPPER(salesperson)=? AND status!='superseded'
                                               AND sent_at!='' AND substr(sent_at,1,10) BETWEEN ? AND ?""", (rkz, ps, pe))]
        return float(sum(_q_totals(con, i)["total"] for i in ids)) if measure == "quotation_value" else float(len(ids))
    if measure == "enquiry_count":
        return float(con.execute("SELECT COUNT(*) FROM enquiries WHERE UPPER(salesperson)=? AND date BETWEEN ? AND ?",
                                 (rkz, ps, pe)).fetchone()[0])
    return 0.0


def enrich(con, t: dict) -> dict:
    today = date.today()
    ps, pe = date.fromisoformat(t["period_start"]), date.fromisoformat(t["period_end"])
    got = achieved(con, t["rkz"], t["measure"], t["period_start"], t["period_end"])
    amt = float(t["amount"] or 0)
    total_days = (pe - ps).days + 1
    days_left = max(0, (pe - today).days + 1) if today <= pe else 0
    t.update(measure_label=MEASURES.get(t["measure"], t["measure"]), achieved=round(got, 2),
             remaining=round(max(0.0, amt - got), 2), pct=round(100 * got / amt, 1) if amt else 0.0,
             days_total=total_days, days_left=days_left, elapsed_pct=round(100 * min(total_days, max(0, (today - ps).days + 1)) / total_days, 1),
             state="done" if amt and got >= amt else ("expired" if today > pe else ("upcoming" if today < ps else "running")))
    return t


def _user_row(con, email: str):
    return con.execute("SELECT email, name, rkz, role, active FROM users WHERE email=?", (email.strip().lower(),)).fetchone()


@router.get("/api/targets")
def list_targets(request: Request, email: str = ""):
    """Admins: every target (optionally one user); engineers/viewers: their own."""
    me = auth.current_user(request)
    con = db.connect()
    if _is_admin(request):
        sql, args = "SELECT * FROM targets", []
        if email:
            sql += " WHERE email=?"; args = [email.strip().lower()]
    else:
        sql, args = "SELECT * FROM targets WHERE email=?", [me["email"]]
    rows = [enrich(con, r) for r in db.rows(con.execute(sql + " ORDER BY period_start DESC, email", args))]
    con.close()
    return rows


@router.get("/api/targets/mine")
def my_targets(request: Request):
    """The caller's targets whose period contains today (for the dashboard block), plus recent past ones."""
    me = auth.current_user(request)
    today = date.today().isoformat()
    con = db.connect()
    rows = [enrich(con, r) for r in db.rows(con.execute(
        "SELECT * FROM targets WHERE email=? ORDER BY period_start DESC LIMIT 12", (me["email"],)))]
    con.close()
    return {"current": [t for t in rows if t["period_start"] <= today <= t["period_end"]],
            "past": [t for t in rows if t["period_end"] < today][:6],
            "upcoming": [t for t in rows if t["period_start"] > today]}


@router.get("/api/targets/overview")
def overview(request: Request):
    """Admin team view: every running target with progress, grouped per user."""
    auth.require_admin(request)
    today = date.today().isoformat()
    con = db.connect()
    rows = [enrich(con, r) for r in db.rows(con.execute(
        "SELECT * FROM targets WHERE period_start<=? AND period_end>=? ORDER BY email, measure", (today, today)))]
    # anyone with an RKZ code can carry a target (sales engineers, and admins who also sell, e.g. RV)
    users = db.rows(con.execute("SELECT email, name, rkz, role FROM users WHERE active=1 AND rkz!='' ORDER BY email"))
    con.close()
    return {"targets": rows, "engineers": users, "measures": MEASURES, "periods": PERIODS}


@router.get("/api/targets/measures")
def measures():
    return {"measures": MEASURES, "periods": PERIODS, "default": SETTINGS.targets.get("default_measure", "order_value"),
            "fy_start_month": int(SETTINGS.targets.get("financial_year_start_month", 4))}


@router.post("/api/targets")
def add_target(t: TargetIn, request: Request):
    admin = auth.require_admin(request)
    if t.measure not in MEASURES:
        raise HTTPException(422, {"error_type": "bad_measure", "detail": f"measure must be one of {', '.join(MEASURES)}"})
    if t.period_type not in PERIODS:
        raise HTTPException(422, {"error_type": "bad_period", "detail": f"period_type must be one of {', '.join(PERIODS)}"})
    if t.amount <= 0:
        raise HTTPException(422, {"error_type": "bad_amount", "detail": "Target amount must be greater than zero."})
    con = db.connect()
    u = _user_row(con, t.email)
    if not u:
        con.close(); raise HTTPException(404, {"error_type": "no_user", "detail": "No such user — add them in the Users tab first."})
    if not u["rkz"]:
        con.close(); raise HTTPException(422, {"error_type": "no_rkz", "detail": f"{u['email']} has no RKZ code, so nothing can be counted towards a target. Assign one first."})
    ps, pe = period_bounds(t.period_type, t.period_start)
    dup = con.execute("SELECT id FROM targets WHERE email=? AND measure=? AND period_start=? AND period_type=?",
                      (u["email"], t.measure, ps, t.period_type)).fetchone()
    if dup:
        con.close(); raise HTTPException(409, {"error_type": "duplicate", "detail": f"A {t.period_type} {MEASURES[t.measure]} target starting {ps} already exists for this user (id {dup['id']}) — edit it instead."})
    cur = con.execute("""INSERT INTO targets(email,rkz,measure,period_type,period_start,period_end,amount,note,created_by,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (u["email"], u["rkz"], t.measure, t.period_type, ps, pe, t.amount, t.note.strip(), admin["email"], db.now()))
    db.log_activity(con, "target", cur.lastrowid, "set", f"{u['email']} {MEASURES[t.measure]} {t.amount:g} ({t.period_type} from {ps})")
    con.commit(); nid = cur.lastrowid; con.close()
    return {"id": nid, "period_start": ps, "period_end": pe}


@router.put("/api/targets/{tid}")
def edit_target(tid: int, t: TargetIn, request: Request):
    admin = auth.require_admin(request)
    if t.measure not in MEASURES or t.period_type not in PERIODS or t.amount <= 0:
        raise HTTPException(422, {"error_type": "bad_request", "detail": "Check measure, period type and amount."})
    con = db.connect()
    if not con.execute("SELECT 1 FROM targets WHERE id=?", (tid,)).fetchone():
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"target {tid}"})
    u = _user_row(con, t.email)
    if not u:
        con.close(); raise HTTPException(404, {"error_type": "no_user", "detail": "No such user."})
    ps, pe = period_bounds(t.period_type, t.period_start)
    con.execute("""UPDATE targets SET email=?,rkz=?,measure=?,period_type=?,period_start=?,period_end=?,amount=?,note=? WHERE id=?""",
                (u["email"], u["rkz"], t.measure, t.period_type, ps, pe, t.amount, t.note.strip(), tid))
    db.log_activity(con, "target", tid, "edited", f"{u['email']} {MEASURES[t.measure]} {t.amount:g} by {admin['email']}")
    con.commit(); con.close()
    return {"ok": True, "period_start": ps, "period_end": pe}


@router.delete("/api/targets/{tid}")
def delete_target(tid: int, request: Request):
    admin = auth.require_admin(request)
    con = db.connect()
    r = con.execute("SELECT email FROM targets WHERE id=?", (tid,)).fetchone()
    if not r:
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"target {tid}"})
    con.execute("DELETE FROM targets WHERE id=?", (tid,))
    db.log_activity(con, "target", tid, "deleted", f"{r['email']} by {admin['email']}")
    con.commit(); con.close()
    return {"ok": True}

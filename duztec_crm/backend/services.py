"""Shared helpers: auth scoping, quotation totals, geo aliases."""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, Request

import json
from functools import lru_cache
from pathlib import Path

from . import auth, db


def _scope(request: Request) -> str | None:
    """None = see everything (admin, or read-only viewer). Otherwise the engineer's RKZ code
    ('' = no code assigned -> sees nothing personal)."""
    u = auth.current_user(request)
    if not u or u["role"] in ("admin", "viewer"):
        return None
    return (u.get("rkz") or "").strip().upper() or "__UNASSIGNED__"

def _q_totals(con, qid: int) -> dict[str, float]:
    q = con.execute("SELECT discount_pct FROM quotations WHERE id=?", (qid,)).fetchone()
    items = db.rows(con.execute("SELECT * FROM quotation_items WHERE quotation_id=? ORDER BY sr", (qid,)))
    sub = sum((i["qty"] or 0) * (i["rate"] or 0) for i in items)
    disc = sub * (q["discount_pct"] or 0) / 100
    gst = sum((i["qty"] or 0) * (i["rate"] or 0) * (1 - (q["discount_pct"] or 0) / 100) * (i["gst_pct"] or 0) / 100 for i in items)
    return {"subtotal": round(sub, 2), "discount": round(disc, 2), "gst": round(gst, 2),
            "total": round(sub - disc + gst, 2), "items": items}


def _quote_row(con, r: dict) -> dict:
    t = _q_totals(con, r["id"])
    r = dict(r)
    r.update(total=t["total"], subtotal=t["subtotal"], gst=t["gst"], item_count=len(t["items"]))
    return r





GEO_ALIASES = {"odisha": "Orissa", "uttarakhand": "Uttaranchal", "telangana": "Andhra Pradesh",
               "ladakh": "Jammu and Kashmir", "pondicherry": "Puducherry", "delhi ncr": "Delhi", "nct of delhi": "Delhi"}


def _geo_state(raw: str) -> str:
    st = str(raw or "").strip()
    return GEO_ALIASES.get(st.lower(), st) if st else ""


def _check_quote_access(request: Request, q) -> None:
    sc = _scope(request)
    if sc and (q["salesperson"] or "").strip().upper() != sc:
        raise HTTPException(403, {"error_type": "forbidden", "detail": "This quotation belongs to another RKZ code."})


@lru_cache(maxsize=1)
def pincode_coords() -> dict:
    """pincode -> [lat, lon] (loaded once)."""
    path = Path(__file__).resolve().parent / "pincodes.json"
    try:
        return json.loads(path.read_text())
    except OSError:
        return {}


INDIAN_STATES = [
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
    "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry",
    "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "International",
]


def _is_admin(request: Request) -> bool:
    u = auth.current_user(request)
    return bool(u and u["role"] == "admin")


def _check_quote_edit(request: Request, q) -> None:
    """Edit/revise rule: engineers may edit only their own Drafts; anything Sent or later is admin-only."""
    _check_quote_access(request, q)
    if _is_admin(request):
        return
    if (q["status"] or "") != "draft":
        raise HTTPException(403, {"error_type": "locked",
                                  "detail": "Quotation is locked once marked Sent — ask an admin to edit or revise it."})

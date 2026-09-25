"""OTP login restricted to the Duztec email domain + user management."""
from __future__ import annotations

import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import db
from .config import LOGGER, SETTINGS

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE = "duztec_crm_session"
ROLES = ("admin", "user", "viewer")   # user = sales engineer (own RKZ data); viewer = read-only, sees everything

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT DEFAULT '',
  role TEXT NOT NULL DEFAULT 'user', active INTEGER NOT NULL DEFAULT 1,
  rkz TEXT DEFAULT '', created_at TEXT NOT NULL, last_login TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS otps(
  id INTEGER PRIMARY KEY, email TEXT NOT NULL, code_hash TEXT NOT NULL,
  expires_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, email TEXT NOT NULL,
  expires_at TEXT NOT NULL, created_at TEXT NOT NULL);
"""


def _h(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def _domain() -> str:
    return str(SETTINGS.auth.get("allowed_domain", "duztec.in")).lower().lstrip("@")


def _norm_email(email: str) -> str:
    e = str(email or "").strip().lower()
    if "@" not in e or len(e.split("@")[0]) < 2 or "." not in e.split("@")[1]:
        raise HTTPException(422, {"error_type": "bad_email", "detail": "Enter a valid email address."})
    return e


def _seed_emails() -> set[str]:
    return {str(x).strip().lower() for x in (SETTINGS.auth.get("admin_emails") or [])}


def _check_add_domain(email: str) -> None:
    if not email.endswith("@" + _domain()) and email not in _seed_emails():
        raise HTTPException(422, {"error_type": "bad_domain",
                                  "detail": f"Only {_domain()} email addresses can be added (e.g. office@{_domain()})"})


def init() -> None:
    con = db.connect()
    con.executescript(AUTH_SCHEMA)
    if "rkz" not in [r[1] for r in con.execute("PRAGMA table_info(users)")]:
        con.execute("ALTER TABLE users ADD COLUMN rkz TEXT DEFAULT ''")
    rkz_map = {str(k).strip().lower(): str(v).strip().upper()
               for k, v in (SETTINGS.auth.get("rkz_codes") or {}).items()}
    for e in SETTINGS.auth.get("admin_emails") or []:
        e = str(e).strip().lower()
        if not e:
            continue
        row = con.execute("SELECT id, role FROM users WHERE email=?", (e,)).fetchone()
        if not row:
            con.execute("INSERT INTO users(email,name,role,rkz,created_at) VALUES(?,?,?,?,?)",
                        (e, e.split("@")[0].replace(".", " ").title(), "admin", rkz_map.get(e, ""), db.now()))
            LOGGER.info("Seeded admin user %s", e)
        elif row["role"] != "admin":
            con.execute("UPDATE users SET role='admin' WHERE id=?", (row["id"],))
            LOGGER.info("Promoted %s to admin (config)", e)
        if rkz_map.get(e):
            con.execute("UPDATE users SET rkz=? WHERE email=? AND (rkz='' OR rkz IS NULL)", (rkz_map[e], e))
    con.commit(); con.close()


def send_mail(to_addr: str, subject: str, body: str) -> bool:
    """Send one message. Returns False when SMTP is not configured.

    Port 465 uses implicit SSL; anything else (typically 587) uses STARTTLS.
    """
    smtp = SETTINGS.auth.get("smtp") or {}
    host = str(smtp.get("host") or "").strip()
    if not host:
        return False
    port = int(smtp.get("port", 587))
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp.get("from_addr") or smtp.get("username") or f"crm@{_domain()}"
    msg["To"] = to_addr
    msg.set_content(body)
    cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with cls(host, port, timeout=30) as srv:
        if port != 465:
            srv.starttls()
        if smtp.get("username"):
            srv.login(smtp["username"], smtp.get("password", ""))
        srv.send_message(msg)
    return True


def _send_otp(email: str, code: str) -> bool:
    minutes = int(SETTINGS.auth.get("otp_minutes", 10))
    body = (f"Your Duztec CRM login code is: {code}\n\n"
            f"It is valid for {minutes} minutes. If you did not request this, ignore this email.")
    try:
        sent = send_mail(email, f"Duztec CRM login code: {code}", body)
    except Exception as e:  # noqa: BLE001 - a mail failure must never block login
        LOGGER.error("SMTP send failed for %s (%s: %s) — LOGIN OTP: %s", email, type(e).__name__, e, code)
        return False
    if not sent:
        LOGGER.warning("SMTP not configured — LOGIN OTP for %s: %s (valid %d min)", email, code, minutes)
    return sent


class EmailIn(BaseModel):
    email: str = Field(min_length=5)


class VerifyIn(BaseModel):
    email: str
    code: str = Field(min_length=4, max_length=8)


class UserIn(BaseModel):
    email: str
    name: str = ""
    role: str = "user"
    active: int = 1
    rkz: str = ""


@router.post("/request-otp")
def request_otp(body: EmailIn):
    email = _norm_email(body.email)
    con = db.connect()
    u = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u or not u["active"]:
        con.close()
        raise HTTPException(403, {"error_type": "no_user",
                                  "detail": "This email is not registered in the CRM. Ask an admin to add you (Users tab)."})
    recent = con.execute("SELECT created_at FROM otps WHERE email=? ORDER BY id DESC LIMIT 1", (email,)).fetchone()
    if recent and (datetime.now() - datetime.strptime(recent["created_at"], "%Y-%m-%d %H:%M:%S")).total_seconds() < 45:
        con.close()
        raise HTTPException(429, {"error_type": "too_fast", "detail": "Please wait a moment before requesting another code."})
    code = f"{secrets.randbelow(900000) + 100000}"
    exp = (datetime.now() + timedelta(minutes=int(SETTINGS.auth.get("otp_minutes", 10)))).strftime("%Y-%m-%d %H:%M:%S")
    con.execute("DELETE FROM otps WHERE email=?", (email,))
    con.execute("INSERT INTO otps(email,code_hash,expires_at,created_at) VALUES(?,?,?,?)", (email, _h(code), exp, db.now()))
    con.commit(); con.close()
    mailed = _send_otp(email, code)
    return {"sent": True, "mailed": mailed,
            "message": "Code sent to your email." if mailed else
            "SMTP is not configured yet — the code was written to the CRM server log; ask the administrator."}


@router.post("/verify")
def verify(body: VerifyIn, response: Response):
    email = _norm_email(body.email)
    con = db.connect()
    o = con.execute("SELECT * FROM otps WHERE email=? ORDER BY id DESC LIMIT 1", (email,)).fetchone()
    if not o or o["expires_at"] < db.now():
        con.close()
        raise HTTPException(401, {"error_type": "otp_expired", "detail": "Code expired — request a new one."})
    if o["attempts"] >= 5:
        con.close()
        raise HTTPException(429, {"error_type": "too_many", "detail": "Too many wrong attempts — request a new code."})
    if _h(body.code.strip()) != o["code_hash"]:
        con.execute("UPDATE otps SET attempts=attempts+1 WHERE id=?", (o["id"],))
        con.commit(); con.close()
        raise HTTPException(401, {"error_type": "otp_wrong", "detail": "Incorrect code."})
    con.execute("DELETE FROM otps WHERE email=?", (email,))
    token = secrets.token_urlsafe(32)
    hours = int(SETTINGS.auth.get("session_hours", 168))
    exp = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    con.execute("INSERT INTO sessions(token_hash,email,expires_at,created_at) VALUES(?,?,?,?)",
                (_h(token), email, exp, db.now()))
    con.execute("UPDATE users SET last_login=? WHERE email=?", (db.now(), email))
    for ex in con.execute("SELECT email, expires_at FROM sessions WHERE expires_at < ?", (db.now(),)):
        db.log_activity(con, "user", None, "session_expired", f"{ex['email']} (expired {ex['expires_at']})")
    con.execute("DELETE FROM sessions WHERE expires_at < ?", (db.now(),))
    db.log_activity(con, "user", None, "login", email)
    con.commit(); con.close()
    response.set_cookie(COOKIE, token, max_age=hours * 3600, httponly=True, samesite="lax")
    return {"ok": True, "email": email}


def current_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    con = db.connect()
    s = con.execute("SELECT * FROM sessions WHERE token_hash=? AND expires_at>=?", (_h(token), db.now())).fetchone()
    u = con.execute("SELECT * FROM users WHERE email=? AND active=1", (s["email"],)).fetchone() if s else None
    con.close()
    return dict(u) if u else None


@router.get("/me")
def me(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(401, {"error_type": "unauthenticated", "detail": "Please log in."})
    return {"email": u["email"], "name": u["name"], "role": u["role"], "rkz": u.get("rkz") or "",
            "company_name": SETTINGS.company_name, "tagline": SETTINGS.tagline}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        con = db.connect()
        sess = con.execute("SELECT email FROM sessions WHERE token_hash=?", (_h(token),)).fetchone()
        con.execute("DELETE FROM sessions WHERE token_hash=?", (_h(token),))
        if sess:
            db.log_activity(con, "user", None, "logout", sess["email"])
        con.commit(); con.close()
    response.delete_cookie(COOKIE)
    return {"ok": True}


# ---------------- user management (admin only) ----------------
def require_admin(request: Request) -> dict:
    u = current_user(request)
    if not u:
        raise HTTPException(401, {"error_type": "unauthenticated", "detail": "Please log in."})
    if u["role"] != "admin":
        raise HTTPException(403, {"error_type": "forbidden", "detail": "Admin access required."})
    return u


@router.get("/users")
def list_users(request: Request):
    require_admin(request)
    con = db.connect()
    out = db.rows(con.execute("SELECT id,email,name,role,active,rkz,created_at,last_login,last_seen FROM users ORDER BY email"))
    con.close()
    act = int(SETTINGS.presence.get("active_minutes", 5)) * 60
    idle = int(SETTINGS.presence.get("idle_minutes", 30)) * 60
    now_dt = datetime.now()
    for u in out:
        age = None
        if u.get("last_seen"):
            try:
                age = (now_dt - datetime.strptime(u["last_seen"], "%Y-%m-%d %H:%M:%S")).total_seconds()
            except ValueError:
                age = None
        u["presence"] = "out" if age is None or age > idle else ("active" if age <= act else "idle")
    return out


@router.post("/heartbeat")
def heartbeat(request: Request):
    """Browser pings every minute while the CRM tab is open — feeds Active / Idle / Out on the Users tab.
    It measures 'CRM open in a browser', not 'working'."""
    u = current_user(request)
    if not u:
        raise HTTPException(401, {"error_type": "unauthenticated", "detail": "Please log in."})
    con = db.connect()
    con.execute("UPDATE users SET last_seen=? WHERE email=?", (db.now(), u["email"]))
    con.commit(); con.close()
    return {"ok": True}


@router.post("/users")
def add_user(body: UserIn, request: Request):
    admin = require_admin(request)
    email = _norm_email(body.email)
    if body.role not in ROLES:
        raise HTTPException(422, {"error_type": "bad_role", "detail": f"role must be one of {', '.join(ROLES)}"})
    _check_add_domain(email)
    rkz = body.rkz.strip().upper()
    con = db.connect()
    if con.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        con.close()
        raise HTTPException(409, {"error_type": "duplicate", "detail": "User already exists."})
    if rkz and con.execute("SELECT 1 FROM users WHERE rkz=? AND rkz!=''", (rkz,)).fetchone():
        con.close()
        raise HTTPException(409, {"error_type": "duplicate_rkz", "detail": f"RKZ code {rkz} is already assigned to another user."})
    con.execute("INSERT INTO users(email,name,role,rkz,created_at) VALUES(?,?,?,?,?)",
                (email, body.name.strip() or email.split("@")[0].title(), body.role, rkz, db.now()))
    db.log_activity(con, "user", None, "user_added", f"{email} by {admin['email']}")
    con.commit(); con.close()
    return {"ok": True}


@router.put("/users/{uid}")
def edit_user(uid: int, body: UserIn, request: Request):
    admin = require_admin(request)
    con = db.connect()
    u = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        con.close(); raise HTTPException(404, {"error_type": "not_found", "detail": f"user {uid}"})
    if body.role not in ROLES:
        con.close(); raise HTTPException(422, {"error_type": "bad_role", "detail": f"role must be one of {', '.join(ROLES)}"})
    if u["email"] == admin["email"] and (not body.active or body.role != "admin"):
        con.close(); raise HTTPException(422, {"error_type": "self_lockout", "detail": "You cannot deactivate or demote yourself."})
    rkz = body.rkz.strip().upper()
    if rkz and con.execute("SELECT 1 FROM users WHERE rkz=? AND rkz!='' AND id!=?", (rkz, uid)).fetchone():
        con.close()
        raise HTTPException(409, {"error_type": "duplicate_rkz", "detail": f"RKZ code {rkz} is already assigned to another user."})
    con.execute("UPDATE users SET name=?, role=?, active=?, rkz=? WHERE id=?",
                (body.name.strip() or u["name"], body.role, 1 if body.active else 0, rkz, uid))
    if not body.active:
        con.execute("DELETE FROM sessions WHERE email=?", (u["email"],))
    db.log_activity(con, "user", uid, "user_edited", f"{u['email']} by {admin['email']}")
    con.commit(); con.close()
    return {"ok": True}


@router.get("/login-history")
def login_history(request: Request, email: str = "", days: int = 30):
    """Login / logout / session-expiry events from the activity log (admin only)."""
    require_admin(request)
    days = max(1, min(int(days), 365))
    con = db.connect()
    sql = """SELECT at, action, detail FROM activity WHERE entity_type='user'
             AND action IN ('login','logout','session_expired') AND at >= datetime('now', ?)"""
    args: list = [f"-{days} day"]
    if email:
        sql += " AND detail LIKE ?"; args.append(f"{email.strip().lower()}%")
    rows = db.rows(con.execute(sql + " ORDER BY id DESC LIMIT 2000", args))
    con.close()
    for r in rows:
        r["email"] = r["detail"].split(" ")[0]
    return rows

"""Outgoing mail transports.

    auth.mail.method: "smtp"  -> smtplib (STARTTLS on 587, implicit SSL on 465)      [default]
    auth.mail.method: "graph" -> Microsoft Graph sendMail over HTTPS (app-only OAuth2 client credentials)

Graph exists because Microsoft 365 tenants ship with SMTP AUTH disabled and consumer broadband cannot
use port 25; port 443 is the one thing every network allows. Standard library only — the server rule
is "no extra packages", and two POSTs do not justify msal/requests.
"""
from __future__ import annotations

import json
import smtplib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from .config import SETTINGS

TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
SENDMAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
TIMEOUT = 30
GRAPH_KEYS = ("tenant_id", "client_id", "client_secret", "sender")

_token = {"value": "", "expires": 0.0}
_lock = threading.Lock()


class MailError(RuntimeError):
    """A transport failure with a message that already names the cause (status + provider error code)."""


def method() -> str:
    m = str((SETTINGS.auth.get("mail") or {}).get("method") or "smtp").strip().lower()
    return m if m in ("smtp", "graph") else "smtp"


def graph_settings() -> dict[str, str]:
    g = (SETTINGS.auth.get("mail") or {}).get("graph") or {}
    return {k: str(g.get(k) or "").strip() for k in GRAPH_KEYS}


def graph_configured() -> bool:
    return all(graph_settings().values())


def smtp_settings() -> dict:
    return SETTINGS.auth.get("smtp") or {}


def smtp_configured() -> bool:
    return bool(str(smtp_settings().get("host") or "").strip())


def configured() -> bool:
    return graph_configured() if method() == "graph" else smtp_configured()


# ---------------------------------------------------------------- SMTP
def smtp_send(to_addr: str, subject: str, body: str, default_from: str) -> None:
    smtp = smtp_settings()
    host = str(smtp.get("host") or "").strip()
    port = int(smtp.get("port", 587))
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp.get("from_addr") or smtp.get("username") or default_from
    msg["To"] = to_addr
    msg.set_content(body)
    cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with cls(host, port, timeout=TIMEOUT) as srv:
        if port != 465:
            srv.starttls()
        if smtp.get("username"):
            srv.login(smtp["username"], smtp.get("password", ""))
        srv.send_message(msg)


# ---------------------------------------------------------------- Microsoft Graph
def _post(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, (json.loads(raw) if raw else {})
        except ValueError:
            return e.code, {"raw": raw[:300].decode(errors="replace")}


def graph_token(force: bool = False) -> str:
    """App-only access token, cached in memory until ~5 minutes before it expires."""
    g = graph_settings()
    with _lock:
        if not force and _token["value"] and time.time() < _token["expires"]:
            return _token["value"]
        form = urllib.parse.urlencode({"client_id": g["client_id"], "client_secret": g["client_secret"],
                                       "scope": "https://graph.microsoft.com/.default",
                                       "grant_type": "client_credentials"}).encode()
        st, body = _post(TOKEN_URL.format(tenant=urllib.parse.quote(g["tenant_id"])), form,
                         {"Content-Type": "application/x-www-form-urlencoded"})
        if st != 200 or not body.get("access_token"):
            raise MailError(f"token request failed ({st}): {body.get('error', '?')} — "
                            f"{str(body.get('error_description', body.get('raw', '')))[:300]}")
        _token["value"] = body["access_token"]
        _token["expires"] = time.time() + int(body.get("expires_in", 3600)) - 300
        return _token["value"]


def graph_send(to_addr: str, subject: str, body: str) -> None:
    """POST /users/{sender}/sendMail. Success is HTTP 202 with an empty body; one retry on 401."""
    g = graph_settings()
    payload = json.dumps({"message": {"subject": subject, "body": {"contentType": "Text", "content": body},
                                      "toRecipients": [{"emailAddress": {"address": to_addr}}]},
                          "saveToSentItems": False}).encode()
    url = SENDMAIL_URL.format(sender=urllib.parse.quote(g["sender"]))
    for attempt in (1, 2):
        token = graph_token(force=attempt == 2)
        st, resp = _post(url, payload, {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        if 200 <= st < 300:
            return
        if st == 401 and attempt == 1:      # token rejected early (revoked / clock skew): refresh once
            continue
        err = resp.get("error") or {}
        raise MailError(f"Graph sendMail failed ({st}): {err.get('code', resp.get('raw', '?'))} — "
                        f"{str(err.get('message', ''))[:300]}")


# Hints for the check script: the provider's error code -> what an admin must do.
HINTS = (
    ("AADSTS7000215", "the client secret is wrong or expired — create a new secret in Entra and paste its VALUE (not its ID)."),
    ("AADSTS700016", "the application (client) id is not in this tenant — check client_id and tenant_id."),
    ("AADSTS90002", "tenant not found — tenant_id must be the Directory (tenant) ID GUID or the verified domain duztec.in."),
    ("AADSTS7000222", "the client secret has expired — create a new one."),
    ("ErrorAccessDenied", "Mail.Send (Application) permission is missing, admin consent was not granted, or an access policy excludes this mailbox."),
    ("ErrorInvalidUser", "the sender is not a mailbox in this tenant — use a licensed mailbox address (e.g. server@duztec.in)."),
    ("MailboxNotEnabledForRESTAPI", "the sender mailbox is not licensed for Exchange Online — assign a mailbox licence."),
    ("5.7.139", "SMTP AUTH is disabled for the tenant/mailbox — switch to method: graph or ask a Microsoft 365 admin to enable Authenticated SMTP."),
    ("5.7.3", "SMTP password rejected, or MFA / Security Defaults block basic authentication — switch to method: graph."),
    ("Spamhaus", "the server's public IP is blocklisted; Direct Send cannot work from this network — use method: graph."),
)


def hint_for(error_text: str) -> str:
    for needle, hint in HINTS:
        if needle in error_text:
            return hint
    return ""

"""Standalone outgoing-mail check — verifies email delivery without logging into the CRM.

Works for both transports (auth.mail.method: smtp | graph).

Usage (from the duztec_crm folder, venv active):
    python -m backend.check_smtp                    # show the effective settings only
    python -m backend.check_smtp someone@duztec.in  # ... and send a test message
"""
from __future__ import annotations

import sys
from datetime import datetime

from . import auth, mailer
from .config import LOCAL_CONFIG_PATH


def _masked(v: str) -> str:
    return f"set ({len(v)} chars)" if v else "NOT SET"


def main() -> int:
    m = mailer.method()
    print("Duztec CRM — outgoing mail check")
    print(f"  config.local.yaml : {LOCAL_CONFIG_PATH} ({'found' if LOCAL_CONFIG_PATH.exists() else 'NOT present'})")
    print(f"  method            : {m}")
    if m == "graph":
        g = mailer.graph_settings()
        print(f"  tenant_id         : {g['tenant_id'] or '(empty)'}")
        print(f"  client_id         : {g['client_id'] or '(empty)'}")
        print(f"  client_secret     : {_masked(g['client_secret'])}")
        print(f"  sender            : {g['sender'] or '(empty)'}")
        if not mailer.graph_configured():
            print("\nRESULT: Graph is NOT fully configured (all four keys are needed). Login codes go to data/logs/app.log.")
            print("Fix: fill auth.mail.graph in config.local.yaml (see config.local.example.yaml) and re-run.")
            return 1
    else:
        smtp = mailer.smtp_settings()
        port = int(smtp.get("port", 587))
        print(f"  host              : {smtp.get('host') or '(empty)'}")
        print(f"  port              : {port}  ({'implicit SSL' if port == 465 else 'STARTTLS'})")
        print(f"  username          : {smtp.get('username') or '(none)'}")
        print(f"  password          : {_masked(str(smtp.get('password') or ''))}")
        print(f"  from_addr         : {smtp.get('from_addr') or '(falls back to username)'}")
        if not mailer.smtp_configured():
            print("\nRESULT: SMTP is NOT configured. Login codes are written to data/logs/app.log instead.")
            print("Fix: create config.local.yaml (see config.local.example.yaml) and re-run this check.")
            return 1
    if len(sys.argv) < 2:
        print("\nPass a recipient to send a test message, e.g.:  python -m backend.check_smtp you@duztec.in")
        return 0
    to = sys.argv[1]
    if m == "graph":
        print("\nRequesting an access token from Microsoft Entra ...")
        try:
            mailer.graph_token(force=True)
            print("  token OK")
        except Exception as e:  # noqa: BLE001
            print(f"RESULT: FAILED at the token step — {type(e).__name__}: {e}")
            hint = mailer.hint_for(str(e))
            print(f"Hint: {hint}" if hint else "Hint: check tenant_id / client_id / client_secret in config.local.yaml.")
            return 2
    print(f"Sending test message to {to} ...")
    try:
        ok = auth.send_mail(to, "Duztec CRM — mail test",
                            f"This is a test message from the Duztec Sales CRM (method: {m}).\n"
                            f"Sent at {datetime.now():%d-%b-%Y %H:%M:%S}.\n\n"
                            "If you received this, login-code emails will work.")
    except Exception as e:  # noqa: BLE001
        print(f"RESULT: FAILED — {type(e).__name__}: {e}")
        hint = mailer.hint_for(str(e))
        if hint:
            print(f"Hint: {hint}")
        elif m == "graph":
            print("Hint: see HANDOFF.md §6 — Mail.Send application permission + admin consent, and the sender must be a licensed mailbox.")
        else:
            print("Common causes: wrong port (587 STARTTLS / 465 SSL), app-specific password needed, SMTP AUTH disabled "
                  "for the mailbox (Microsoft 365 default — use method: graph), outbound 587/465 blocked.")
        return 2
    print("RESULT: SENT" if ok else "RESULT: not sent (transport not configured)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

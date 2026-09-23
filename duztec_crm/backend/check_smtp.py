"""Standalone SMTP check — verifies email delivery without logging into the CRM.

Usage (from the duztec_crm folder, venv active):
    python -m backend.check_smtp someone@duztec.in
"""
from __future__ import annotations

import sys
from datetime import datetime

from . import auth
from .config import LOCAL_CONFIG_PATH, SETTINGS


def main() -> int:
    smtp = SETTINGS.auth.get("smtp") or {}
    host = str(smtp.get("host") or "").strip()
    print("Duztec CRM — SMTP check")
    print(f"  config.local.yaml : {LOCAL_CONFIG_PATH} ({'found' if LOCAL_CONFIG_PATH.exists() else 'NOT present'})")
    print(f"  host              : {host or '(empty)'}")
    print(f"  port              : {smtp.get('port', 587)}  ({'implicit SSL' if int(smtp.get('port', 587)) == 465 else 'STARTTLS'})")
    print(f"  username          : {smtp.get('username') or '(none)'}")
    print(f"  password          : {'set (' + str(len(str(smtp.get('password') or ''))) + ' chars)' if smtp.get('password') else 'NOT SET'}")
    print(f"  from_addr         : {smtp.get('from_addr') or '(falls back to username)'}")
    if not host:
        print("\nRESULT: SMTP is NOT configured. Login codes are written to data/logs/app.log instead.")
        print("Fix: create config.local.yaml (see config.local.example.yaml) and re-run this check.")
        return 1
    if len(sys.argv) < 2:
        print("\nPass a recipient to send a test message, e.g.:  python -m backend.check_smtp you@duztec.in")
        return 0
    to = sys.argv[1]
    print(f"\nSending test message to {to} ...")
    try:
        ok = auth.send_mail(to, "Duztec CRM — SMTP test",
                            f"This is a test message from the Duztec Sales CRM.\n"
                            f"Sent at {datetime.now():%d-%b-%Y %H:%M:%S}.\n\n"
                            "If you received this, OTP login emails will work.")
    except Exception as e:  # noqa: BLE001
        print(f"RESULT: FAILED — {type(e).__name__}: {e}")
        print("\nCommon causes:")
        print("  * Wrong port: use 587 (STARTTLS) or 465 (SSL) to match your provider.")
        print("  * Password is a normal mailbox password but the provider requires an app-specific password.")
        print("  * Provider blocks SMTP AUTH for this mailbox (enable it in the mail admin console).")
        print("  * Server firewall blocks outbound 587/465.")
        return 2
    print("RESULT: SENT" if ok else "RESULT: not sent (host empty)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

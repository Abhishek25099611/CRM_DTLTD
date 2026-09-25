# Email OTP delivery failure on the production server — brief for the development machine

**Status (2026-09-25):** login codes for *First login / Forgot password* are NOT delivered by email
on the production server. Every attempt fails and the app falls back to writing the code to
`data/logs/app.log`. No server-side configuration can fix it from the network the server is on.
The agreed fix is to send mail through the **Microsoft Graph API over HTTPS**, built and tested on
the development machine, then pulled onto the server.

This document contains no secrets. The mailbox password lives only in the server's git-ignored
`duztec_crm/config.local.yaml`.

---

## 1. What the user sees

1. User enters their email → *First login / Forgot password* → *Send Code*.
2. `POST /api/auth/request-otp` stores the hashed code, then calls `auth._send_otp()` → `auth.send_mail()`.
3. `send_mail()` raises; `_send_otp()` catches it and logs:
   ```
   ERROR duztec_crm: SMTP send failed for <email> (<ExceptionType>: <SMTP reply>) — LOGIN OTP: <6 digits>
   ```
4. The API returns `{"sent": true, "mailed": false, ...}` and the login card shows
   *"The email could not be sent — the code was written to the CRM server log; ask the administrator."*
5. Only someone sitting at the server can read the code (`findstr "LOGIN OTP" data\logs\app.log`),
   so remote users cannot set or reset a password without help.

Login itself (email + password) is unaffected. The failure only blocks first-time password setup
and password resets.

## 2. Server environment (the facts that make SMTP impossible)

| Item | Value |
|---|---|
| OS | Windows 11 Pro, CRM runs as SYSTEM via Task Scheduler (`run_crm_service.bat`) |
| Network | **Airtel consumer broadband**, Wi-Fi, LAN IP 192.168.1.62 (DHCP) |
| Public IPv4 | 110.226.176.84 (dynamic, residential) |
| Public IPv6 | 2401:4900:1c94:… (Airtel residential range, AS mentioned by Spamhaus) |
| Outbound 443 (HTTPS) | **Works** (git, pip, api.ipify.org all succeeded) |
| Outbound 587 (SMTP submission) | Works at TCP level (TLS handshake + AUTH reached Microsoft) |
| Outbound 25 over IPv4 | **Blocked by the ISP** (`Test-NetConnection 52.101.144.3 -Port 25` → `TcpTestSucceeded: False`) |
| Outbound 25 over IPv6 | Open, but the source address is on the **Spamhaus blocklist** |
| Mail tenant | duztec.in is on **Microsoft 365** (MX `duztec-in.mail.protection.outlook.com`) |
| Sending mailbox | `server@duztec.in` (licensed M365 mailbox, password known and correct) |

## 3. Every attempt and its exact error

### Attempt 1: personal Outlook.com account (2026-09-24)
```
host smtp-mail.outlook.com  port 587 STARTTLS  user duztec2023@outlook.com
→ SMTPAuthenticationError: (535, b'5.7.3 Authentication unsuccessful [...]')
```
Cause: Microsoft retired Basic authentication (username + password) for SMTP on consumer
Outlook.com accounts. Abandoned; do not revisit.

### Attempt 2: Microsoft 365 SMTP AUTH, the intended setup (2026-09-25)
```
host smtp.office365.com  port 587 STARTTLS  user server@duztec.in  (password 16 chars, verified loaded)
→ SMTPAuthenticationError: (535, b'5.7.139 Authentication unsuccessful, SmtpClientAuthentication is
  disabled for the Tenant. Visit https://aka.ms/smtp_auth_disabled for more information.
  [PN0PR01CA0035.INDPRD01.PROD.OUTLOOK.COM 2026-09-25T06:55:39.914Z 08DF19A9E2389312]')
```
Cause: SMTP AUTH is switched off for the whole duztec.in tenant (the Microsoft default for newer
tenants). A Microsoft 365 admin *could* enable it per mailbox (admin.microsoft.com → Users →
server@duztec.in → Mail → Manage email apps → "Authenticated SMTP"). However:
- Microsoft is retiring Basic authentication for SMTP AUTH in Exchange Online, so this is at best
  a temporary fix and may already be impossible for this tenant.
- Security Defaults / MFA on the mailbox would still block it.

**The server config is currently left on this setting**, so it starts working by itself if an
admin enables SMTP AUTH. It is not a solution we should depend on.

### Attempt 3: Microsoft 365 Direct Send, no authentication (2026-09-25)
```
host duztec-in.mail.protection.outlook.com  port 25  (no login; resolved to IPv6)
→ SMTPRecipientsRefused: {'office@duztec.in': (550, b'5.7.1 Service unavailable, Client host
  [2401:4900:1c94:6cc5:604e:d6c0:af7a:3ae6] blocked using Spamhaus. To request removal from this
  list see https://www.spamhaus.org/query/ip/2401:4900:1c94:6cc5:604e:d6c0:af7a:3ae6 AS(1440)
  [MA1PEPF00007265.INDPRD01.PROD.OUTLOOK.COM 2026-09-25T06:58:54.012Z 08DF144417886ECA]')}
```
IPv4 retry: TCP port 25 is blocked outbound by Airtel.
Cause: consumer broadband addresses are on Spamhaus policy lists and ISPs block port 25. That is
permanent for this line. Direct Send would also only reach @duztec.in mailboxes, never
`abhishek.ghumare@lechlerindia.com`. Abandoned.

### Summary

| Path | Transport | Blocked by | Fixable on the server? |
|---|---|---|---|
| Outlook.com SMTP | 587 | Basic auth retired (consumer) | No |
| M365 SMTP AUTH | 587 | Tenant has SMTP AUTH disabled; Basic auth being retired | Only temporarily, by a M365 admin |
| M365 Direct Send | 25 | ISP blocks IPv4:25; IPv6 on Spamhaus | No |
| **Microsoft Graph `sendMail`** | **443** | Nothing known | **Yes, needs code, the chosen fix** |

## 4. Relevant code (current `main`)

- `duztec_crm/backend/auth.py`
  - `send_mail(to_addr, subject, body) -> bool`: the **only** mail transport. It reads
    `SETTINGS.auth["smtp"]` and uses `smtplib.SMTP` + `starttls()` (or `SMTP_SSL` on 465), logging in
    only if `username` is set. It returns `False` when `host` is empty and raises on failure.
  - `_send_otp(email, code) -> bool` wraps `send_mail`. On any exception it logs the code with
    "SMTP send failed … LOGIN OTP: …" and returns False. **A mail failure must never block login.
    Keep this behaviour.**
  - `request_otp()` returns `mailed` to the frontend, which chooses the message shown.
- `duztec_crm/backend/check_smtp.py`: the standalone test (`python -m backend.check_smtp <to>`).
  It prints the effective settings, calls `auth.send_mail`, and prints the error on failure.
- `duztec_crm/backend/config.py`: `config.yaml` ← `config.local.yaml` ← env vars
  (`DUZTEC_SMTP_HOST/PORT/USER/PASSWORD/FROM`), deep-merged.
- `duztec_crm/config.local.example.yaml`: the template for the server's secrets file.

## 5. Requested change: add a Microsoft Graph transport

### Design
- Add a transport switch, e.g. `auth.mail.method: "graph" | "smtp"` (default `smtp` so existing
  installs are unchanged). `send_mail()` dispatches on it and keeps its signature and contract
  (returns False when unconfigured, raises on failure). `_send_otp`, `request_otp` and the frontend
  need no change.
- Graph path, OAuth2 **client-credentials** flow (app-only, no user sign-in, no MFA prompts):
  1. `POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token`
     form: `client_id`, `client_secret`, `scope=https://graph.microsoft.com/.default`,
     `grant_type=client_credentials` → `access_token` (≈60 min; cache it in memory until ~5 min
     before `expires_in`).
  2. `POST https://graph.microsoft.com/v1.0/users/{sender}/sendMail`
     `Authorization: Bearer <token>`, JSON body:
     ```json
     {"message": {"subject": "...", "body": {"contentType": "Text", "content": "..."},
                  "toRecipients": [{"emailAddress": {"address": "user@duztec.in"}}]},
      "saveToSentItems": false}
     ```
     Success = HTTP **202** with an empty body. On a non-2xx reply, raise with the status and Graph's
     `error.code` / `error.message` so it lands in the existing "send failed" log line.
- **Use only the standard library** (`urllib.request`, `urllib.parse`, `json`). The server rule is
  "no extra packages", and `msal`/`requests` are not needed for two POSTs. Timeout ~30 s.
- Config keys (secret values go in the server's `config.local.yaml`, never in git):
  ```yaml
  auth:
    mail:
      method: "graph"
      graph:
        tenant_id: "<directory (tenant) id GUID>"
        client_id: "<application (client) id GUID>"
        client_secret: "<secret value>"      # quote it; YAML treats '#' as a comment
        sender: "server@duztec.in"
  ```
  Optionally add env overrides (`DUZTEC_GRAPH_TENANT_ID`, `DUZTEC_GRAPH_CLIENT_ID`,
  `DUZTEC_GRAPH_CLIENT_SECRET`, `DUZTEC_GRAPH_SENDER`) alongside the existing SMTP ones in `config.py`.
- Update `check_smtp.py` (or add `check_mail.py`) to print the active method and the Graph settings
  with the secret masked (length only), fetch a token, and send the test. Map common failures to hints:
  - `AADSTS7000215` invalid client secret · `AADSTS700016` wrong client/tenant id
  - Graph `403 ErrorAccessDenied` → Mail.Send application permission missing, admin consent not
    granted, or the app is restricted away from this mailbox
  - `404 ErrorInvalidUser` / `MailboxNotEnabledForRESTAPI` → the sender is not a licensed mailbox
- Update `config.local.example.yaml`, `HANDOFF.md` §6 and the README email note. Keep the SMTP
  section as the fallback for other deployments.

### Microsoft 365 / Entra admin steps (document these in HANDOFF.md §6)
1. entra.microsoft.com → App registrations → **New registration** → name "Duztec CRM Mailer",
   single tenant, no redirect URI.
2. API permissions → Add → Microsoft Graph → **Application permissions** → `Mail.Send` →
   **Grant admin consent for duztec.in**.
3. Certificates & secrets → **New client secret** (24 months) → copy the *Value* once.
4. Note the **Directory (tenant) ID** and **Application (client) ID** from the Overview page.
5. **Restrict the app to the one mailbox.** By default `Mail.Send` (application) can send as *any*
   mailbox in the tenant. Scope it to server@duztec.in using Exchange Online **RBAC for
   Applications** (`New-ManagementScope` + `New-ManagementRoleAssignment -Role "Application Mail.Send"`),
   or the older `New-ApplicationAccessPolicy -AccessRight RestrictAccess`. Verify with
   `Test-ServicePrincipalAuthorization` / `Test-ApplicationAccessPolicy`.
6. Give the three values to whoever edits the server's `config.local.yaml`.

### Acceptance criteria
- On the server, `.venv\Scripts\python -m backend.check_smtp office@duztec.in` (or the new check
  script) reports the Graph method and ends with a successful send. The mail arrives.
- The same to an external address (`abhishek.ghumare@lechlerindia.com`) arrives. Graph, unlike
  Direct Send, is not limited to the tenant.
- In the app, *First login / Forgot password → Send Code* shows "Code sent to your email."
  and no new "SMTP send failed" lines appear in `data/logs/app.log`.
- With Graph misconfigured, login still works and the code still falls back to the log (behaviour
  unchanged).
- No secret is committed. `git status` never lists `config.local.yaml`.

### Deployment to the server afterwards
`git pull` on main → no new packages should be needed → edit `config.local.yaml` (add the
`auth.mail` block and keep the existing `company:` and `auth.smtp` blocks) → run the check script →
restart the "Duztec CRM" scheduled task (needs an elevated shell) → verify in the app.

## 6. Alternatives considered (not chosen)
- **SMTP AUTH with OAuth2 (XOAUTH2)** on smtp.office365.com:587: this also needs an app
  registration and still depends on the tenant's SMTP AUTH switch. Graph is simpler.
- **Third-party relay** (SendGrid, Brevo, Amazon SES on 587/2525/443): works from this network, but
  adds an external service and needs SPF/DKIM DNS records for duztec.in.
- **Moving the server to a business connection with a static IP**: would fix Direct Send for
  @duztec.in recipients only. Out of scope.

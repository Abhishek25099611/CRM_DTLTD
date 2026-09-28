# Duztec Sales CRM — Deployment & Handoff

**Application:** Duztec Sales CRM (enquiries → quotations → orders)
**Runs on:** one always-on office PC/server, served to users over the LAN
**Default URL:** `http://<server-ip>:8016/`
**Stack:** Python 3.11 · FastAPI · SQLite · vanilla JS (no build step, no external services)

This document is written for whoever installs and operates the app on the server. Read
sections 1–7 before the first install; sections 8–15 are operational reference.

---

## 1. What the application does

| Area | Capability |
|---|---|
| Enquiries | Punch-in form (`ENQ-2627-###`) with Enquiry Type and a **Technical** requirement field, duplicate warning, kanban New/Qualified/Quoted/Closed |
| Quotations | Line items with HSN/qty/rate/GST, CGST+SGST vs IGST, discount, revisions (`Q00xxx-B`), **Project specification** (Tender / Technical / Supporting / Other) with a list filter, end customer, text sections + auto-numbered **Terms & Conditions**, letterhead print → PDF. **Net value (excl. GST) is the primary figure**; Supporting quotations are never counted as business value |
| Orders | Created automatically when a quotation is marked **Won** (captures customer PO, delivery date, contact person name/phone/email copied from the quotation) |
| Customers | Master with GSTIN, state, pincode, contacts |
| Follow-ups | Dated reminders with due/overdue list |
| Dashboard | KPIs, funnel, quotations-by-month, **India map** (pincode bubbles or state heat) |
| Users | Password login (emailed code to set/reset), admin/engineer/viewer roles, **RKZ codes** with per-engineer data isolation |
| Documents | Files attached to customers, enquiries, quotations and orders (offers, costing sheets, drawings, customer PO PDF) — stored under `data/uploads/`, download only when logged in |
| SLA | Enquiry → quotation 48-working-hour timer (Mon–Sat 09:00–18:00) with badges and a dashboard KPI |
| Products | Master list (code, HSN, unit, rate, specification) feeding a dropdown on quotation lines; specifications print on the quotation |
| Targets | Admin sets per-user targets (₹ order value by default; also counts) per month/quarter/year; progress bars on each engineer's dashboard, team overview for admins |
| Presence | Users tab shows Active / Idle / Out from a browser heartbeat (tab open ≠ working) |
| Charts | Monthly funnel, order-value trend and quotation-vs-order value for the last 12 months |
| Export | Excel export of every register (incl. Lost deals and login history); one-click SQLite backup |

**Roles and RKZ scoping (important):**

| Role | Sees | Can change |
|---|---|---|
| Admin | everything | everything; sets RKZ codes, manages users, edits/revises any quotation |
| Sales engineer (`user`) | only records carrying their own RKZ code (e.g. `RV`) | their own records; may edit their own **Draft** quotations — once a quotation is marked **Sent** it is locked and only an admin can edit or revise it |
| View only (`viewer`) | everything | nothing — every create/edit/delete is refused by the server |

Records with no RKZ are invisible to engineers and visible only to admins and viewers.
Existing quotations imported from the MIS workbook have no RKZ until an admin assigns one.

---

## 2. Repository layout

```
Duztec_Dashbaord/                 <- repository root
├── HANDOFF.md                    <- this file
├── SERVER_PROMPT.md              <- paste into Claude Code on the server to automate setup
├── .gitignore
└── duztec_crm/                   <- the application
    ├── config.yaml               shared defaults (in git)
    ├── config.local.example.yaml template for machine-specific secrets
    ├── run_dashboard.bat         interactive launcher (opens a browser)
    ├── run_crm_service.bat       headless launcher for Task Scheduler
    ├── backup_crm.bat            nightly backup job
    ├── backend/
    │   ├── main.py               app factory: login middleware, startup, routers, static files
    │   ├── config.py             YAML + config.local.yaml + env vars -> Settings singleton
    │   ├── db.py                 SQLite schema, numbering, state/pincode backfill, backup
    │   ├── auth.py               password login, emailed-code reset, sessions, user management, send_mail()
    │   ├── check_smtp.py         standalone "does email work?" test
    │   ├── schemas.py            Pydantic request models
    │   ├── services.py           RKZ scoping, quotation totals, geo helpers
    │   ├── routes_dashboard.py   /api/health /api/config /api/summary /api/geo
    │   ├── routes_customers.py   customers + contacts
    │   ├── routes_enquiries.py   enquiry punch-in + statuses
    │   ├── routes_quotations.py  builder, revisions, won/lost, print
    │   ├── routes_operations.py  orders, follow-ups, assign-rkz, exports, backup
    │   ├── import_mis.py         one-time MIS workbook import (opening data)
    │   ├── print_quote.py        quotation → letterhead HTML (GST split, amount in words)
    │   ├── pincodes.json         10,892 Indian pincodes → lat/lon (offline geocoding)
    │   └── requirements.txt
    ├── frontend/                 index.html · crm.js · charts.js · style.css · logos · india_states.json
    └── data/                     crm.db · logs/ · backup/         [NOT in git]
```

Adding a feature = one new `routes_*.py` + one line in `main.py`. The frontend is a single
`crm.js` on purpose — no build step, no npm, nothing to compile on the server.

---

## 3. What is deliberately NOT in git

| Excluded | Why | How it reaches the server |
|---|---|---|
| `duztec_crm/data/` (crm.db, logs, backups) | Live business data; would cause merge conflicts | **Copy `crm.db` manually — see §5.3** |
| `config.local.yaml` | Contains the real SMTP password | Created on the server from the example file |
| `.venv*/`, `__pycache__/` | Machine-specific binaries | Recreated by the launcher |
| `*.xlsx`, `*.xls` | Source business workbooks | Copy manually if a fresh MIS import is wanted |
| `_archive/` | Retired dashboards from the earlier project phase | Not needed in production |

---

## 4. Server requirements

- **OS:** Windows 10/11 (primary target; Linux works — see §5.7)
- **Python 3.11 or newer**, "Add python.exe to PATH" ticked during install
- **Git** (to clone and pull updates)
- ~500 MB free disk for app + venv; data grows slowly (current DB ≈ 100 KB)
- **Wired LAN, static IP** — users bookmark `http://<ip>:8016/`
- **UPS strongly recommended** — SQLite plus sudden power loss is the main data-loss risk
- Outbound TCP **587** (or 465) open for sending login-code emails (first login / password reset)

Hardware: any modern mini-PC/desktop is far more than enough (the app idles at ~150 MB RAM).

---

## 5. First deployment

### 5.1 Install prerequisites
Install Python 3.11+ and Git. Verify in a new terminal:
```
python --version
git --version
```

### 5.2 Clone the repository
```
cd C:\
git clone <your-private-repo-url> Duztec_Dashbaord
cd Duztec_Dashbaord\duztec_crm
```

### 5.3 Restore the live data  ← **do this before the first start**
The database holds all customers, quotations, orders, users and RKZ assignments.

Copy `duztec_crm/data/crm.db` from the current machine to the same path on the server
(USB stick, shared folder — it is a single file). Then:
```
mkdir data\logs data\backup      (if they do not exist)
```

> **If you skip this step**, the app starts with an empty database and will import
> `MIS 2026-27.xlsx` if you place that workbook one level above `duztec_crm`. That recreates
> customers/quotations/orders from the spreadsheet but **loses** anything entered in the CRM
> since the import (quotations Q00566+, RKZ assignments, pincode edits, extra users).
> Copying `crm.db` is the correct path for this migration.

### 5.4 Create the local config (SMTP + real GSTIN)
```
copy config.local.example.yaml config.local.yaml
notepad config.local.yaml
```
Fill in the SMTP block (§6). `config.local.yaml` is git-ignored, so `git pull` will never
overwrite it and your password never lands in the repository.

### 5.5 First run
```
run_dashboard.bat
```
The launcher creates `.venv`, installs dependencies, and starts the server on port 8016.
Leave the window open (§8 makes it start automatically instead).

Verify: `http://127.0.0.1:8016/api/health` returns `{"status":"ok",...}`.

### 5.6 First login
1. Open `http://127.0.0.1:8016/`
2. Enter an admin email (seeded in `config.yaml → auth.admin_emails`):
   `office@duztec.in`, `vasanirs@duztec.in`, `abhishek.ghumare@lechlerindia.com`
3. Nobody has a password yet, so click **First login / Forgot password** → **Send Code**.
   **With SMTP working**, the 6-digit code arrives by email.
   **Without SMTP**, it is written to `data\logs\app.log` — find it with:
   ```
   findstr "LOGIN OTP" data\logs\app.log
   ```
4. Enter the code and choose a password (8+ characters). You are logged in; from then on log in
   with email + password. The session lasts 7 days per browser.
5. Go to the **Users** tab → add each sales engineer with a unique **RKZ code**.

### 5.7 Linux alternative
```
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8016
```
Use a systemd unit instead of Task Scheduler (§8).

---

## 6. Email configuration — required for real users

Until outgoing mail works the app still runs, but login codes go only to the server log —
meaning **only someone with access to the server can set or reset a password**. Configure it
before rollout. There are two transports (`backend/mailer.py`), selected by `auth.mail.method`
in `config.local.yaml`:

| Method | How it sends | When to use |
|---|---|---|
| `graph` | Microsoft Graph `sendMail` over HTTPS (port 443) with an Entra app registration | **Duztec's server** — duztec.in is on Microsoft 365, the tenant has SMTP AUTH disabled and the Airtel line blocks port 25 (see `EMAIL_OTP_ISSUE.md`) |
| `smtp` (default) | `smtplib`, STARTTLS on 587 or implicit SSL on 465 | Any provider that still allows password SMTP (Zoho, Google Workspace app password, cPanel) |

### 6.1 Microsoft Graph — one-time setup by a Microsoft 365 admin (about 15 minutes)
1. Sign in at **entra.microsoft.com** as a duztec.in Global Administrator → *App registrations* →
   **New registration**: name `Duztec CRM Mailer`, *Accounts in this organizational directory only*,
   no redirect URI → Register.
2. On the app's **Overview** page copy the **Application (client) ID** and the **Directory (tenant) ID**.
3. **API permissions** → Add a permission → Microsoft Graph → **Application permissions** →
   `Mail.Send` → Add. Then click **Grant admin consent for duztec.in** (status must show a green tick).
4. **Certificates & secrets** → New client secret → description `CRM server`, expiry 24 months →
   Add → copy the **Value** column immediately (it is shown once; the *Secret ID* is not it).
   Put a reminder in the calendar to rotate it before it expires.
5. Restrict the app to the one sending mailbox (by default `Mail.Send` can send as *any* mailbox).
   In Exchange Online PowerShell (`Connect-ExchangeOnline`):
   ```powershell
   New-ApplicationAccessPolicy -AppId <client id> -PolicyScopeGroupId server@duztec.in `
       -AccessRight RestrictAccess -Description "Duztec CRM may send only as server@duztec.in"
   Test-ApplicationAccessPolicy -AppId <client id> -Identity server@duztec.in     # expect AccessCheckResult: Granted
   ```
   (Policies take up to 30 minutes to apply.)
6. Hand the three values to whoever edits the server's `config.local.yaml`:
```yaml
auth:
  mail:
    method: "graph"
    graph:
      tenant_id: "<Directory (tenant) ID>"
      client_id: "<Application (client) ID>"
      client_secret: "<secret VALUE — keep the double quotes>"
      sender: "server@duztec.in"          # must be a licensed mailbox in the tenant
```
   Environment variables work too and keep the secret out of files: `DUZTEC_MAIL_METHOD=graph`,
   `DUZTEC_GRAPH_TENANT_ID`, `DUZTEC_GRAPH_CLIENT_ID`, `DUZTEC_GRAPH_CLIENT_SECRET`, `DUZTEC_GRAPH_SENDER`.

No extra Python packages are needed; the transport uses the standard library. The access token is
cached in memory and refreshed automatically. Sent mail is not saved to the mailbox's Sent Items.

### 6.2 SMTP (other providers)
```yaml
auth:
  mail:
    method: "smtp"        # or leave auth.mail out entirely
  smtp:
    host: "smtp.zoho.in"
    port: 587             # 465 = implicit SSL, anything else = STARTTLS
    username: "office@duztec.in"
    password: "<app-specific password>"
    from_addr: "Duztec CRM <office@duztec.in>"
```

| Provider | host | port | Notes |
|---|---|---|---|
| Zoho Mail (India) | `smtp.zoho.in` | 587 | App-specific password required when 2FA is on |
| Google Workspace | `smtp.gmail.com` | 587 | Requires an App Password (2-Step Verification on) |
| Microsoft 365 | `smtp.office365.com` | 587 | Only if an admin enables "Authenticated SMTP" — Microsoft is retiring this; prefer `graph` |
| cPanel / shared hosting | `mail.duztec.in` | 587 or 465 | |

`DUZTEC_SMTP_PASSWORD=...` overrides whatever is in the YAML.

### 6.3 Test it *before* announcing the app
From `duztec_crm` with the venv active:
```
.venv\Scripts\python -m backend.check_smtp yourname@duztec.in
```
It prints the active method and the effective settings (secret masked), fetches a Graph token
when applicable, sends a test message, and on failure translates the provider's error code into
what to fix (wrong secret, missing admin consent, unlicensed sender, SMTP AUTH disabled…). Restart
the app after changing `config.local.yaml`, then do one real *First login / Forgot password* to
confirm end-to-end — the login card must say *"Code sent to your email."*, not the message about
the server log.

### 6.4 Deliverability
Send from a real mailbox on your own domain (`server@duztec.in`), so SPF/DKIM already pass.
Graph sends through Microsoft's own infrastructure, so the server's IP reputation does not matter.
Tell users to check Junk on the first login.

---

## 7. Making the CRM reachable for users

1. Give the server a **static LAN IP** (router DHCP reservation or a static address), e.g.
   `192.168.1.50`. Bookmarks break if this changes.
2. Allow inbound **TCP 8016** in Windows Defender Firewall (Private profile only):
   ```
   netsh advfirewall firewall add rule name="Duztec CRM 8016" dir=in action=allow protocol=TCP localport=8016 profile=private
   ```
3. Users open `http://192.168.1.50:8016/`.
4. Keep this on the **office LAN only**. Do not port-forward it to the internet — see §14.

---

## 8. Run automatically in the background

**Windows Task Scheduler** (recommended):
- Program: `C:\Duztec_Dashbaord\duztec_crm\run_crm_service.bat`
- Trigger: **At startup**
- "Run whether user is logged on or not", "Run with highest privileges"
- Settings: restart the task every 5 minutes if it fails, do not stop it on idle

`run_crm_service.bat` is the headless variant (no browser popup, no `pause`). It writes
`data\logs\service.log`.

Also set: BIOS "restore power on AC loss" = ON · Windows sleep/hibernate = OFF ·
Windows Update restart window at night.

**Linux** `/etc/systemd/system/duztec-crm.service`:
```ini
[Unit]
Description=Duztec Sales CRM
After=network.target

[Service]
WorkingDirectory=/opt/Duztec_Dashbaord/duztec_crm
ExecStart=/opt/Duztec_Dashbaord/duztec_crm/.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8016
Restart=always
User=duztec

[Install]
WantedBy=multi-user.target
```

---

## 9. Backups — set this up on day one

The system is two things on disk: the database `duztec_crm\data\crm.db` **and the uploaded
documents folder `duztec_crm\data\uploads\`**. A backup that has one without the other is incomplete —
the database rows would point at files that no longer exist.

- **In-app:** Dashboard → *Backup database* (or `POST /api/backup`) writes a consistent copy
  into `data\backup\crm_YYYYMMDD_HHMMSS.db` (database only).
- **Nightly:** schedule `backup_crm.bat` (Task Scheduler, daily ~20:00). It creates a
  timestamped database copy, prunes copies older than 30 days, and mirrors `data\uploads\`
  into `data\backup\uploads\`.
- **Disk space:** drawings and PDFs add up — size the server disk for the documents folder
  (25 MB per file limit by default, `uploads.max_mb` in config).
- **Off-machine:** weekly, copy `data\backup\` to a USB drive or cloud folder kept elsewhere.
  A backup on the same disk does not survive disk failure, theft or fire.
- **Test a restore once:** stop the app, replace `crm.db` with a backup, start, log in, confirm
  the data is there. An untested backup is not a backup.

---

## 10. Updating the app from git

```
cd C:\Duztec_Dashbaord
git pull
cd duztec_crm
.venv\Scripts\python -m pip install -r backend\requirements.txt
```
Then restart the app (or the scheduled task).

`data\` and `config.local.yaml` are git-ignored, so **your data and settings survive a pull**.
Schema changes are applied automatically at startup (`db.init()` adds missing columns).
Take a backup before pulling anyway — it costs seconds.

---

## 11. Day-to-day administration

- **Add a sales engineer:** Users tab → *+ Add User* → Duztec email, name, unique RKZ code,
  role *Sales engineer*. On first login they click *First login / Forgot password*, verify the
  emailed code and choose a password. The Users tab shows whether each password is set.
- **Deactivate someone:** Users tab → *Deactivate*. Their sessions are killed instantly.
- **Assign old records to an RKZ:** the ✎ buttons on Quotations rows, the Orders RKZ column, or
  *Assign RKZ* on an enquiry card. The picker lists active users' codes.
- **Check coverage:** Users tab → *RKZ Coverage* shows per-code counts and the **Unassigned**
  row (records no engineer can see).
- **Customer locations:** Customers tab → ✎ next to State/Pincode. The dashboard map plots
  pincodes; the legend shows how many records still lack one.

---

## 12. Configuration reference (`config.yaml`)

| Key | Purpose |
|---|---|
| `app.port` | HTTP port (8016) |
| `company.*` | Letterhead: address, CIN, **GSTIN**, bank details, home state (drives CGST/SGST vs IGST) |
| `numbering.*` | `ENQ-2627-` prefix, quotation prefix `Q` and padding |
| `quotation_defaults.*` | Validity days, GST %, delivery/payment terms, notes |
| `auth.allowed_domain` | `duztec.in` — only this domain may be added as users |
| `auth.admin_emails` | Seeded admins; also the explicit exceptions to the domain rule |
| `auth.rkz_codes` | Seed RKZ code per admin email |
| `auth.session_hours` | Login validity (168 h = 7 days) |
| `auth.otp_minutes` | Validity of the emailed login code, minutes (10) |
| `auth.smtp.*` | Mail server — **override in `config.local.yaml`** |
| `geo.pincode_keywords` | Plant/city keyword → pincode, used to auto-place customers on the map |
| `geo.state_keywords` | Keyword → state, used when a customer's state is blank |
| `paths.*` | db / logs / backup / MIS import file |

---

## 13. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Please log in." with no login box | Browser cached an old page. Hard-reload: Ctrl+F5 (Windows), ⌥⌘R (Safari). |
| No login-code email arrives | Run `python -m backend.check_smtp you@duztec.in`; check spam; confirm app-password and port. |
| "This email is not registered" | Ask an admin to add the user in the Users tab. |
| "Only duztec.in email addresses can be added" | By design. Exceptions must be listed in `auth.admin_emails`. |
| Engineer sees no data | Their records have no RKZ, or their RKZ is unset. Users tab → RKZ Coverage → assign. |
| Port 8016 already in use | Another copy is running. Close it, or change the port in `config.local.yaml`. |
| Users cannot reach the server | Firewall rule (§7.2), static IP, and the app must bind `0.0.0.0` (the launchers do). |
| Quotation PDF has placeholder GSTIN | Set the real GSTIN and bank details (§12). |
| App won't start after a pull | `pip install -r backend\requirements.txt`; check `data\logs\app.log` for the traceback. |

Logs: `data\logs\app.log` (rotating, 1 MB × 5). Every login, status change and RKZ assignment is
also recorded in the in-app activity feed on the dashboard.

---

## 14. Security posture and known limitations

- **LAN-only by design.** There is no HTTPS, no rate-limited public endpoint and no WAF.
  Do not expose port 8016 to the internet. For remote access use a VPN into the office network.
- Authentication is email + password (salted PBKDF2-SHA256, 600k iterations). 5 wrong passwords
  lock the account for 15 minutes. Setting or resetting a password needs a code emailed to the
  user and signs out their other devices. Sessions are HTTP-only cookies valid 7 days. Anyone with
  access to the server's log file can read verification codes while SMTP
  is unconfigured — another reason to complete §6 before rollout.
- Admins can see all data; engineers are restricted by RKZ at the API level (not just the UI).
- Quotation numbering is sequential and shared; two people creating quotations at the exact same
  second is fine (SQLite serialises writes), but this is a single-server design.
- SQLite suits this workload (tens of users, thousands of rows). If it ever outgrows that,
  `db.py` is the only module that needs to change to move to PostgreSQL.

---

## 15. Pre-production checklist

- [ ] `crm.db` copied from the old machine and verified (customer/quotation counts match)
- [x] `config.local.yaml` created with working mail — `check_smtp` passes (production server: Microsoft
      Graph, app "Duztec CRM Mailer", sender server@duztec.in; internal and external delivery verified 2026-09-28)
- [ ] **Rotate the Graph client secret before it expires — created 2026-09-28, 24 months → expires
      ~2028-09-28.** Entra → App registrations → Duztec CRM Mailer → Certificates & secrets → New client
      secret → update `auth.mail.graph.client_secret` in the server's `config.local.yaml` → restart the
      "Duztec CRM" task → run `check_smtp` → delete the old secret. Set a calendar reminder ~2028-08.
- [ ] ApplicationAccessPolicy restricting the app to server@duztec.in created (§6.1 step 5) and
      `Test-ApplicationAccessPolicy` shows Granted — until then the app may send as any duztec.in mailbox
- [ ] Real **GSTIN**, bank details and standard terms filled in (quotations are legal documents)
- [ ] One real first login (emailed code → set password) completed by someone who is *not* on the server
- [ ] Static IP set, firewall rule added, users can reach `http://<ip>:8016/`
- [ ] Task Scheduler entry created; server rebooted once to prove it comes back up
- [ ] Nightly backup job scheduled **and a restore tested**
- [ ] Off-machine backup location agreed
- [ ] Sales engineers added with RKZ codes; "Unassigned" count in RKZ Coverage reviewed
- [ ] Test users removed/deactivated (`sales@duztec.in`, `ag@duztec.in` were created during testing)

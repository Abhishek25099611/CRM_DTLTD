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
| Enquiries | Punch-in form (`ENQ-2627-###`), duplicate warning, kanban New/Qualified/Quoted/Closed |
| Quotations | Line items with HSN/qty/rate/GST, CGST+SGST vs IGST, discount, revisions (`Q00xxx-B`), letterhead print → PDF |
| Orders | Created automatically when a quotation is marked **Won** (captures customer PO) |
| Customers | Master with GSTIN, state, pincode, contacts |
| Follow-ups | Dated reminders with due/overdue list |
| Dashboard | KPIs, funnel, quotations-by-month, **India map** (pincode bubbles or state heat) |
| Users | OTP login, admin/engineer roles, **RKZ codes** with per-engineer data isolation |
| Export | Excel export of every register; one-click SQLite backup |

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
    │   ├── auth.py               OTP login, sessions, user management, send_mail()
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
- Outbound TCP **587** (or 465) open for sending OTP emails

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
3. **With SMTP working**, the 6-digit code arrives by email.
   **Without SMTP**, it is written to `data\logs\app.log` — find it with:
   ```
   findstr "LOGIN OTP" data\logs\app.log
   ```
4. Enter the code. The session lasts 7 days per browser.
5. Go to the **Users** tab → add each sales engineer with a unique **RKZ code**.

### 5.7 Linux alternative
```
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8016
```
Use a systemd unit instead of Task Scheduler (§8).

---

## 6. Email (SMTP) configuration — required for real users

Until SMTP is configured the app still works, but login codes go only to the server log —
meaning **only someone with access to the server can log in**. Configure it before rollout.

### 6.1 Settings
Edit `config.local.yaml`:
```yaml
auth:
  smtp:
    host: "smtp.zoho.in"
    port: 587
    username: "office@duztec.in"
    password: "<app-specific password>"
    from_addr: "Duztec CRM <office@duztec.in>"
```

| Provider | host | port | Notes |
|---|---|---|---|
| Zoho Mail (India) | `smtp.zoho.in` | 587 | App-specific password required when 2FA is on |
| Zoho Mail (global) | `smtp.zoho.com` | 587 | |
| Google Workspace | `smtp.gmail.com` | 587 | Requires an App Password (2-Step Verification on) |
| Microsoft 365 | `smtp.office365.com` | 587 | "Authenticated SMTP" must be enabled for the mailbox |
| cPanel / shared hosting | `mail.duztec.in` | 587 or 465 | |

**Port rule:** 465 = implicit SSL, anything else (normally 587) = STARTTLS. Both are supported.

Prefer an environment variable to keep the password out of files entirely:
`DUZTEC_SMTP_PASSWORD=...` overrides whatever is in the YAML.

### 6.2 Test it *before* announcing the app
From `duztec_crm` with the venv active:
```
.venv\Scripts\python -m backend.check_smtp yourname@duztec.in
```
It prints the effective settings, sends a test message, and on failure lists the likely cause
(wrong port, app-password needed, SMTP AUTH disabled, firewall). Restart the app after changing
config so it picks the new values up, then do one real OTP login to confirm end-to-end.

### 6.3 Deliverability
Send from a real mailbox on your own domain (`office@duztec.in`), not a spoofed address, so
SPF/DKIM already pass. Tell users to check spam on the first login.

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

The entire database is one file: `duztec_crm\data\crm.db`.

- **In-app:** Dashboard → *Backup database* (or `POST /api/backup`) writes a consistent copy
  into `data\backup\crm_YYYYMMDD_HHMMSS.db`.
- **Nightly:** schedule `backup_crm.bat` (Task Scheduler, daily ~20:00). It creates a
  timestamped copy and prunes copies older than 30 days.
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
  role *Sales engineer*. They can log in immediately via OTP.
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
| `auth.otp_minutes` | OTP validity (10) |
| `auth.smtp.*` | Mail server — **override in `config.local.yaml`** |
| `geo.pincode_keywords` | Plant/city keyword → pincode, used to auto-place customers on the map |
| `geo.state_keywords` | Keyword → state, used when a customer's state is blank |
| `paths.*` | db / logs / backup / MIS import file |

---

## 13. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Please log in." with no login box | Browser cached an old page. Hard-reload: Ctrl+F5 (Windows), ⌥⌘R (Safari). |
| No OTP email arrives | Run `python -m backend.check_smtp you@duztec.in`; check spam; confirm app-password and port. |
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
- Authentication is email OTP; sessions are HTTP-only cookies valid 7 days. There are no
  passwords to leak, but anyone with access to the server's log file can read OTPs while SMTP
  is unconfigured — another reason to complete §6 before rollout.
- Admins can see all data; engineers are restricted by RKZ at the API level (not just the UI).
- Quotation numbering is sequential and shared; two people creating quotations at the exact same
  second is fine (SQLite serialises writes), but this is a single-server design.
- SQLite suits this workload (tens of users, thousands of rows). If it ever outgrows that,
  `db.py` is the only module that needs to change to move to PostgreSQL.

---

## 15. Pre-production checklist

- [ ] `crm.db` copied from the old machine and verified (customer/quotation counts match)
- [ ] `config.local.yaml` created with working SMTP — `check_smtp` passes
- [ ] Real **GSTIN**, bank details and standard terms filled in (quotations are legal documents)
- [ ] One real OTP login completed by someone who is *not* on the server
- [ ] Static IP set, firewall rule added, users can reach `http://<ip>:8016/`
- [ ] Task Scheduler entry created; server rebooted once to prove it comes back up
- [ ] Nightly backup job scheduled **and a restore tested**
- [ ] Off-machine backup location agreed
- [ ] Sales engineers added with RKZ codes; "Unassigned" count in RKZ Coverage reviewed
- [ ] Test users removed/deactivated (`sales@duztec.in`, `ag@duztec.in` were created during testing)

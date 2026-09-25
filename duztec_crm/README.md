# Duztec Sales CRM (port 8016)

The active Duztec application: enquiry punch-in → quotation generation (letterhead PDF, GST,
revisions) → follow-ups → orders, with password login (emailed code to set/reset), per-engineer
RKZ data scoping, region heat map and Excel import/export. FastAPI + SQLite + vanilla JS, Duztec
branding throughout.

Deploying or operating the server? Read `../HANDOFF.md` — it is the authoritative guide.

## Layout

```
duztec_crm/
├── config.yaml               shared runtime config (in git): company/letterhead text, numbering,
│                             quotation defaults, geo keywords, auth (admins, RKZ seeds)
├── config.local.example.yaml template for config.local.yaml — machine-specific secrets
│                             (SMTP password, real GSTIN, bank details) [config.local.yaml is gitignored]
├── run_dashboard.bat         interactive launcher (creates .venv, installs, opens browser, starts uvicorn)
├── run_crm_service.bat       headless launcher for Task Scheduler (logs to data/logs/service.log)
├── backup_crm.bat            nightly backup job: timestamped copy of crm.db, 30-day retention
├── backend/
│   ├── main.py               app factory: middleware (login gate), startup, router mounting, static
│   ├── config.py             config.yaml <- config.local.yaml <- env vars -> Settings singleton + logging
│   ├── db.py                 SQLite schema, connection, numbering, state backfill, backup
│   ├── auth.py               password login, emailed-code set/reset, sessions, user management, send_mail()
│   ├── check_smtp.py         standalone "does email work?" test
│   ├── schemas.py            Pydantic request models
│   ├── services.py           shared logic: RKZ scoping, quotation totals, geo aliases
│   ├── routes_dashboard.py   /api/health /api/config /api/summary /api/geo
│   ├── routes_customers.py   customers + contacts CRUD
│   ├── routes_enquiries.py   enquiry punch-in + statuses
│   ├── routes_quotations.py  builder, revisions, won/lost, letterhead print
│   ├── routes_operations.py  orders, follow-ups, assign-rkz, rkz-overview, Excel export, backup
│   ├── import_mis.py         one-time MIS 2026-27.xlsx opening-data import (skipped if file absent)
│   ├── print_quote.py        quotation -> print HTML (letterhead, GST split, amount-in-words)
│   └── pincodes.json         Indian pincodes -> lat/lon (offline geocoding for the map)
├── frontend/
│   ├── index.html            SPA shell + login overlay (password / first login / forgot password)
│   ├── crm.js                all views (dashboard/enquiries/quotations/orders/customers/
│   │                         follow-ups/users) — single file by design (no build step)
│   ├── charts.js             dependency-free SVG charts (bars/hbars/stacked + heat map helpers)
│   ├── style.css             Duztec theme tokens + components
│   ├── india_states.json     simplified state polygons for the heat map (59 KB)
│   └── duztec-logo.png / duztec-mark.png
└── data/                     crm.db (SQLite, WAL) · logs/ · backup/   [gitignored]
```

## Run
`run_dashboard.bat` (Windows, interactive) or, from this folder:
```
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
.venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8016
```
On the server the CRM runs unattended via Task Scheduler (`run_crm_service.bat`) — see HANDOFF.md §8.

## Operating notes
- **Login**: email + password, only for users an admin has added (@duztec.in, plus the admin
  exceptions listed in config.yaml). On first login — or after forgetting the password — the user
  clicks **First login / Forgot password**, receives a 6-digit code by email and sets a password
  (min. 8 characters). A reset signs out the user's other devices. 5 wrong passwords lock the
  account for 15 minutes. Passwords are stored as salted PBKDF2-SHA256 hashes.
- **Email (SMTP)**: configured in `config.local.yaml` (or `DUZTEC_SMTP_*` env vars). Test with
  `.venv\Scripts\python -m backend.check_smtp you@duztec.in`. If sending fails, the code is written
  to `data/logs/app.log` (`findstr "LOGIN OTP" data\logs\app.log`) so only the server can log in.
- **Admins** (config-seeded): office@, vasanirs@ (RKZ RV), abhishek.ghumare@lechlerindia.com.
  Users tab: add engineers with unique RKZ codes; the Password column shows who has set one;
  the RKZ Coverage panel shows unassigned records.
- **Roles**: `admin` (everything) · `user` = sales engineer (own RKZ rows only; may edit own
  Drafts, locked once Sent) · `viewer` (sees everything, all writes refused by the middleware).
  Admins assign RKZ to old records via the ✎ buttons (dropdown of active users' codes) and can
  view login/logout history from the Users tab.
- **Enquiry Type** (Normal / Tender / Budgetary / Supporting / Repeat Order) lives in the
  enquiries `priority` column, is validated against `config.yaml → enquiry_types`, and is copied
  onto the quotation `type`.
- **Quotation text sections** (introduction, scope, warranty, guarantee) are pre-filled from
  `quotation_defaults` and printed on the letterhead; delivery/payment terms are multi-line.
- **Documents**: files attach to customers, enquiries, quotations and orders (`routes_documents.py`);
  stored under `data/uploads/<entity>/<id>/`, metadata in the `documents` table, served only to
  logged-in users and subject to RKZ scope. Limits/categories in `config.yaml → uploads`.
  **Back up `data/uploads` together with `crm.db`** (`backup_crm.bat` mirrors it).
- **48-hour SLA**: `services.working_hours_between` counts Mon–Sat 09:00–18:00 (`config.yaml → sla`)
  from enquiry punch-in (`created_at`) to the first `quotations.sent_at`; badges on enquiry cards,
  KPI tile on the dashboard.
- **End customer** lives on the customer master (`customers.end_customer`) and is shown on
  enquiries, quotations (printed), orders and the Lost tab.
- **Net / Total price** on the print: Net = qty × rate (before GST), Total = Net + GST; discount
  applies in the totals block only (Duztec's chosen definition).
- **Products master** (`routes_products.py`): code/name/HSN/unit/default rate/specification; seeded
  once from `config.yaml → products_seed` while empty; quotation lines link via
  `quotation_items.product_id` and the print adds a "Technical Specifications" block. Retire, never
  delete (lines keep the link).
- **Targets** (`routes_targets.py`): per user + measure + period (monthly/quarterly/yearly, start
  snapped to the 1st); achievement computed live from RKZ records (orders by PO date, quotations by
  `sent_at`, enquiries by date). Engineers see own (`/api/targets/mine`), admins the team overview.
- **Presence**: the browser posts `/api/auth/heartbeat` once a minute → `users.last_seen` →
  Active/Idle/Out on the Users tab (thresholds in `config.yaml → presence`). Measures "tab open",
  not work.
- **Monthly series** (`/api/summary → monthly`, last 12 months) feed the Monthly Funnel, Order Value
  Trend and Quotation-vs-Order charts (`charts.js` `grouped` / `line`, one ₹ scale — never dual-axis).
- **Testing without touching live data**: start a second instance with
  `DUZTEC_PORT=8026 DUZTEC_DB=/tmp/t.db DUZTEC_UPLOADS=/tmp/up DUZTEC_LOGS=/tmp/logs` pointing at a
  *copy* of `crm.db`.
- **Schema migrations**: `db.MIGRATIONS` adds missing columns at startup, so `git pull` + restart
  upgrades an existing database in place.
- **Numbering**: enquiries `ENQ-2627-001…`; quotations `Q` + 5 digits, never below
  `numbering.quote_start` (493 → first quotation Q00493), then highest existing + 1. Revisions
  add a letter suffix (`Q00493-B`) and do not advance the series.
- **Letterhead**: real GSTIN (27AAGCD9556R1ZN) and bank details go in `config.local.yaml`
  under `company:`, not config.yaml. Bank details are still to be filled in.
- **Backups**: dashboard button / `POST /api/backup`, plus `backup_crm.bat` scheduled nightly
  (20:00) → `data/backup` (database + mirror of `data/uploads`), 30-day retention. Copy that
  folder off-machine regularly.

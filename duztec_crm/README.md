# Duztec Sales CRM (port 8016)

The active Duztec application: enquiry punch-in → quotation generation (letterhead PDF, GST,
revisions) → follow-ups → orders, with OTP login, per-engineer RKZ data scoping, region heat map
and Excel import/export. FastAPI + SQLite + vanilla JS, Duztec branding throughout.

## Layout

```
duztec_crm/
├── config.yaml               ALL runtime config: company/GSTIN/letterhead text, numbering,
│                             quotation defaults, geo state-keywords, auth (admins, RKZ seeds, SMTP)
├── run_dashboard.bat         Windows launcher (creates .venv, installs, starts uvicorn)
├── backend/
│   ├── main.py               app factory: middleware (login gate), startup, router mounting, static
│   ├── config.py             YAML -> Settings singleton + logging
│   ├── db.py                 SQLite schema, connection, numbering, state backfill, backup
│   ├── auth.py               OTP login, sessions, user management (admin), RKZ codes
│   ├── schemas.py            Pydantic request models
│   ├── services.py           shared logic: RKZ scoping, quotation totals, geo aliases
│   ├── routes_dashboard.py   /api/health /api/config /api/summary /api/geo
│   ├── routes_customers.py   customers + contacts CRUD
│   ├── routes_enquiries.py   enquiry punch-in + statuses
│   ├── routes_quotations.py  builder, revisions, won/lost, letterhead print
│   ├── routes_operations.py  orders, follow-ups, assign-rkz, rkz-overview, Excel export, backup
│   ├── import_mis.py         one-time MIS 2026-27.xlsx opening-data import
│   └── print_quote.py        quotation -> print HTML (letterhead, GST split, amount-in-words)
├── frontend/
│   ├── index.html            SPA shell + login overlay
│   ├── crm.js                all views (dashboard/enquiries/quotations/orders/customers/
│   │                         follow-ups/users) — single file by design (no build step)
│   ├── charts.js             dependency-free SVG charts (bars/hbars/stacked + heat map helpers)
│   ├── style.css             Duztec theme tokens + components
│   ├── india_states.json     simplified state polygons for the heat map (59 KB)
│   └── duztec-logo.png / duztec-mark.png
└── data/                     crm.db (SQLite, WAL) · logs/ · backup/   [gitignored]
```

## Run
`run_dashboard.bat` (Windows) or
`python -m uvicorn backend.main:app --host 0.0.0.0 --port 8016` from this folder
(dev machine uses the shared venv at `../.venv-dashboards`).

## Operating notes
- **Login**: OTP to @duztec.in emails (+ explicitly listed admin exceptions). Until `auth.smtp`
  is filled in config.yaml, codes are written to `data/logs/app.log` (dev mode).
- **Admins** (config-seeded): office@, vasanirs@ (RKZ RV), abhishek.ghumare@lechlerindia.com.
  Users tab: add engineers with unique RKZ codes; RKZ Coverage panel shows unassigned records.
- **Roles**: `admin` (everything) · `user` = sales engineer (own RKZ rows only; may edit own
  Drafts, locked once Sent) · `viewer` (sees everything, all writes refused by the middleware).
  Admins assign RKZ to old records via the ✎ buttons (dropdown of active users' codes) and can
  view login/logout history from the Users tab.
- **Enquiry Type** (Normal / Tender / Budgetary / Supporting / Repeat Order) lives in the
  enquiries `priority` column, is validated against `config.yaml → enquiry_types`, and is copied
  onto the quotation `type`.
- **Quotation text sections** (introduction, scope, warranty, guarantee) are pre-filled from
  `quotation_defaults` and printed on the letterhead; delivery/payment terms are multi-line.
- **Schema migrations**: `db.MIGRATIONS` adds missing columns at startup, so `git pull` + restart
  upgrades an existing database in place.
- **Before real quotations**: replace the GSTIN placeholder, bank details and default terms in
  config.yaml.
- **Backups**: dashboard button / POST /api/backup writes to data/backup — schedule nightly + copy
  off-machine.
- Archived sibling dashboards (bills/ops/MIS/pending-PO/PO-details) live in `../_archive/` with
  their own README — restore by moving a folder back and running its launcher.

# Prompt for Claude Code on the Duztec server — pull Phase 4 + switch email to Microsoft Graph

The server is already on `main` (it pushed `EMAIL_OTP_ISSUE.md` there). `main` now also carries
Phase 4 (project specification, net-first values, T&C, order contact/delivery date) and the
**Microsoft Graph mail transport** requested in that brief. This prompt pulls both, restarts, and
configures Graph once a Microsoft 365 admin has created the app registration (HANDOFF.md §6.1).
Copy everything between the lines into Claude Code **running on the server**, in the repository
folder. Do not put the client secret in this file — paste it only when the session asks for it.

---

```
You are updating the Duztec Sales CRM that is already running on this machine (port 8016, Task
Scheduler / run_crm_service.bat, config.local.yaml holds the real GSTIN and the SMTP block).
Read HANDOFF.md first — especially §6 (email) and §10 (updating). Two jobs, in this order:
(A) pull the latest main and restart; (B) switch outgoing mail to the Microsoft Graph transport
that was built in response to your EMAIL_OTP_ISSUE.md brief. Tell me the result of each step
before moving on. Never print a secret back to me in full and never commit config.local.yaml.

========================= PART A — PULL AND RESTART =========================

1. SAFETY FIRST
   - `git status` and `git branch --show-current`: expect main, clean tree. If there are
     uncommitted changes, STOP and show me; do not stash, reset or discard.
   - Run duztec_crm\backup_crm.bat (or copy data\crm.db and data\uploads to
     data\backup\pre-update-<date>) and show me the file names.

2. PULL
   - git pull origin main
   - `git log --oneline -5` must show "CRM Phase 4: project spec, supporting exclusion, ..." and
     the "Microsoft Graph mail transport" commit above your "Add EMAIL_OTP_ISSUE.md" commit.
   - No new Python packages are needed (the Graph transport is standard library), but run
     .venv\Scripts\python -m pip install -r duztec_crm\backend\requirements.txt anyway and
     report the output.

3. RESTART AND VERIFY PHASE 4
   - Restart the scheduled task; confirm http://127.0.0.1:8016/api/health is ok.
   - In data\logs\app.log expect seven "Migration: added ..." lines (enquiries.technical,
     quotations.end_customer / additional_description / terms_conditions,
     orders.contact_name / contact_phone / contact_email). Any traceback: show it verbatim.
   - Log in and check, telling me exactly what you see:
       a. New Enquiry form has a "Technical" box under Enquiry type.
       b. Quotations tab: "Project specification" filter (Tender / Technical / Supporting / Other),
          "Project spec." column, "Net value (excl. GST)" column, end customer under the customer.
       c. New Quotation form: Project specification, End customer (pre-filled from the customer),
          Introduction, Scope, Warranty, Additional description, Terms & Conditions (numbered
          default text). Guarantee / Delivery terms / Payment terms / Notes boxes are gone.
       d. Print an existing quotation: the totals block shows "Net Total (excluding GST)"
          highlighted, then CGST/SGST (or IGST), then "Total including GST" in a lighter row;
          the old delivery/payment terms appear as a numbered Terms & Conditions list.
       e. Dashboard: Pipeline / Lost tiles say "net, excl. GST"; if any quotation is Supporting,
          the pipeline tile says "N supporting excluded".
       f. Orders tab: "Contact person" and "Delivery date" columns; Edit shows contact
          name/phone/email and delivery date.

========================= PART B — EMAIL VIA MICROSOFT GRAPH =========================

4. WHAT A MICROSOFT 365 ADMIN MUST DO FIRST (not on this machine)
   Show me HANDOFF.md §6.1 steps 1–5 and ask me for the three values once they exist:
     - Directory (tenant) ID, Application (client) ID, and the client secret VALUE
     - confirm that Mail.Send (Application) has "Granted for duztec.in" and that the
       ApplicationAccessPolicy restricting the app to server@duztec.in was created.
   If I do not have them yet, stop here and tell me exactly what to ask the admin for.

5. CONFIGURE
   - In duztec_crm\config.local.yaml add (keep the existing company: and auth.smtp blocks):
       auth:
         mail:
           method: "graph"
           graph:
             tenant_id: "<tenant id>"
             client_id: "<client id>"
             client_secret: "<secret value — in double quotes>"
             sender: "server@duztec.in"
     YAML note: auth: already exists in that file — put mail: inside it, do not create a
     second auth: key. Confirm with `git status` that config.local.yaml is not listed.

6. TEST
   - .venv\Scripts\python -m backend.check_smtp office@duztec.in
     It must print "method : graph", "token OK" and "RESULT: SENT". On failure it prints a Hint
     line naming the fix (wrong secret, missing admin consent, unlicensed sender…) — show me the
     full output and do the matching thing; do not edit backend\ code.
   - Then .venv\Scripts\python -m backend.check_smtp abhishek.ghumare@lechlerindia.com
     (external address — Graph is not limited to the tenant). I will confirm both arrived.

7. APPLY AND VERIFY IN THE APP
   - Restart the scheduled task (config.local.yaml is read at startup).
   - Log out; enter a @duztec.in user's email → "First login / Forgot password" → "Send Code".
     The card must say "Code sent to your email." I will confirm the email arrived and that
     setting the password and logging in works.
   - grep data\logs\app.log for "Mail send failed" — there must be no new lines.

8. HAND BACK
   - Report: pull result, Phase 4 checks a–f, which mail method is active, whether external
     addresses receive codes, the client-secret expiry date (put it in HANDOFF.md §15 as a
     reminder to rotate), and anything still outstanding (bank details in config.local.yaml
     are still blank; HSN codes 8424 / 9987 in config.yaml → products_seed are guesses).
   - Commit only documentation you changed (e.g. HANDOFF.md §15) directly on main and push.

RULES
- Never commit secrets. config.local.yaml, data\ and .venv\ must stay out of git — check
  `git status` before every commit.
- Never overwrite or delete duztec_crm\data\crm.db or data\uploads. This server's database is
  the system of record; never copy a crm.db from another machine over it.
- Do not modify backend\ or frontend\ to work around a configuration problem. A genuine code
  bug: show me the traceback and the proposed fix first.
- Report failures verbatim rather than summarising them as "done".
```

---

## Notes for the person running this

- Part B needs someone with **Global Administrator** rights on duztec.in's Microsoft 365 to do
  HANDOFF.md §6.1 (app registration, Mail.Send permission with admin consent, client secret,
  access policy). Until that is done, Part A is still worth running — Phase 4 does not depend on it.
- The client secret expires (choose 24 months). Rotating it is: new secret in Entra → paste into
  config.local.yaml → restart. Note the expiry date somewhere visible.
- The old `auth.smtp` block can stay in `config.local.yaml`; it is ignored while `method: "graph"`.
- Bank details for the quotation letterhead are still blank in the server's `config.local.yaml`.

**Expected duration:** Part A 10 minutes; Part B 15 minutes once the admin values exist.

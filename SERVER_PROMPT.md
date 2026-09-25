# Prompt for Claude Code on the Duztec server — update to `main`

The CRM is already deployed on the server (port 8016, Task Scheduler, `config.local.yaml` holding the
SMTP password and the real GSTIN). The server-side work done on branch `duztec` (password login,
Q00493 numbering floor, backup .bat fix) has been **merged into `main` on GitHub together with the
Phase-2/3 features built on the development machine**. This prompt moves the server checkout to
`main` and restarts the app. Copy everything between the lines into Claude Code **running on the
server**, in the repository folder.

---

```
You are updating the Duztec Sales CRM that is already running on this machine. Read HANDOFF.md in
the repository root first — it is the authoritative deployment document. The branch `duztec` you
worked on earlier has been merged into `main` on GitHub (merge commit "Merge origin/duztec: password
login + Phase 2/3 features"). Your job is to switch this checkout to main, restart the app and
verify it. Tell me the result of each step before moving on.

1. SAFETY FIRST
   - Show `git status` and `git branch --show-current`. I expect branch `duztec` with a clean tree.
     If there are uncommitted changes, STOP and show them to me — do not stash, reset or discard.
   - Confirm config.local.yaml, data\ and .venv\ are ignored (`git status --ignored`).
   - Run duztec_crm\backup_crm.bat (or copy data\crm.db and data\uploads to
     data\backup\pre-update-<date>) and show me the resulting file names. Do not skip this.

2. SWITCH TO MAIN
   - git fetch origin
   - git checkout main
   - git pull origin main
   - Show `git log --oneline -8`. It must contain the merge commit above AND your own earlier
     commits (889a33d "Server deployment: password login…", 191d248 "README: document password
     login…"). If either is missing, STOP and tell me.
   - `git branch --merged main` should list `duztec`; if so delete the local branch
     (`git branch -d duztec`). Ask me before deleting it on GitHub.

3. DEPENDENCIES
   - .venv\Scripts\python -m pip install -r duztec_crm\backend\requirements.txt
     (python-multipart is new — it is needed for file uploads). Report install errors verbatim.

4. RESTART AND VERIFY
   - Restart the CRM the way it is scheduled (stop/start the Task Scheduler task or
     run_crm_service.bat). Check http://127.0.0.1:8016/api/health returns status ok.
   - In data\logs\app.log expect lines like "Migration: added …" and "Seeded 10 products from
     config" — new tables (documents, products, targets) and columns are created automatically.
     Any traceback: show it to me verbatim.
   - Log in with your existing email + password (passwords and users survive the update).
   - Check, and show me a screenshot or the exact text where you can:
       a. Users tab has Presence and Password columns, the Role dropdown offers Admin / Sales
          engineer / View only, and "Login history" opens.
       b. Products and Targets tabs exist (admins only for Targets).
       c. Dashboard shows "Quoted within 48h", Team Targets, and three monthly charts.
       d. A quotation print preview shows the REAL GSTIN from config.local.yaml, Net Price and
          Total Price columns, and the Introduction / Scope / Warranty / Guarantee sections.
       e. Quotation numbering is unchanged: next number = highest existing + 1 (never below 493).
   - Do one "First login / Forgot password" cycle for a test address to prove the code still
     arrives by EMAIL, then delete or deactivate that test user.

5. HAND BACK
   - Give me the current URL, the list of users and who has a password set, and anything the
     HANDOFF.md §15 checklist still lists as outstanding. Known open items: bank details in
     config.local.yaml are blank; HSN codes in config.yaml → products_seed (8424 / 9987) are
     guesses — accounts must confirm and edit them in the Products tab.

RULES
- Never commit secrets. config.local.yaml, data\ and .venv\ must stay out of git — check
  `git status` before every commit. crm.db is git-ignored on purpose; never force-add it.
- Never overwrite or delete duztec_crm\data\crm.db or data\uploads. This server's database is the
  system of record — do NOT copy a crm.db from any other machine over it.
- Do not modify files under backend\ or frontend\ to work around a configuration problem; fix the
  configuration. If you believe there is a genuine code bug, show me the traceback and your
  proposed fix before changing anything.
- From now on commit server-side changes directly on main in small commits and push promptly, so
  the two machines never diverge again. Do not create long-lived branches.
- Report failures verbatim rather than summarising them as "done".
```

---

## Notes for the person running this

- The server database is the live one. The development Mac only holds test data now — never copy
  its `crm.db` to the server again.
- After the update, users who already had a password keep it. Anyone added later uses
  **First login / Forgot password** on the login screen to receive a code by email and choose one.
- The **Password** column on the Users tab tells you who has not set a password yet.
- Still to be filled on the server, in `config.local.yaml` under `company:`: bank details for the
  quotation letterhead.
- If you are on Linux instead of Windows: use the systemd unit and cron job from HANDOFF.md §5.7
  and §8 instead of Task Scheduler and the .bat files.

**Expected duration:** 10–15 minutes.

# Prompt for Claude Code on the Duztec server

Copy everything between the lines below into Claude Code **running on the server machine**, in the
folder where you cloned the repository. Fill in the four bracketed values first.

---

```
You are setting up the Duztec Sales CRM on this machine so office users can access it over the LAN.
Read HANDOFF.md in the repository root first — it is the authoritative deployment document and
explains the architecture, the data model and every configuration key. Follow it, and ask me
before doing anything it does not cover.

ENVIRONMENT (fill these in before pasting):
- Repo cloned at: [C:\Duztec_Dashbaord]
- This server's static LAN IP: [192.168.1.50]
- Mail provider for duztec.in: [Zoho / Google Workspace / Microsoft 365 / cPanel]
- SMTP mailbox to send from: [office@duztec.in]   (I will paste the app password when you ask)

WHAT THE APP IS
A FastAPI + SQLite + vanilla-JS internal CRM: enquiry punch-in, quotation generation with GST and a
letterhead PDF, orders, follow-ups, a dashboard with an India map, OTP login restricted to
@duztec.in, and per-sales-engineer data isolation by "RKZ" code. It listens on port 8016 and is
LAN-only by design. No build step, no external services.

DO THESE TASKS IN ORDER, and tell me the result of each before moving on:

1. VERIFY THE CHECKOUT
   - Confirm Python 3.11+ and git are installed and on PATH.
   - Confirm the repo contains duztec_crm/ with backend/, frontend/, config.yaml and HANDOFF.md.
   - Do NOT run any dashboard from _archive/ if that folder exists; only duztec_crm is in use.

2. RESTORE THE LIVE DATABASE  (critical — do this BEFORE the first start)
   - The database file duztec_crm/data/crm.db holds all customers, quotations, orders, users and
     RKZ assignments. I will copy it onto this machine; tell me the exact path to put it at.
   - After I confirm it is in place, verify it by counting rows in the customers, quotations,
     orders and users tables, and show me the counts. Expect roughly 63 customers, 76 quotations,
     28 orders, 5 users. If the file is missing or the counts are zero, STOP and tell me —
     do not let the app create an empty database and do not run the MIS import.

3. INSTALL DEPENDENCIES
   - Create the virtual environment and install backend/requirements.txt (run_dashboard.bat does
     this automatically, or do it manually). Report any install errors verbatim.

4. CONFIGURE EMAIL  (this is the main reason for this session)
   - Copy config.local.example.yaml to config.local.yaml.
   - Ask me for the SMTP app password, then write the auth.smtp block: host, port, username,
     password, from_addr for my provider. Remember: port 465 = implicit SSL, 587 = STARTTLS.
   - NEVER commit config.local.yaml or print the password back to me in full.
   - Test it with:  python -m backend.check_smtp <my-email>
     Show me the full output. If it fails, diagnose it (wrong port, app-password required,
     SMTP AUTH disabled for the mailbox, outbound firewall) and retry until a test email
     actually arrives — I will confirm receipt.

5. FILL IN THE LEGAL/LETTERHEAD DETAILS
   - config.yaml still carries a placeholder GSTIN ("27XXXXXXXXXXXXX") and blank bank details.
     Ask me for the real GSTIN, bank details and any standard delivery/payment terms, and put
     them in config.local.yaml (not config.yaml, so git pull stays clean).
   - Generate one quotation print preview afterwards and show me that the letterhead is correct.

6. START THE APP AND VERIFY
   - Start it bound to 0.0.0.0 on port 8016.
   - Check http://127.0.0.1:8016/api/health returns status ok.
   - Do one real OTP login end-to-end and confirm the code arrived by EMAIL (not the log file).
   - Confirm the dashboard loads with the expected KPI numbers and that the Users tab lists the
     three admins: office@duztec.in, vasanirs@duztec.in, abhishek.ghumare@lechlerindia.com.

7. MAKE IT REACHABLE FOR USERS
   - Confirm this machine has a static LAN IP (or a DHCP reservation) and tell me what it is.
   - Add a Windows Firewall inbound rule for TCP 8016, PRIVATE profile only.
   - Verify from another device on the network that http://<ip>:8016/ shows the login page.
   - Do NOT port-forward this to the internet or expose it publicly. If remote access is needed,
     tell me it requires a VPN instead.

8. RUN IT AUTOMATICALLY
   - Create a Task Scheduler task running duztec_crm\run_crm_service.bat at startup, "run whether
     user is logged on or not", with restart-on-failure.
   - Reboot the machine and prove the CRM comes back up on its own.

9. BACKUPS
   - Schedule backup_crm.bat daily (about 20:00). It writes a timestamped copy into data\backup
     and prunes copies older than 30 days.
   - Then TEST A RESTORE: stop the app, swap in a backup copy, start it, confirm the data is
     intact, and restore the live file afterwards. Report exactly what you did.
   - Tell me what off-machine backup location you recommend and how to automate copying there.

10. HAND BACK
    - Give me: the URL users should bookmark, the admin emails, where logs live, how to add a
      sales engineer with an RKZ code, and how to update the app later (git pull + pip install +
      restart).
    - List anything from the HANDOFF.md §15 pre-production checklist that is still outstanding.

RULES
- Never commit secrets. config.local.yaml, data/ and .venv/ must stay out of git — verify with
  `git status` that they are ignored before any commit.
- Never overwrite or delete duztec_crm/data/crm.db. Back it up before anything risky.
- Do not modify files under backend/ or frontend/ to work around a configuration problem; fix the
  configuration. If you believe there is a genuine code bug, show me the traceback and your
  proposed fix before changing anything.
- Report failures verbatim rather than summarising them as "done".
```

---

## Notes for the person running this

**Before you start**, make sure you have:
1. The `crm.db` file from the current machine (`duztec_crm/data/crm.db`) on a USB stick or share.
2. The SMTP app password for the sending mailbox.
3. The real GSTIN and bank details for quotation letterheads.
4. Admin rights on the server (Task Scheduler and firewall rules need them).

**If you are deploying to Linux instead of Windows**, add this line to the prompt:
`This is a Linux server — use a systemd unit instead of Task Scheduler and a cron job instead of
the .bat backup script; HANDOFF.md §5.7 and §8 cover both.`

**Expected duration:** about 30–60 minutes, most of it waiting on SMTP credentials and the reboot test.

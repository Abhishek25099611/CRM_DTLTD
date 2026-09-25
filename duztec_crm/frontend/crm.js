/* Duztec Sales CRM frontend. Single file by design (no build step). */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const today = () => new Date().toISOString().slice(0, 10);
  let CFG = null, view = 'dash', customersCache = [];

  function inr(v) { v = Math.round((v || 0) * 100) / 100; const neg = v < 0; v = Math.abs(v);
    let s = Math.floor(v).toString();
    if (s.length > 3) { let h = s.slice(0, -3), t = s.slice(-3), p = []; while (h.length > 2) { p.unshift(h.slice(-2)); h = h.slice(0, -2); } if (h) p.unshift(h); s = p.join(',') + ',' + t; }
    return (neg ? '-' : '') + s; }
  const money = v => '₹ ' + inr(v);
  const short = v => (window.DzCharts ? window.DzCharts.short(v) : inr(v));
  const fmtSize = b => b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : b > 1024 ? Math.round(b / 1024) + ' KB' : b + ' B';

  function flash(msg, ok = true) { const b = $(ok ? 'ok-box' : 'error-box'); b.textContent = msg; b.classList.remove('hidden'); setTimeout(() => b.classList.add('hidden'), ok ? 3500 : 8000); }
  async function handle(r, path) {
    if (r.status === 401 && !path.startsWith('/api/auth/')) { showLogin(); throw new Error('Please log in.'); }
    if (!r.ok) { let d; try { d = (await r.json()).detail; } catch (e) { d = { detail: r.statusText }; } throw new Error(typeof d === 'string' ? d : d.detail); }
    return r.json();
  }
  async function api(path, opts = {}) {
    if (opts.body) { opts.method = opts.method || 'POST'; opts.headers = { 'Content-Type': 'application/json' }; opts.body = JSON.stringify(opts.body); }
    return handle(await fetch(path, opts), path);
  }
  async function apiForm(path, formData) { return handle(await fetch(path, { method: 'POST', body: formData }), path); }

  // ================= auth =================
  let ME = null;
  const isAdmin = () => !!(ME && ME.role === 'admin');
  function showLogin() { $('login-overlay').classList.remove('hidden'); }
  function hideLogin() { $('login-overlay').classList.add('hidden'); }
  function loginMsg(m, err) { const el = $('login-msg'); el.textContent = m; el.classList.toggle('login-msg-err', !!err); }
  async function initAuth() {
    try { ME = await api('/api/auth/me'); onLoggedIn(); return true; }
    catch (e) { showLogin(); return false; }
  }
  function onLoggedIn() {
    hideLogin();
    $('user-chip').classList.remove('hidden');
    const tag = ME.role === 'admin' ? ' (admin)' : ME.role === 'viewer' ? ' (view only)' : (ME.rkz ? ' (' + ME.rkz + ')' : '');
    $('user-email').textContent = ME.email + tag;
    if (isAdmin()) { $('nav-users').classList.remove('hidden'); $('nav-targets').classList.remove('hidden'); }
    document.body.classList.toggle('role-viewer', ME.role === 'viewer');   // hides every [data-write] control
    if (!window.__hb) {   // presence heartbeat: "CRM open in a browser", once a minute
      const ping = () => api('/api/auth/heartbeat', { method: 'POST' }).catch(() => {});
      ping(); window.__hb = setInterval(ping, 60000);
    }
  }
  $('login-send').onclick = async () => {
    const email = $('login-email').value.trim();
    loginMsg('Sending…');
    try {
      const r = await api('/api/auth/request-otp', { body: { email } });
      $('login-step1').classList.add('hidden'); $('login-step2').classList.remove('hidden');
      $('login-sent-to').textContent = email; $('login-code').value = ''; $('login-code').focus();
      loginMsg(r.message, !r.mailed);
    } catch (e) { loginMsg(e.message, true); }
  };
  $('login-verify').onclick = async () => {
    try {
      await api('/api/auth/verify', { body: { email: $('login-email').value.trim(), code: $('login-code').value.trim() } });
      loginMsg('');
      ME = await api('/api/auth/me'); onLoggedIn();
      CFG = await api('/api/config'); switchView('dash');
    } catch (e) { loginMsg(e.message, true); }
  };
  $('login-back').onclick = () => { $('login-step2').classList.add('hidden'); $('login-step1').classList.remove('hidden'); loginMsg(''); };
  $('login-code').addEventListener('keydown', e => { if (e.key === 'Enter') $('login-verify').click(); });
  $('login-email').addEventListener('keydown', e => { if (e.key === 'Enter') $('login-send').click(); });
  $('btn-logout').onclick = async () => { await api('/api/auth/logout', { method: 'POST' }); location.reload(); };

  const SP = { won: 'won', lost: 'lost', cold: 'cold', sent: 'sent', draft: 'draft', new: 'new', qualified: 'qualified', quoted: 'quoted', dropped: 'dropped',
               admin: 'won', user: 'sent', viewer: 'cold' };
  const pill = (st, label) => `<span class="status-pill ${SP[st] || 'open'}">${esc(label || st)}</span>`;
  const typePill = t => t ? `<span class="type-pill">${esc(t)}</span>` : '';
  const slaBadge = e => {
    if (!e || !e.sla || e.sla === 'na') return '';
    const h = e.hours == null ? '' : e.hours + 'h';
    const lbl = { ok: 'quoted in ' + h, late: 'quoted late · ' + h, open: h + ' of ' + e.limit + 'h', warn: h + ' · due soon', breach: h + ' · overdue' }[e.sla] || e.sla;
    return `<span class="sla sla-${e.sla}" title="Working hours (Mon–Sat 9–18) from punch-in to the first quotation sent · limit ${e.limit}h">${esc(lbl)}</span>`;
  };

  function openModal(title, html) { $('modal-title').textContent = title; $('modal-body').innerHTML = html; $('modal').classList.remove('hidden'); }
  function closeModal() { $('modal').classList.add('hidden'); }
  $('modal-close').onclick = closeModal;
  $('modal').addEventListener('click', e => { if (e.target === $('modal')) closeModal(); });

  async function loadCustomers() { customersCache = await api('/api/customers'); return customersCache; }
  const custOptions = sel => '<option value="">— select customer —</option>' + customersCache.map(c => `<option value="${c.id}" ${c.id == sel ? 'selected' : ''}>${esc(c.name)}${c.end_customer ? ' → ' + esc(c.end_customer) : ''}</option>`).join('');
  const stateOptions = sel => '<option value="">— select state —</option>' + (CFG.states || []).map(s => `<option ${s === sel ? 'selected' : ''}>${esc(s)}</option>`).join('');
  const typeOptions = sel => (CFG.enquiry_types || ['Normal']).map(t => `<option ${t === (sel || 'Normal') ? 'selected' : ''}>${esc(t)}</option>`).join('');
  const contactLabel = c => esc(c.name) + (c.designation ? ' — ' + esc(c.designation) : '') + (c.department ? ' (' + esc(c.department) + ')' : '');

  // ================= DOCUMENTS (shared panel) =================
  async function docsPanel(entityType, entityId, title, after) {
    const [docs, meta] = await Promise.all([api(`/api/documents?entity_type=${entityType}&entity_id=${entityId}`), api('/api/documents/categories')]);
    openModal('Documents — ' + title, `
      <div class="table-wrap doc-list"><table><thead><tr><th>File</th><th>Category</th><th>Note</th><th class="num">Size</th><th>Uploaded</th><th></th></tr></thead>
      <tbody>${docs.map(d => `<tr><td><a class="link" href="/api/documents/${d.id}/download">${esc(d.filename)}</a></td><td>${esc(d.category)}</td><td class="wrap">${esc(d.note)}</td>
        <td class="num">${fmtSize(d.size)}</td><td>${esc(d.uploaded_at.slice(0, 16))}<div class="muted small">${esc(d.uploaded_by)}</div></td>
        <td><button class="btn small danger" data-ddel="${d.id}" data-write>Delete</button></td></tr>`).join('') || '<tr class="empty"><td colspan="6">No documents yet</td></tr>'}</tbody></table></div>
      <div class="modal-form" data-write style="margin-top:12px;border-top:1px solid var(--line);padding-top:12px">
        <div class="full"><h3 style="margin:0">Upload a document</h3></div>
        <div><label>Category</label><select id="d-cat">${meta.categories.map(c => `<option>${esc(c)}</option>`).join('')}</select></div>
        <div><label>Note (optional)</label><input id="d-note" placeholder="e.g. costing sheet rev 2"></div>
        <div class="full doc-drop">Allowed: ${meta.allowed_extensions.join(', ')} · max ${meta.max_mb} MB<input type="file" id="d-file"></div>
        <div class="full"><button class="btn primary" id="d-up">Upload</button></div>
      </div>`);
    $('d-up').onclick = async () => {
      const f = $('d-file').files[0]; if (!f) return flash('Choose a file first', false);
      const fd = new FormData(); fd.append('entity_type', entityType); fd.append('entity_id', entityId); fd.append('category', $('d-cat').value); fd.append('note', $('d-note').value); fd.append('file', f);
      try { await apiForm('/api/documents', fd); flash('Uploaded ' + f.name); docsPanel(entityType, entityId, title, after); if (after) after(); }
      catch (e) { flash(e.message, false); }
    };
    document.querySelectorAll('[data-ddel]').forEach(b => b.onclick = async () => {
      if (!confirm('Delete this document? This cannot be undone.')) return;
      try { await api('/api/documents/' + b.dataset.ddel, { method: 'DELETE' }); flash('Document deleted'); docsPanel(entityType, entityId, title, after); if (after) after(); }
      catch (e) { flash(e.message, false); }
    });
  }

  // ================= DASHBOARD =================
  async function renderDash() {
    const s = await api('/api/summary');
    const enq = Object.fromEntries(s.enquiries.map(r => [r.status, r.n]));
    const openEnq = (enq.new || 0) + (enq.qualified || 0);
    const qs = Object.fromEntries(s.quotes.map(r => [r.status, r.n]));
    const sla = s.sla || {};
    $('view').innerHTML = `
      ${s.scope_rkz ? `<section class="card summary-strip">Showing only <b>RKZ ${esc(s.scope_rkz === '__UNASSIGNED__' ? '(none assigned — ask an admin)' : s.scope_rkz)}</b> data. Admins see all RKZ codes.</section>` : ''}
      <section class="kpis">
        <div class="kpi neutral"><div class="kpi-label">Open Enquiries</div><div class="kpi-value">${openEnq}</div><div class="kpi-sub">${s.enquiries_stale} idle &gt; 7 days</div></div>
        <div class="kpi ${sla.open_breach ? 'critical' : 'success'}"><div class="kpi-label">Quoted within ${sla.limit || 48}h</div><div class="kpi-value">${sla.pct_in_time == null ? '—' : sla.pct_in_time + '%'}</div><div class="kpi-sub">${sla.in_time || 0} in time · ${sla.late || 0} late · <b>${sla.open_breach || 0}</b> open overdue</div></div>
        <div class="kpi overdue"><div class="kpi-label">Pipeline Value</div><div class="kpi-value">${money(s.pipeline_value)}</div><div class="kpi-sub">${(qs.sent || 0) + (qs.draft || 0)} live quotations</div></div>
        <div class="kpi success"><div class="kpi-label">Won Orders</div><div class="kpi-value">${money(s.won_value)}</div><div class="kpi-sub"><b>${s.orders.n}</b> orders booked</div></div>
        <div class="kpi critical"><div class="kpi-label">Lost</div><div class="kpi-value">${money(s.lost_value)}</div><div class="kpi-sub"><b>${s.lost}</b> lost · quoted value incl. GST</div></div>
        <div class="kpi warning"><div class="kpi-label">Win Rate</div><div class="kpi-value">${s.win_rate_count}%</div><div class="kpi-sub">by count · <b>${s.win_rate_value}%</b> by value</div></div>
        <div class="kpi minor"><div class="kpi-label">Follow-ups Due</div><div class="kpi-value">${s.followups_due}</div><div class="kpi-sub">today or overdue</div></div>
      </section>
      <section class="card"><h2 id="tg-title">${isAdmin() ? 'Team Targets <span class="muted small">(running now)</span>' : 'My Targets'}</h2><div class="target-grid" id="tg-block"><span class="muted small">Loading…</span></div></section>
      <div class="grid-3">
        <section class="card chart-card"><h2>Monthly Funnel <span class="muted small">(12 months)</span></h2><div class="chart" id="ch-mfunnel"></div></section>
        <section class="card chart-card"><h2>Order Value Trend</h2><div class="chart" id="ch-otrend"></div></section>
        <section class="card chart-card"><h2>Quotation vs Order Value</h2><div class="chart" id="ch-qvo"></div></section>
      </div>
      <div class="grid-3">
        <section class="card chart-card"><h2>Funnel <span class="muted small">(all time)</span></h2><div class="chart" id="ch-funnel"></div></section>
        <section class="card chart-card"><h2>Quotations by Month</h2><div class="chart" id="ch-month"></div></section>
        <section class="card"><h2>Recent Activity</h2><ul class="act-list">${s.recent.map(a => `<li>${esc(a.at.slice(5, 16))} · <b>${esc(a.action)}</b> ${esc(a.entity_type)} ${esc(a.detail)}</li>`).join('') || '<li>None yet</li>'}</ul></section>
      </div>
      <div class="grid-2" style="margin-bottom:16px">
        <section class="card chart-card"><h2 style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px">Region Map
          <span style="display:flex;gap:6px;flex-wrap:wrap">
            <select id="map-metric" class="btn small" style="text-transform:none">
              <option value="enquiries">Enquiries</option><option value="offers" selected>Offers submitted</option><option value="won">Won orders</option></select>
            <select id="map-mode" class="btn small" style="text-transform:none">
              <option value="n">By count</option><option value="value">By value ₹</option></select>
            <select id="map-view" class="btn small" style="text-transform:none">
              <option value="points" selected>Pincode points</option><option value="heat">State heat</option></select>
          </span></h2>
          <div id="map-box" style="min-height:320px"></div><div id="map-legend" class="muted small" style="margin-top:6px"></div></section>
        <section class="card"><h2>Top Regions <span class="muted small" id="map-title"></span></h2>
          <div class="table-wrap"><table><thead><tr><th>Region</th><th class="num">Count</th><th class="num">Value</th></tr></thead>
          <tbody id="map-rows"></tbody></table></div>
          <div class="muted small" style="margin-top:6px">Click a bubble or a region row to see the customers behind it. Locations come from the customer master (state and pincode).</div></section>
      </div>
      <section class="card"><div class="filter-actions">
        <button class="btn primary" id="go-enq" data-write>+ New Enquiry</button>
        <button class="btn secondary" id="go-quote" data-write>+ New Quotation</button>
        <a class="btn secondary" href="/api/export/quotations.xlsx">Export quotations.xlsx</a>
        <a class="btn secondary" href="/api/export/enquiries.xlsx">Export enquiries.xlsx</a>
        <button class="btn" id="btn-backup" data-write>Backup database</button>
      </div></section>`;
    const C = window.DzCharts;
    const totalEnq = s.enquiries.reduce((a, r) => a + r.n, 0);
    const quoted = (qs.sent || 0) + (qs.draft || 0) + s.won + s.lost + (qs.cold || 0);
    C.hbars($('ch-funnel'), [
      { label: 'Enquiries', value: totalEnq || 0.001, top: String(totalEnq), tip: totalEnq + ' enquiries', color: '#2260a4' },
      { label: 'Quoted', value: quoted, top: String(quoted), tip: 'quotations (all)', color: '#5b87c5' },
      { label: 'Won', value: s.won, top: String(s.won), tip: s.won + ' won', color: '#a1c138' },
    ], {});
    C.bars($('ch-month'), s.monthly_quotes.map(m => ({ label: m.m.slice(5), value: m.n, top: String(m.n), tip: m.m + ': ' + m.n })), {});
    const M = s.monthly || [];
    const cats = M.map((x, i) => { const d = new Date(x.m + '-01T00:00:00'); const mon = d.toLocaleString('en', { month: 'short' }); return (i === 0 || x.m.endsWith('-01')) ? mon + " '" + x.m.slice(2, 4) : mon; });
    const rupees = v => '₹ ' + short(v);
    C.grouped($('ch-mfunnel'), cats, [
      { name: 'Enquiries', color: '#2260a4', values: M.map(x => x.enquiries) },
      { name: 'Quoted', color: '#5b87c5', values: M.map(x => x.quotations) },
      { name: 'Won', color: '#a1c138', values: M.map(x => x.won) }], { title: 'Monthly funnel' });
    C.line($('ch-otrend'), M.map((x, i) => ({ label: cats[i], value: x.order_value, tip: money(x.order_value) + ' · ' + x.orders + ' order' + (x.orders === 1 ? '' : 's') })), { fmt: rupees, title: 'Order value by month' });
    C.grouped($('ch-qvo'), cats, [
      { name: 'Quotation value', color: '#5b87c5', values: M.map(x => x.quotation_value) },
      { name: 'Order value', color: '#a1c138', values: M.map(x => x.order_value) }], { fmt: rupees, title: 'Quotation vs order value' });
    renderTargetBlock();
    initMap();
    $('go-enq').onclick = () => { switchView('enquiries'); setTimeout(newEnquiryForm, 150); };
    $('go-quote').onclick = () => { switchView('quotes'); setTimeout(() => quoteForm(null), 150); };
    $('btn-backup').onclick = async () => { try { const r = await api('/api/backup', { method: 'POST' }); flash('Backup written: ' + r.path); } catch (e) { flash(e.message, false); } };
  }

  // ================= ENQUIRIES =================
  async function renderEnquiries() {
    await loadCustomers();
    const list = await api('/api/enquiries');
    const cols = [['new', 'New'], ['qualified', 'Qualified'], ['quoted', 'Quoted'], ['won,lost,dropped', 'Closed']];
    const breached = list.filter(e => e.sla === 'breach').length;
    $('view').innerHTML = `
      <section class="card filters"><div class="filter-actions">
        <button class="btn primary" id="btn-new-enq" data-write>+ New Enquiry</button>
        <a class="btn secondary" href="/api/export/enquiries.xlsx">Export Excel</a></div>
        <div class="muted small">Click a card for actions. ${list.length} enquiries total${breached ? ` · <span class="sla sla-breach">${breached} past the 48-h quotation limit</span>` : ''}.</div></section>
      <div class="kanban">${cols.map(([k, t]) => { const items = list.filter(e => k.split(',').includes(e.status));
        return `<div class="kcol"><h3>${t}<span>${items.length}</span></h3>${items.map(e => `
          <div class="kcard type-${esc((e.priority || 'Normal').replace(/\s+/g, ''))}" data-id="${e.id}"><b>${esc(e.enq_no)} ${pill(e.status)} ${typePill(e.priority)}</b>
          ${esc(e.customer)}${e.end_customer ? ' <span class="muted">→ ' + esc(e.end_customer) + '</span>' : ''}<div class="muted">${esc(e.system)} · ${esc(e.date)}${e.expected_value ? ' · ' + money(e.expected_value) : ''}${e.next_followup ? ' · FU ' + esc(e.next_followup) : ''} ${slaBadge(e)}</div></div>`).join('')}</div>`; }).join('')}</div>`;
    $('btn-new-enq').onclick = newEnquiryForm;
    document.querySelectorAll('.kcard').forEach(el => el.onclick = () => enquiryActions(list.find(x => x.id == el.dataset.id)));
  }

  function newEnquiryForm() {
    openModal('New Enquiry', `<div class="modal-form">
      <div><label>Date</label><input type="date" id="f-date" value="${today()}"></div>
      <div><label>Source</label><select id="f-source"><option>Call</option><option>Email</option><option>Visit</option><option>Exhibition</option><option>Reference</option><option>Website</option></select></div>
      <div class="full"><label>Customer</label><select id="f-cust">${custOptions()}</select>
        <div class="muted small" style="margin-top:4px">Not listed? <a href="#" id="f-addcust" class="link">Add new customer</a></div></div>
      <div class="full"><label>Contact person</label><select id="f-contact"><option value="">—</option></select></div>
      <div><label>System / product</label><input id="f-system" placeholder="e.g. MB-50, SFDS System"></div>
      <div><label>Expected value (₹)</label><input type="number" id="f-value" min="0"></div>
      <div class="full"><label>Requirement</label><textarea id="f-req"></textarea></div>
      <div><label>Salesperson (RKZ)</label><input id="f-sp" placeholder="e.g. RV" value="${!isAdmin() ? esc(ME.rkz) : ''}" ${!isAdmin() ? 'readonly style="background:var(--gray)"' : ''}></div>
      <div><label>Enquiry type</label><select id="f-type">${typeOptions()}</select></div>
      <div class="full muted small">The 48-working-hour quotation timer starts when you save this enquiry.</div>
      <div class="full"><button class="btn primary" id="f-save">Save Enquiry</button></div></div>`);
    $('f-cust').onchange = async () => { const cid = $('f-cust').value; if (!cid) return;
      const cs = await api('/api/contacts?customer_id=' + cid);
      $('f-contact').innerHTML = '<option value="">—</option>' + cs.map(c => `<option value="${c.id}">${contactLabel(c)}</option>`).join(''); };
    $('f-addcust').onclick = e => { e.preventDefault(); customerForm(() => { newEnquiryForm(); }); };
    $('f-save').onclick = async () => {
      try {
        const r = await api('/api/enquiries', { body: { date: $('f-date').value, source: $('f-source').value,
          customer_id: +$('f-cust').value, contact_id: +$('f-contact').value || null, system: $('f-system').value,
          expected_value: +$('f-value').value || 0, requirement: $('f-req').value, salesperson: $('f-sp').value, priority: $('f-type').value } });
        closeModal(); flash('Enquiry ' + r.enq_no + ' created' + (r.duplicate_warning ? ' — ⚠ ' + r.duplicate_warning : ''));
        renderEnquiries();
      } catch (e) { flash(e.message, false); }
    };
  }

  function enquiryActions(e) {
    openModal(e.enq_no + ' — ' + e.customer, `
      <p>${pill(e.status)} ${typePill(e.priority)} ${slaBadge(e)} · ${esc(e.system)} · ${esc(e.date)} · ${esc(e.source)}${e.expected_value ? ' · ' + money(e.expected_value) : ''}${e.contact ? ' · ' + esc(e.contact) : ''}${e.end_customer ? '<br>End customer: ' + esc(e.end_customer) : ''}<br>
      <span class="muted">${esc(e.requirement || '')}</span></p>
      <div class="filter-actions" style="flex-wrap:wrap">
        <button class="btn primary" id="a-quote" data-write>Create Quotation</button>
        ${isAdmin() ? '<button class="btn secondary" id="a-rkz" data-write>Assign RKZ (' + esc(e.salesperson || 'none') + ')</button>' : ''}
        <button class="btn secondary" id="a-qualify" data-write>Mark Qualified</button>
        <button class="btn secondary" id="a-fu" data-write>Add Follow-up</button>
        <button class="btn secondary" id="a-docs">Files</button>
        <button class="btn danger" id="a-drop" data-write>Drop</button>
      </div>`);
    $('a-quote').onclick = () => { closeModal(); switchView('quotes'); setTimeout(() => quoteForm(e), 150); };
    $('a-qualify').onclick = async () => { await api(`/api/enquiries/${e.id}/status`, { body: { status: 'qualified' } }); closeModal(); renderEnquiries(); };
    $('a-drop').onclick = async () => { await api(`/api/enquiries/${e.id}/status`, { body: { status: 'dropped' } }); closeModal(); renderEnquiries(); };
    $('a-fu').onclick = () => followupForm('enquiry', e.id, e.enq_no);
    $('a-docs').onclick = () => docsPanel('enquiry', e.id, e.enq_no);
    const ar = $('a-rkz'); if (ar) ar.onclick = () => { closeModal(); assignRkz('enquiry', [e.id], e.salesperson, renderEnquiries); };
  }

  // ================= QUOTATIONS =================
  let quoteSearch = '';
  async function renderQuotes() {
    await loadCustomers();
    const list = await api('/api/quotations' + (quoteSearch ? '?q=' + encodeURIComponent(quoteSearch) : ''));
    const canEditRow = q => isAdmin() || q.status === 'draft';   // engineers: own drafts only (server enforces too)
    $('view').innerHTML = `
      <section class="card filters">
        <div class="filter grow"><label for="q-search">Search quotation no. or customer</label><input id="q-search" value="${esc(quoteSearch)}" placeholder="e.g. Q00566 or JSW"></div>
        <div class="filter-actions">
          <button class="btn" id="btn-q-search">Search</button>
          <button class="btn primary" id="btn-new-q" data-write>+ New Quotation</button>
          <a class="btn secondary" href="/api/export/quotations.xlsx">Export Excel</a></div>
        <div class="muted small" style="flex-basis:100%">${list.length} quotations (excluding superseded revisions). Click a quotation number for full details.${!isAdmin() ? ' You can edit your own Drafts; once Sent, only an admin can edit or revise.' : ''}</div></section>
      <section class="card"><div class="table-wrap"><table><thead>
        <tr><th>No.</th><th>Date</th><th>Customer</th><th>Type</th><th class="num">Items</th><th class="num">Total (incl. GST)</th><th>Status</th><th>RKZ</th><th>Actions</th></tr></thead>
        <tbody>${list.map(q => `<tr>
          <td><button class="link-btn" data-detail="${q.id}">${esc(q.quote_no)}${q.rev ? '-' + q.rev : ''}</button></td><td>${esc(q.date)}</td><td class="wrap">${esc(q.customer)}${q.contact ? `<div class="muted small">${esc(q.contact)}</div>` : ''}</td>
          <td>${typePill(q.type)}</td>
          <td class="num">${q.item_count}</td><td class="num">${inr(q.total)}</td><td>${pill(q.status)}${q.lost_reason ? `<div class="muted small">${esc(q.lost_reason)}</div>` : ''}</td>
          <td>${esc(q.salesperson || '')}${isAdmin() ? ` <button class="btn small" data-qrkz="${q.id}" data-cur="${esc(q.salesperson || '')}" title="Assign RKZ" data-write>✎</button>` : ''}</td>
          <td class="actions-cell">
            <a class="btn small secondary" target="_blank" href="/api/quotations/${q.id}/print">Print</a>
            ${['draft', 'sent'].includes(q.status) && canEditRow(q) ? `<button class="btn small" data-edit="${q.id}" data-write>Edit</button>` : ''}
            ${q.status === 'draft' ? `<button class="btn small secondary" data-sent="${q.id}" data-write>Mark Sent</button>` : ''}
            ${['sent', 'draft', 'cold'].includes(q.status) ? `<button class="btn small secondary" data-won="${q.id}" data-write>Won</button><button class="btn small danger" data-lost="${q.id}" data-write>Lost</button>` : ''}
            ${isAdmin() ? `<button class="btn small" data-rev="${q.id}" data-write>Revise</button>` : ''}
            <button class="btn small" data-fu="${q.id}" data-no="${esc(q.quote_no)}" data-write>FU</button>
            <button class="btn small" data-qdocs="${q.id}" data-no="${esc(q.quote_no)}">Files</button>
          </td></tr>`).join('') || '<tr class="empty"><td colspan="9">No quotations match</td></tr>'}</tbody></table></div></section>`;
    $('btn-q-search').onclick = () => { quoteSearch = $('q-search').value.trim(); renderQuotes(); };
    $('q-search').addEventListener('keydown', e => { if (e.key === 'Enter') $('btn-q-search').click(); });
    $('btn-new-q').onclick = () => quoteForm(null);
    document.querySelectorAll('[data-detail]').forEach(b => b.onclick = () => quoteDetail(+b.dataset.detail));
    document.querySelectorAll('[data-edit]').forEach(b => b.onclick = async () => { try { quoteForm(null, await api('/api/quotations/' + b.dataset.edit)); } catch (e) { flash(e.message, false); } });
    document.querySelectorAll('[data-sent]').forEach(b => b.onclick = async () => { try { await api(`/api/quotations/${b.dataset.sent}/status`, { body: { status: 'sent' } }); flash('Marked Sent — 48-h timer stopped for its enquiry'); renderQuotes(); } catch (e) { flash(e.message, false); } });
    document.querySelectorAll('[data-won]').forEach(b => b.onclick = () => wonForm(b.dataset.won));
    document.querySelectorAll('[data-lost]').forEach(b => b.onclick = () => lostForm(b.dataset.lost));
    document.querySelectorAll('[data-rev]').forEach(b => b.onclick = async () => { try { const r = await api(`/api/quotations/${b.dataset.rev}/revise`, { method: 'POST' }); flash('Revision ' + r.rev + ' created (old copy kept)'); renderQuotes(); } catch (e) { flash(e.message, false); } });
    document.querySelectorAll('[data-fu]').forEach(b => b.onclick = () => followupForm('quotation', +b.dataset.fu, b.dataset.no));
    document.querySelectorAll('[data-qdocs]').forEach(b => b.onclick = () => docsPanel('quotation', +b.dataset.qdocs, b.dataset.no));
    document.querySelectorAll('[data-qrkz]').forEach(b => b.onclick = () => assignRkz('quotation', [+b.dataset.qrkz], b.dataset.cur, renderQuotes));
  }

  async function quoteDetail(qid) {
    let d; try { d = await api(`/api/quotations/${qid}/detail`); } catch (e) { return flash(e.message, false); }
    const c = d.customer_detail || {}, ct = d.contact_detail, o = d.order, e = d.enquiry;
    const row = (l, v) => `<div><span class="lbl">${l}</span><span class="val">${v || '—'}</span></div>`;
    const net = i => (i.qty || 0) * (i.rate || 0);
    openModal(`${d.quote_no}${d.rev ? '-' + d.rev : ''} — ${d.customer}`, `
      <div class="filter-actions" style="margin-bottom:10px;flex-wrap:wrap">${pill(d.status)} ${typePill(d.type)}
        <a class="btn small secondary" target="_blank" href="/api/quotations/${d.id}/print">Print</a>
        <button class="btn small" id="qd-docs">Files (${d.documents.length})</button>
        ${d.can_edit && ['draft', 'sent'].includes(d.status) ? '<button class="btn small" id="qd-edit" data-write>Edit</button>' : ''}</div>
      <div class="detail-grid">
        ${row('Customer', esc(c.name))}${row('End customer', esc(c.end_customer))}
        ${row('GSTIN', esc(c.gstin))}${row('State · Pincode', esc((c.state || '') + (c.pincode ? ' · ' + c.pincode : '')))}
        ${row('Contact person', ct ? contactLabel(ct) + (ct.phone ? ' · ' + esc(ct.phone) : '') + (ct.email ? ' · ' + esc(ct.email) : '') : '')}
        ${row('Address', esc(c.address))}
        ${row('Date · Validity', esc(d.date) + ' · ' + d.validity_days + ' days')}${row('RKZ', esc(d.salesperson))}
        ${row('GST mode', d.gst_mode === 'inter' ? 'IGST (other state)' : 'CGST + SGST')}${row('Sent on', esc(d.sent_at))}
        ${row('Enquiry', e ? esc(e.enq_no) + ' · ' + esc(e.date) + ' ' + slaBadge(e) : '')}${row('Discount', d.discount_pct ? d.discount_pct + '%' : '')}
      </div>
      <div class="detail-section"><h3>Products &amp; pricing</h3>
        <div class="table-wrap"><table><thead><tr><th>#</th><th>Description</th><th>HSN</th><th class="num">Qty</th><th>Unit</th><th class="num">Rate</th><th class="num">Net price</th><th class="num">GST</th><th class="num">Total price</th></tr></thead>
        <tbody>${d.items.map(i => `<tr><td>${i.sr}</td><td class="wrap">${esc(i.description)}</td><td>${esc(i.hsn)}</td><td class="num">${i.qty}</td><td>${esc(i.unit)}</td><td class="num">${inr(i.rate)}</td><td class="num">${inr(net(i))}</td><td class="num">${i.gst_pct}%</td><td class="num">${inr(net(i) * (1 + (i.gst_pct || 0) / 100))}</td></tr>`).join('')}</tbody></table></div>
        <div class="totals-box"><span>Subtotal (net): ${money(d.subtotal)}</span>${d.discount_pct ? `<span>Discount ${d.discount_pct}%</span>` : ''}<span>GST: ${money(d.gst)}</span><b>Grand total: ${money(d.total)}</b></div></div>
      <div class="detail-section"><div class="detail-grid">
        ${row('Payment terms', esc(d.payment_terms))}${row('Delivery terms', esc(d.delivery_terms))}
        ${row('Scope of supply', esc(d.scope))}${row('Warranty', esc(d.warranty))}
        ${row('Guarantee', esc(d.guarantee))}${row('Notes', esc(d.notes))}</div></div>
      <div class="detail-section"><h3>Order status</h3>${o ? `${pill('won')} SO <b>${esc(o.so_no || '—')}</b> · Customer PO ${esc(o.po_no || '—')} (${esc(o.po_date)}) · ${money(o.value)}${o.delivery_date ? ' · delivery ' + esc(o.delivery_date) : ''}` : d.status === 'lost' ? `${pill('lost')} ${esc(d.lost_reason)}` : '<span class="muted">No order yet</span>'}</div>
      <div class="detail-section"><h3>Revisions</h3>${d.revisions.map(r => `<div>${esc(r.quote_no)}${r.rev ? '-' + r.rev : ''} ${pill(r.status)} ${esc(r.date)} · ${money(r.total)}</div>`).join('')}</div>
      <div class="detail-section"><h3>Attachments (${d.documents.length})</h3>${d.documents.map(x => `<div><a class="link" href="/api/documents/${x.id}/download">${esc(x.filename)}</a> <span class="muted small">${esc(x.category)} · on ${esc(x.entity_type)} · ${esc(x.uploaded_at.slice(0, 10))}</span></div>`).join('') || '<span class="muted">None — use Files to attach the customer PO, drawings or offers received.</span>'}</div>
      ${d.followups.length ? `<div class="detail-section"><h3>Follow-ups</h3>${d.followups.map(f => `<div>${esc(f.due_date)} · ${esc(f.channel)} · ${esc(f.note)} ${f.done ? '<span class="muted">(done)</span>' : ''}</div>`).join('')}</div>` : ''}`);
    $('qd-docs').onclick = () => docsPanel('quotation', d.id, d.quote_no, () => {});
    const ed = $('qd-edit'); if (ed) ed.onclick = () => quoteForm(null, d);
  }

  let PRODUCTS = [];
  function itemRow(it = {}) {
    const d = CFG.quotation_defaults;
    return `<tr>
      <td><select class="i-prod" title="Pick from the Products master to fill this line"><option value="">— product —</option>${PRODUCTS.map(p => `<option value="${p.id}" ${p.id == it.product_id ? 'selected' : ''}>${esc(p.code)}</option>`).join('')}</select>
          <input class="i-desc" value="${esc(it.description || '')}" placeholder="Description" style="margin-top:3px"></td>
      <td style="width:90px"><input class="i-hsn" value="${esc(it.hsn || '')}" placeholder="HSN"></td>
      <td class="num" style="width:80px"><input type="number" class="i-qty" value="${it.qty ?? 1}" min="0" step="any"></td>
      <td style="width:80px"><input class="i-unit" value="${esc(it.unit || 'Nos.')}"></td>
      <td class="num" style="width:120px"><input type="number" class="i-rate" value="${it.rate ?? 0}" min="0" step="any"></td>
      <td class="num" style="width:80px"><input type="number" class="i-gst" value="${it.gst_pct ?? d.gst_pct ?? 18}" min="0" step="any"></td>
      <td class="num i-net" style="width:110px"></td>
      <td style="width:40px"><button class="btn small danger i-del">×</button></td></tr>`;
  }

  async function quoteForm(enq, existing) {
    const d = CFG.quotation_defaults;
    const q = existing || {};
    try { PRODUCTS = await api('/api/products?active_only=1'); } catch (e) { PRODUCTS = []; }
    const sec = (id, label, val) => `<div class="full"><label>${label}</label><textarea id="${id}" rows="3">${esc(val || '')}</textarea></div>`;
    openModal(existing ? `Edit ${q.quote_no}${q.rev ? '-' + q.rev : ''}` : 'New Quotation' + (enq ? ' — from ' + enq.enq_no : ''), `
      <div class="modal-form">
        <div class="full"><label>Customer</label><select id="q-cust">${custOptions(q.customer_id || (enq && enq.customer_id))}</select></div>
        <div class="full"><label>Contact person</label><select id="q-contact"><option value="">—</option></select></div>
        <div><label>Date</label><input type="date" id="q-date" value="${q.date || today()}"></div>
        <div><label>Validity (days)</label><input type="number" id="q-valid" value="${q.validity_days || d.validity_days || 30}"></div>
        <div><label>GST mode</label><select id="q-gst"><option value="intra" ${q.gst_mode !== 'inter' ? 'selected' : ''}>Within ${esc(CFG.company.home_state || 'state')} (CGST+SGST)</option><option value="inter" ${q.gst_mode === 'inter' ? 'selected' : ''}>Other state (IGST)</option></select></div>
        <div><label>Discount %</label><input type="number" id="q-disc" value="${q.discount_pct || 0}" min="0" step="any"></div>
        <div><label>Salesperson (RKZ)</label><input id="q-sp" value="${!isAdmin() ? esc(ME.rkz) : esc(q.salesperson || (enq && enq.salesperson) || '')}" ${!isAdmin() ? 'readonly style="background:var(--gray)"' : ''}></div>
        <div><label>Quotation type</label><select id="q-type">${typeOptions(q.type || (enq && enq.priority) || 'Normal')}</select></div>
        ${sec('q-intro', 'Introduction (printed before the price table)', q.introduction || d.introduction)}
      </div>
      <div class="items-editor"><h3 style="margin:6px 0">Line items</h3>
        <div class="table-wrap"><table><thead><tr><th>Description</th><th>HSN</th><th class="num">Qty</th><th>Unit</th><th class="num">Rate ₹</th><th class="num">GST %</th><th class="num">Net price ₹</th><th></th></tr></thead>
        <tbody id="q-items">${(q.items && q.items.length ? q.items : [enq ? { description: enq.system, qty: 1, rate: enq.expected_value || 0 } : {}]).map(itemRow).join('')}</tbody></table></div>
        <button class="btn small secondary" id="q-add">+ Add line</button>
        <div class="totals-box" id="q-totals"></div>
      </div>
      <div class="modal-form">
        ${sec('q-scope', 'Scope of supply', q.scope || d.scope)}
        ${sec('q-warranty', 'Warranty', q.warranty || d.warranty)}
        ${sec('q-guarantee', 'Guarantee', q.guarantee || d.guarantee)}
        ${sec('q-del', 'Delivery terms', q.delivery_terms || d.delivery_terms)}
        ${sec('q-pay', 'Payment terms', q.payment_terms || d.payment_terms)}
        ${sec('q-notes', 'Notes', q.notes || d.notes)}
        <div class="full filter-actions"><button class="btn primary" id="q-save">${existing ? 'Save Changes' : 'Save Draft'}</button></div>
      </div>`);
    const loadContacts = async () => { const cid = $('q-cust').value; if (!cid) return;
      const cs = await api('/api/contacts?customer_id=' + cid);
      $('q-contact').innerHTML = '<option value="">—</option>' + cs.map(c => `<option value="${c.id}" ${c.id == (q.contact_id || (enq && enq.contact_id)) ? 'selected' : ''}>${contactLabel(c)}</option>`).join(''); };
    $('q-cust').onchange = loadContacts; loadContacts();
    const recalc = () => { let sub = 0, gst = 0; const disc = +$('q-disc').value || 0;
      document.querySelectorAll('#q-items tr').forEach(tr => { const a = (+tr.querySelector('.i-qty').value || 0) * (+tr.querySelector('.i-rate').value || 0); tr.querySelector('.i-net').textContent = inr(a); sub += a; gst += a * (1 - disc / 100) * ((+tr.querySelector('.i-gst').value || 0) / 100); });
      const tot = sub * (1 - disc / 100) + gst;
      $('q-totals').innerHTML = `<span>Subtotal (net): ${money(sub)}</span>${disc ? `<span>Discount: −${money(sub * disc / 100)}</span>` : ''}<span>GST: ${money(gst)}</span><b>Total: ${money(tot)}</b>`; };
    $('modal-body').addEventListener('input', recalc);
    $('modal-body').addEventListener('change', e => {   // product picked -> fill the line from the master
      if (!e.target.classList.contains('i-prod')) return;
      const p = PRODUCTS.find(x => x.id == e.target.value); if (!p) return;
      const tr = e.target.closest('tr');
      tr.querySelector('.i-desc').value = p.name; tr.querySelector('.i-hsn').value = p.hsn || ''; tr.querySelector('.i-unit').value = p.unit || 'Nos.';
      if (p.rate > 0) tr.querySelector('.i-rate').value = p.rate;
      recalc();
    });
    $('modal-body').addEventListener('click', e => { if (e.target.classList.contains('i-del')) { e.target.closest('tr').remove(); recalc(); } });
    $('q-add').onclick = () => { $('q-items').insertAdjacentHTML('beforeend', itemRow()); recalc(); };
    recalc();
    $('q-save').onclick = async () => {
      const items = [...document.querySelectorAll('#q-items tr')].map(tr => ({
        description: tr.querySelector('.i-desc').value.trim(), hsn: tr.querySelector('.i-hsn').value.trim(),
        qty: +tr.querySelector('.i-qty').value || 0, unit: tr.querySelector('.i-unit').value.trim(),
        rate: +tr.querySelector('.i-rate').value || 0, gst_pct: +tr.querySelector('.i-gst').value || 0,
        product_id: +tr.querySelector('.i-prod').value || null,
      })).filter(i => i.description);
      if (!$('q-cust').value) return flash('Select a customer', false);
      if (!items.length) return flash('Add at least one line item', false);
      const body = { enquiry_id: enq ? enq.id : (q.enquiry_id || null), customer_id: +$('q-cust').value,
        contact_id: +$('q-contact').value || null, date: $('q-date').value, validity_days: +$('q-valid').value,
        gst_mode: $('q-gst').value, discount_pct: +$('q-disc').value || 0, salesperson: $('q-sp').value, type: $('q-type').value,
        introduction: $('q-intro').value, scope: $('q-scope').value, warranty: $('q-warranty').value, guarantee: $('q-guarantee').value,
        delivery_terms: $('q-del').value, payment_terms: $('q-pay').value, notes: $('q-notes').value, items };
      try {
        const r = existing ? await api('/api/quotations/' + q.id, { method: 'PUT', body })
                           : await api('/api/quotations', { body });
        closeModal(); flash(existing ? 'Quotation updated' : 'Quotation ' + r.quote_no + ' created');
        renderQuotes();
      } catch (e) { flash(e.message, false); }
    };
  }

  function wonForm(qid) {
    openModal('Mark Won — order details', `<div class="modal-form">
      <div><label>Customer PO No.</label><input id="w-po"></div>
      <div><label>PO Date</label><input type="date" id="w-date" value="${today()}"></div>
      <div><label>Sales Order (SO) No.</label><input id="w-so" placeholder="e.g. S00390"></div>
      <div><label>Order value ₹ (blank = quote total)</label><input type="number" id="w-val" min="0" step="any"></div>
      <div class="full doc-drop">Attach the customer's PO (PDF, optional — can be added later under Files)<input type="file" id="w-pdf" accept=".pdf,.jpg,.jpeg,.png"></div>
      <div class="full muted small">Payment terms and the product are copied from the quotation onto the order. You can edit them later in the Orders tab.</div>
      <div class="full"><button class="btn primary" id="w-save">Confirm Won → create Order</button></div></div>`);
    $('w-save').onclick = async () => { try {
      const r = await api(`/api/quotations/${qid}/status`, { body: { status: 'won', po_no: $('w-po').value, so_no: $('w-so').value, po_date: $('w-date').value, value: +$('w-val').value || 0 } });
      const f = $('w-pdf').files[0];
      if (f && r.order_id) {
        const fd = new FormData(); fd.append('entity_type', 'order'); fd.append('entity_id', r.order_id); fd.append('category', 'Customer PO'); fd.append('note', 'PO ' + $('w-po').value); fd.append('file', f);
        try { await apiForm('/api/documents', fd); } catch (e) { flash('Order created, but the PO file was not saved: ' + e.message, false); }
      }
      closeModal(); flash('Marked Won — order created' + (f ? ' with PO attached' : '')); renderQuotes();
    } catch (e) { flash(e.message, false); } };
  }
  function lostForm(qid) {
    openModal('Mark Lost', `<div class="modal-form"><div class="full"><label>Reason (required)</label><input id="l-reason" placeholder="e.g. price, delivery time, bought elsewhere"></div>
      <div class="full"><button class="btn danger" id="l-save">Confirm Lost</button></div></div>`);
    $('l-save').onclick = async () => { try {
      await api(`/api/quotations/${qid}/status`, { body: { status: 'lost', reason: $('l-reason').value } });
      closeModal(); flash('Marked Lost'); renderQuotes();
    } catch (e) { flash(e.message, false); } };
  }

  // ================= ORDERS =================
  async function renderOrders() {
    const list = await api('/api/orders');
    const total = list.reduce((a, o) => a + (o.value || 0), 0);
    $('view').innerHTML = `<section class="card"><h2>Orders <span class="muted small">(${list.length} · ${money(total)})</span></h2>
      <div class="filter-actions" style="margin-bottom:10px"><a class="btn secondary" href="/api/export/orders.xlsx">Export Excel</a></div>
      <div class="table-wrap"><table><thead><tr><th>SO No.</th><th>PO No.</th><th>PO Date</th><th>Customer</th><th>Product</th><th>Quote</th><th>RKZ</th><th class="num">Value</th><th>Payment terms</th><th></th></tr></thead>
      <tbody>${list.map(o => `<tr><td><b>${esc(o.so_no || '—')}</b></td><td class="wrap">${esc(o.po_no)}</td><td>${esc(o.po_date)}</td><td class="wrap">${esc(o.customer)}</td>
        <td class="wrap">${esc(o.system || '')}</td><td>${o.quote_no ? `<button class="link-btn" data-odetail="${o.quotation_id}">${esc(o.quote_no)}${o.quote_rev ? '-' + esc(o.quote_rev) : ''}</button>` : ''}</td>
        <td>${esc(o.responsible || '—')}${isAdmin() ? ` <button class="btn small" data-orkz="${o.id}" data-cur="${esc(o.responsible || '')}" title="Assign RKZ" data-write>✎</button>` : ''}</td>
        <td class="num">${inr(o.value)}</td><td class="wrap">${esc(o.payment_terms)}</td>
        <td class="actions-cell"><button class="btn small" data-oedit="${o.id}" title="Edit SO / PO / terms" data-write>Edit</button><button class="btn small" data-odocs="${o.id}" data-no="${esc(o.so_no || o.po_no || o.customer)}">Files</button></td></tr>`).join('') || '<tr class="empty"><td colspan="10">No orders</td></tr>'}</tbody></table></div></section>`;
    document.querySelectorAll('[data-orkz]').forEach(b => b.onclick = () => assignRkz('order', [+b.dataset.orkz], b.dataset.cur, renderOrders));
    document.querySelectorAll('[data-oedit]').forEach(b => b.onclick = () => orderForm(list.find(x => x.id == b.dataset.oedit)));
    document.querySelectorAll('[data-odocs]').forEach(b => b.onclick = () => docsPanel('order', +b.dataset.odocs, 'Order ' + b.dataset.no));
    document.querySelectorAll('[data-odetail]').forEach(b => b.onclick = () => quoteDetail(+b.dataset.odetail));
  }

  function orderForm(o) {
    openModal('Edit order — ' + (o.so_no || o.po_no || o.customer), `<div class="modal-form">
      <div><label>Sales Order (SO) No.</label><input id="o-so" value="${esc(o.so_no || '')}"></div>
      <div><label>Customer PO No.</label><input id="o-po" value="${esc(o.po_no || '')}"></div>
      <div><label>PO Date</label><input type="date" id="o-date" value="${esc(o.po_date || '')}"></div>
      <div><label>Order value ₹</label><input type="number" id="o-val" value="${o.value || 0}" min="0" step="any"></div>
      <div><label>Delivery date</label><input type="date" id="o-deliv" value="${esc(o.delivery_date || '')}"></div>
      <div></div>
      <div class="full"><label>Payment terms</label><textarea id="o-pay" rows="3">${esc(o.payment_terms || '')}</textarea></div>
      <div class="full"><button class="btn primary" id="o-save">Save Order</button></div></div>`);
    $('o-save').onclick = async () => { try {
      await api('/api/orders/' + o.id, { method: 'PUT', body: { so_no: $('o-so').value, po_no: $('o-po').value, po_date: $('o-date').value,
        value: +$('o-val').value || 0, payment_terms: $('o-pay').value, delivery_date: $('o-deliv').value } });
      closeModal(); flash('Order updated'); renderOrders();
    } catch (e) { flash(e.message, false); } };
  }

  // ================= LOST =================
  async function renderLost() {
    const list = await api('/api/lost');
    const total = list.reduce((a, r) => a + (r.value || 0), 0);
    $('view').innerHTML = `<section class="card"><h2>Lost Deals <span class="muted small">(${list.length} · ${money(total)} quoted value incl. GST)</span></h2>
      <div class="filter-actions" style="margin-bottom:10px"><a class="btn secondary" href="/api/export/lost.xlsx">Export Excel</a></div>
      <div class="table-wrap"><table><thead><tr><th>Quote</th><th>Quoted</th><th>Lost on</th><th>Customer</th><th>End customer</th><th>Product</th><th>Type</th><th>RKZ</th><th class="num">Value</th><th>Reason</th></tr></thead>
      <tbody>${list.map(r => `<tr class="row-critical"><td><button class="link-btn" data-detail="${r.id}">${esc(r.quote_no)}${r.rev ? '-' + esc(r.rev) : ''}</button>${r.enq_no ? `<div class="muted small">${esc(r.enq_no)}</div>` : ''}</td>
        <td>${esc(r.date)}</td><td>${esc((r.lost_on || '').slice(0, 10))}</td><td class="wrap">${esc(r.customer)}</td><td class="wrap">${esc(r.end_customer || '')}</td>
        <td class="wrap">${esc(r.product || '')}</td><td>${typePill(r.type)}</td><td>${esc(r.salesperson || '—')}</td><td class="num">${inr(r.value)}</td><td class="wrap">${esc(r.lost_reason)}</td></tr>`).join('') || '<tr class="empty"><td colspan="10">No lost deals recorded</td></tr>'}</tbody></table></div>
      <div class="muted small" style="margin-top:8px">A lost deal is a quotation marked Lost (with its reason); it has no PO or SO. Click the quotation number for full details and revisions.</div></section>`;
    document.querySelectorAll('[data-detail]').forEach(b => b.onclick = () => quoteDetail(+b.dataset.detail));
  }

  // ================= CUSTOMERS & CONTACTS =================
  function customerForm(after) {
    openModal('New Customer', `<div class="modal-form">
      <div class="full"><label>Name</label><input id="c-name"></div>
      <div class="full"><label>End customer <span class="muted small">(the plant / end user when this customer is a trader or EPC — e.g. "JSW Dolvi" for LIPL)</span></label><input id="c-endcust"></div>
      <div><label>GSTIN</label><input id="c-gstin"></div>
      <div><label>State</label><select id="c-state">${stateOptions('')}</select></div>
      <div><label>Pincode</label><input id="c-pin" maxlength="6" inputmode="numeric" placeholder="e.g. 400604"></div>
      <div><label>Segment</label><input id="c-seg" placeholder="Steel / Cement / OEM…"></div>
      <div class="full"><label>Address</label><textarea id="c-addr"></textarea></div>
      <div class="full"><h3 style="margin:4px 0 0">First contact person <span class="muted small">(optional — add more later)</span></h3></div>
      <div><label>Name</label><input id="c-contact"></div>
      <div><label>Designation</label><input id="c-cdesig" placeholder="e.g. Purchase Manager"></div>
      <div><label>Department</label><input id="c-cdept" placeholder="e.g. Purchase"></div>
      <div><label>Phone</label><input id="c-phone"></div>
      <div class="full"><label>Email</label><input id="c-cemail" type="email"></div>
      <div class="full"><button class="btn primary" id="c-save">Save Customer</button></div></div>`);
    $('c-save').onclick = async () => { try {
      const r = await api('/api/customers', { body: { name: $('c-name').value, end_customer: $('c-endcust').value, gstin: $('c-gstin').value, state: $('c-state').value, pincode: $('c-pin').value, address: $('c-addr').value, segment: $('c-seg').value } });
      if ($('c-contact').value.trim()) await api('/api/contacts', { body: { customer_id: r.id, name: $('c-contact').value, phone: $('c-phone').value, email: $('c-cemail').value, designation: $('c-cdesig').value, department: $('c-cdept').value } });
      await loadCustomers(); closeModal(); flash('Customer saved');
      if (after) after(); else if (view === 'customers') renderCustomers();
    } catch (e) { flash(e.message, false); } };
  }

  const custBody = (c, patch) => ({ name: c.name, gstin: c.gstin, address: c.address, state: c.state || '', pincode: c.pincode || '', segment: c.segment, end_customer: c.end_customer || '', ...patch });

  async function renderCustomers() {
    const list = await loadCustomers();
    $('view').innerHTML = `<section class="card filters"><div class="filter-actions"><button class="btn primary" id="btn-new-c" data-write>+ New Customer</button>
      <a class="btn secondary" href="/api/export/customers.xlsx">Export customers</a><a class="btn secondary" href="/api/export/contacts.xlsx">Export contacts</a></div>
      <div class="muted small">${list.length} customers</div></section>
      <section class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>End customer</th><th>Contacts</th><th>Files</th><th>GSTIN</th><th>State</th><th>Pincode</th><th>Segment</th><th class="num">Enquiries</th><th class="num">Quotes</th><th class="num">Order value</th></tr></thead>
      <tbody>${list.map(c => `<tr><td class="wrap"><b>${esc(c.name)}</b></td>
        <td class="wrap">${esc(c.end_customer || '—')} <button class="btn small" data-endc="${c.id}" title="Edit end customer" data-write>✎</button></td>
        <td><button class="btn small secondary" data-contacts="${c.id}">${c.contact_count || 0} contact${c.contact_count === 1 ? '' : 's'}</button></td>
        <td><button class="btn small secondary" data-cdocs="${c.id}">${c.document_count || 0} file${c.document_count === 1 ? '' : 's'}</button></td>
        <td>${esc(c.gstin)}</td><td>${esc(c.state)} <button class="btn small" data-state="${c.id}" title="Edit state" data-write>✎</button></td>
        <td>${esc(c.pincode || '—')} <button class="btn small" data-pin="${c.id}" title="Edit pincode" data-write>✎</button></td><td>${esc(c.segment)}</td>
        <td class="num">${c.enquiries}</td><td class="num">${c.quotes}</td><td class="num">${inr(c.order_value)}</td></tr>`).join('')}</tbody></table></div></section>`;
    $('btn-new-c').onclick = () => customerForm();
    document.querySelectorAll('[data-contacts]').forEach(b => b.onclick = () => contactsPanel(list.find(x => x.id == b.dataset.contacts)));
    document.querySelectorAll('[data-cdocs]').forEach(b => b.onclick = () => { const c = list.find(x => x.id == b.dataset.cdocs); docsPanel('customer', c.id, c.name, () => loadCustomers().then(renderCustomers)); });
    document.querySelectorAll('[data-state]').forEach(b => b.onclick = () => {
      const c = list.find(x => x.id == b.dataset.state);
      openModal('State — ' + c.name, `<div class="modal-form"><div class="full"><label>State</label><select id="st-sel">${stateOptions(c.state || '')}</select></div>
        <div class="full"><button class="btn primary" id="st-save">Save</button></div></div>`);
      $('st-save').onclick = async () => { try { await api('/api/customers/' + c.id, { method: 'PUT', body: custBody(c, { state: $('st-sel').value }) }); closeModal(); flash('State updated'); renderCustomers(); } catch (e) { flash(e.message, false); } };
    });
    document.querySelectorAll('[data-endc]').forEach(b => b.onclick = () => {
      const c = list.find(x => x.id == b.dataset.endc);
      openModal('End customer — ' + c.name, `<div class="modal-form"><div class="full"><label>End customer / plant</label><input id="ec-val" value="${esc(c.end_customer || '')}" placeholder="e.g. JSW Dolvi"></div>
        <div class="full muted small">Shown on enquiries, quotations (printed under the customer name), orders and the Lost tab.</div>
        <div class="full"><button class="btn primary" id="ec-save">Save</button></div></div>`);
      $('ec-save').onclick = async () => { try { await api('/api/customers/' + c.id, { method: 'PUT', body: custBody(c, { end_customer: $('ec-val').value }) }); closeModal(); flash('End customer updated'); renderCustomers(); } catch (e) { flash(e.message, false); } };
    });
    document.querySelectorAll('[data-pin]').forEach(b => b.onclick = async () => {
      const c = list.find(x => x.id == b.dataset.pin);
      const pin = prompt('Pincode for ' + c.name + ' (6 digits, blank to clear):', c.pincode || '');
      if (pin === null) return;
      if (pin.trim() && !/^[1-8]\d{5}$/.test(pin.trim())) return flash('Enter a valid 6-digit Indian pincode', false);
      try { await api('/api/customers/' + c.id, { method: 'PUT', body: custBody(c, { pincode: pin.trim() }) }); flash('Pincode updated'); renderCustomers(); }
      catch (e) { flash(e.message, false); }
    });
  }

  async function contactsPanel(c, editing) {
    const cs = await api('/api/contacts?customer_id=' + c.id);
    const ed = editing || {};
    openModal('Contacts — ' + c.name, `
      <div class="table-wrap"><table><thead><tr><th>Name</th><th>Designation</th><th>Department</th><th>Phone</th><th>Email</th><th></th></tr></thead>
      <tbody>${cs.map(x => `<tr><td><b>${esc(x.name)}</b></td><td>${esc(x.designation || x.role || '')}</td><td>${esc(x.department || '')}</td><td>${esc(x.phone)}</td><td>${esc(x.email)}</td>
        <td class="actions-cell"><button class="btn small" data-cedit="${x.id}" data-write>Edit</button><button class="btn small danger" data-cdel="${x.id}" data-write>Delete</button></td></tr>`).join('') || '<tr class="empty"><td colspan="6">No contacts yet</td></tr>'}</tbody></table></div>
      <div class="modal-form" data-write style="margin-top:12px;border-top:1px solid var(--line);padding-top:12px">
        <div class="full"><h3 style="margin:0">${ed.id ? 'Edit contact' : 'Add contact'}</h3></div>
        <div><label>Name</label><input id="ct-name" value="${esc(ed.name || '')}"></div>
        <div><label>Designation</label><input id="ct-desig" value="${esc(ed.designation || '')}" placeholder="e.g. Purchase Manager"></div>
        <div><label>Department</label><input id="ct-dept" value="${esc(ed.department || '')}" placeholder="e.g. Purchase / Projects"></div>
        <div><label>Phone</label><input id="ct-phone" value="${esc(ed.phone || '')}"></div>
        <div class="full"><label>Email</label><input id="ct-email" type="email" value="${esc(ed.email || '')}"></div>
        <div class="full filter-actions"><button class="btn primary" id="ct-save">${ed.id ? 'Update contact' : 'Add contact'}</button>${ed.id ? '<button class="btn" id="ct-cancel">Cancel edit</button>' : ''}</div>
      </div>`);
    $('ct-save').onclick = async () => {
      const body = { customer_id: c.id, name: $('ct-name').value, designation: $('ct-desig').value, department: $('ct-dept').value, phone: $('ct-phone').value, email: $('ct-email').value };
      if (!body.name.trim()) return flash('Contact name is required', false);
      try {
        if (ed.id) await api('/api/contacts/' + ed.id, { method: 'PUT', body }); else await api('/api/contacts', { body });
        flash(ed.id ? 'Contact updated' : 'Contact added'); contactsPanel(c);
        if (view === 'customers') loadCustomers().then(renderCustomers);
      } catch (e) { flash(e.message, false); }
    };
    const cancel = $('ct-cancel'); if (cancel) cancel.onclick = () => contactsPanel(c);
    document.querySelectorAll('[data-cedit]').forEach(b => b.onclick = () => contactsPanel(c, cs.find(x => x.id == b.dataset.cedit)));
    document.querySelectorAll('[data-cdel]').forEach(b => b.onclick = async () => {
      const x = cs.find(y => y.id == b.dataset.cdel);
      if (!confirm('Delete contact ' + x.name + '?')) return;
      try { await api('/api/contacts/' + x.id, { method: 'DELETE' }); flash('Contact deleted'); contactsPanel(c); if (view === 'customers') loadCustomers().then(renderCustomers); }
      catch (e) { flash(e.message, false); }
    });
  }

  // ================= FOLLOW-UPS =================
  function followupForm(type, id, ref) {
    openModal('Follow-up on ' + ref, `<div class="modal-form">
      <div><label>Due date</label><input type="date" id="u-date" value="${today()}"></div>
      <div><label>Channel</label><select id="u-ch"><option>Call</option><option>Email</option><option>Visit</option><option>WhatsApp</option></select></div>
      <div class="full"><label>Note</label><input id="u-note"></div>
      <div class="full"><button class="btn primary" id="u-save">Save Follow-up</button></div></div>`);
    $('u-save').onclick = async () => { try { await api('/api/followups', { body: { entity_type: type, entity_id: id, due_date: $('u-date').value, channel: $('u-ch').value, note: $('u-note').value } });
      closeModal(); flash('Follow-up saved'); } catch (e) { flash(e.message, false); } };
  }

  async function renderFollowups() {
    const list = await api('/api/followups');
    $('view').innerHTML = `<section class="card"><h2>Open Follow-ups <span class="muted small">(${list.length})</span></h2>
      <div class="table-wrap"><table><thead><tr><th>Due</th><th>Ref</th><th>Channel</th><th>Note</th><th></th></tr></thead>
      <tbody>${list.map(f => `<tr><td class="${f.due_date <= today() ? 'due-overdue' : ''}">${esc(f.due_date)}</td>
        <td class="wrap">${esc(f.ref || f.entity_type + ' #' + f.entity_id)}</td><td>${esc(f.channel)}</td><td class="wrap">${esc(f.note)}</td>
        <td><button class="btn small secondary" data-done="${f.id}" data-write>Done</button></td></tr>`).join('') || '<tr class="empty"><td colspan="5">Nothing due — punch in some enquiries!</td></tr>'}</tbody></table></div></section>`;
    document.querySelectorAll('[data-done]').forEach(b => b.onclick = async () => { try { await api(`/api/followups/${b.dataset.done}/done`, { body: { status: 'done', reason: '' } }); renderFollowups(); } catch (e) { flash(e.message, false); } });
  }

  // ================= region map =================
  let GEO = null, MAPJ = null;
  async function initMap() {
    try {
      if (!MAPJ) MAPJ = await api('/static/india_states.json');
      GEO = await api('/api/geo');
      $('map-metric').onchange = drawMap; $('map-mode').onchange = drawMap; $('map-view').onchange = drawMap;
      drawMap();
    } catch (e) { $('map-box').textContent = 'Map unavailable: ' + e.message; }
  }
  function heatColor(t) { // 0..1 -> light tint .. deep Duztec blue (stronger ramp)
    if (t <= 0) return '#e7ecea';
    const a = [205, 220, 238], b = [16, 58, 108];
    const c = a.map((v, i) => Math.round(v + (b[i] - v) * Math.pow(t, 0.6)));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }
  function regionModal(title, customers, n, value, label) {
    openModal(title, `<p>${n} ${esc(label)} · ${money(value)}</p><div class="table-wrap"><table><thead><tr><th>Customer</th></tr></thead>
      <tbody>${(customers || []).map(c => `<tr><td>${esc(c)}</td></tr>`).join('') || '<tr class="empty"><td>No customer names available</td></tr>'}</tbody></table></div>
      <div class="muted small" style="margin-top:6px">Use the Quotations / Orders tabs with the search box to open the individual records.</div>`);
  }
  function drawMap() {
    if (!MAPJ || !GEO) return;
    const metric = $('map-metric').value, mode = $('map-mode').value;
    const data = GEO[metric] || {};
    const max = Math.max(1e-9, ...Object.entries(data).filter(([k]) => k !== 'International' && k !== '(No state set)').map(([, d]) => d[mode]));
    const K = Math.cos(22 * Math.PI / 180);   // projection: x = lon * cos(22deg), y = -lat
    let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
    MAPJ.states.forEach(st => st.p.forEach(r => r.forEach(([lo, la]) => {
      const x = lo * K, y = -la;
      if (x < minX) minX = x; if (x > maxX) maxX = x; if (y < minY) minY = y; if (y > maxY) maxY = y;
    })));
    const W = 640, H = W * (maxY - minY) / (maxX - minX);
    const sc = W / (maxX - minX);
    const viewMode = $('map-view') ? $('map-view').value : 'heat';
    const label = $('map-metric').selectedOptions[0].text.toLowerCase();
    let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H.toFixed(0)}" width="100%" role="img" aria-label="India map">`;
    MAPJ.states.forEach(st => {
      const d = data[st.n] || { n: 0, value: 0 };
      const t = d[mode] / max;
      const path = st.p.map(r => 'M' + r.map(([lo, la]) => `${((lo * K - minX) * sc).toFixed(1)},${((-la - minY) * sc).toFixed(1)}`).join('L') + 'Z').join('');
      svg += `<path d="${path}" data-state="${esc(st.n)}" fill="${viewMode === 'points' ? '#eef1ee' : heatColor(t)}" stroke="#ffffff" stroke-width="0.8" style="cursor:${d.n ? 'pointer' : 'default'}"><title>${esc(st.n)}: ${d.n} ${label} · ${money(d.value)}</title></path>`;
    });
    if (viewMode === 'points') {
      const pts = [...((GEO.points && GEO.points[metric]) || [])].sort((a, b) => b[mode] - a[mode]);
      const pmax = Math.max(1e-9, ...pts.map(p => p[mode]));
      pts.forEach((p, idx) => {
        const x = ((p.lon * K - minX) * sc).toFixed(1), y = ((-p.lat - minY) * sc).toFixed(1);
        const r = (5 + 16 * Math.sqrt(p[mode] / pmax)).toFixed(1);
        svg += `<circle cx="${x}" cy="${y}" r="${r}" data-pin="${esc(p.pin)}" fill="rgba(34,96,164,.72)" stroke="#ffffff" stroke-width="1.5" style="cursor:pointer">` +
               `<title>PIN ${esc(p.pin)} — ${esc(p.customers.join(', '))}\n${p.n} ${label} · ${money(p.value)}</title></circle>`;
        if (idx < 5) svg += `<text x="${x}" y="${(+y - +r - 4).toFixed(1)}" text-anchor="middle" font-size="11" font-weight="800" fill="#10395c" stroke="#ffffff" stroke-width="3" paint-order="stroke">${mode === 'n' ? p.n : short(p.value)}</text>`;
      });
    }
    svg += '</svg>';
    $('map-box').innerHTML = svg;
    $('map-box').querySelectorAll('circle[data-pin]').forEach(c => c.onclick = () => { const p = GEO.points[metric].find(x => x.pin === c.dataset.pin); if (p) regionModal('Pincode ' + p.pin, p.customers, p.n, p.value, label); });
    $('map-box').querySelectorAll('path[data-state]').forEach(pth => pth.onclick = () => { const d = data[pth.dataset.state]; if (d && d.n) regionModal(pth.dataset.state, d.customers, d.n, d.value, label); });
    $('map-title').textContent = '(' + $('map-metric').selectedOptions[0].text + ')';
    if (viewMode === 'points') {
      const miss = (GEO.no_pincode && GEO.no_pincode[metric]) || 0;
      $('map-legend').innerHTML = 'Bubble size = ' + (mode === 'n' ? 'count' : 'value') + ' at that pincode · top 5 labelled · click a bubble for its customers' +
        (miss ? ` &nbsp;·&nbsp; <span style="color:var(--warning);font-weight:700">${miss} record(s) have no pincode</span> — set pincodes in the Customers tab` : '');
      const pts = [...((GEO.points && GEO.points[metric]) || [])].sort((a, b) => b[mode] - a[mode]).slice(0, 12);
      $('map-rows').innerHTML = pts.map(p => `<tr style="cursor:pointer" data-rowpin="${esc(p.pin)}"><td>${esc(p.pin)} · ${esc(p.customers[0] || '')}${p.customers.length > 1 ? ' +' + (p.customers.length - 1) : ''}</td><td class="num">${p.n}</td><td class="num">${inr(p.value)}</td></tr>`).join('') || '<tr class="empty"><td colspan="3">No pincodes set yet — add pincodes to customers</td></tr>';
      $('map-rows').querySelectorAll('[data-rowpin]').forEach(tr => tr.onclick = () => { const p = GEO.points[metric].find(x => x.pin === tr.dataset.rowpin); if (p) regionModal('Pincode ' + p.pin, p.customers, p.n, p.value, label); });
    } else {
      const steps = [0, .25, .5, .75, 1];
      $('map-legend').innerHTML = 'Low ' + steps.map(t => `<span style="display:inline-block;width:26px;height:11px;background:${heatColor(t)};border:1px solid var(--line)"></span>`).join('') +
        ' High &nbsp;·&nbsp; max = ' + (mode === 'n' ? Math.round(max) : money(max));
      const rows = Object.entries(data).sort((a, b) => b[1][mode] - a[1][mode]);
      $('map-rows').innerHTML = rows.map(([k, d]) => `<tr${k === 'International' || k === '(No state set)' ? ' class="row-warning"' : ''}><td>${esc(k)}</td><td class="num">${d.n}</td><td class="num">${inr(d.value)}</td></tr>`).join('') || '<tr class="empty"><td colspan="3">No data</td></tr>';
    }
  }

  // ================= RKZ assignment (admin) =================
  async function assignRkz(entityType, ids, cur, after) {
    const users = await api('/api/auth/users').catch(() => []);
    const codes = users.filter(u => u.rkz && u.active).map(u => ({ rkz: u.rkz, who: u.name || u.email }));
    if (!codes.length) return flash('No RKZ codes exist yet — assign codes to users in the Users tab first.', false);
    openModal('Assign RKZ', `<div class="modal-form">
      <div class="full"><label>RKZ code (sales engineer)</label>
        <select id="ar-code">
          ${codes.map(c => `<option value="${esc(c.rkz)}" ${c.rkz === (cur || '').toUpperCase() ? 'selected' : ''}>${esc(c.rkz)} — ${esc(c.who)}</option>`).join('')}
          <option value="">— Clear (no RKZ) —</option>
        </select></div>
      <div class="full muted small">Applies to ${ids.length} ${entityType}(s). Sales engineers only see records carrying their own RKZ.</div>
      <div class="full"><button class="btn primary" id="ar-save">Assign</button></div></div>`);
    $('ar-save').onclick = async () => {
      try {
        const r = await api('/api/assign-rkz', { body: { entity_type: entityType, ids, rkz: $('ar-code').value } });
        closeModal(); flash('RKZ updated on ' + r.updated + ' record(s)' + (r.warning ? ' — ⚠ ' + r.warning : ''));
        if (after) after();
      } catch (e) { flash(e.message, false); }
    };
  }

  // ================= users (admin) =================
  const ROLE_LABEL = { admin: 'Admin (sees everything)', user: 'Sales engineer (own RKZ data)', viewer: 'View only (read everything, change nothing)' };
  async function renderUsers() {
    const list = await api('/api/auth/users');
    const ov = await api('/api/rkz-overview').catch(() => null);
    const active = list.filter(u => u.active);
    $('view').innerHTML = `<section class="card filters"><div class="filter-actions"><button class="btn primary" id="btn-new-user">+ Add User</button>
      <button class="btn secondary" id="btn-login-history">Login history</button></div>
      <div class="muted small">${active.length} active user(s) of ${list.length}. Only @duztec.in emails can be added; deactivated users are logged out immediately.</div></section>
      ${ov ? `<section class="card"><h2>RKZ Coverage</h2>
        <div class="table-wrap"><table><thead><tr><th>RKZ</th><th class="num">Enquiries</th><th class="num">Quotations</th><th class="num">Orders</th></tr></thead>
        <tbody>${ov.by_rkz.map(r => `<tr><td><b>${esc(r.rkz)}</b></td><td class="num">${r.enquiries}</td><td class="num">${r.quotations}</td><td class="num">${r.orders}</td></tr>`).join('')}
        <tr class="row-warning"><td><b>Unassigned</b></td><td class="num">${ov.unassigned.enquiries}</td><td class="num">${ov.unassigned.quotations}</td><td class="num">${ov.unassigned.orders}</td></tr></tbody></table></div>
        <div class="muted small" style="margin-top:6px">To assign old records: use the ✎ next to RKZ in the Quotations and Orders tables, or "Assign RKZ" on an enquiry card. Records without an RKZ are invisible to sales engineers (admins and viewers always see them).</div></section>` : ''}
      <section class="card"><div class="table-wrap"><table><thead><tr><th>Email</th><th>Name</th><th>Presence</th><th>RKZ</th><th>Role</th><th>Status</th><th>Last login</th><th>Actions</th></tr></thead>
      <tbody>${list.map(u => `<tr class="${u.active ? '' : 'row-critical'}"><td><b>${esc(u.email)}</b></td><td>${esc(u.name)}</td>
        <td><span class="presence ${esc(u.presence || 'out')}"></span>${{ active: 'Active', idle: 'Idle', out: 'Out' }[u.presence] || 'Out'}${u.last_seen ? `<div class="muted small" title="last seen">${esc(u.last_seen.slice(5, 16))}</div>` : ''}</td>
        <td><b>${esc(u.rkz || '—')}</b> <button class="btn small" data-rkz="${u.id}" title="Edit RKZ code">✎</button></td>
        <td><select class="btn small" data-rolesel="${u.id}" style="text-transform:none">${Object.entries(ROLE_LABEL).map(([k, v]) => `<option value="${k}" ${u.role === k ? 'selected' : ''}>${v}</option>`).join('')}</select></td>
        <td>${u.active ? 'Active' : 'Deactivated'}</td><td>${esc(u.last_login || 'never')}</td>
        <td class="actions-cell"><button class="btn small ${u.active ? 'danger' : 'secondary'}" data-toggle="${u.id}">${u.active ? 'Deactivate' : 'Reactivate'}</button></td></tr>`).join('')}</tbody></table></div></section>
      <div class="muted small" style="margin-top:8px">RKZ = sales engineer code (e.g. RV). Sales engineers see only records carrying their RKZ; admins see everything; view-only users see everything but cannot create or change anything.
      Presence = the CRM tab open in a browser (Active &lt; 5 min, Idle &lt; 30 min, otherwise Out) — it is not a measure of work.</div>`;
    $('btn-new-user').onclick = () => {
      openModal('Add User', `<div class="modal-form">
        <div class="full"><label>Duztec email</label><input id="nu-email" type="email" placeholder="name@duztec.in"></div>
        <div><label>Name</label><input id="nu-name"></div>
        <div><label>RKZ code</label><input id="nu-rkz" placeholder="e.g. RV" style="text-transform:uppercase"></div>
        <div class="full"><label>Role</label><select id="nu-role">${Object.entries(ROLE_LABEL).map(([k, v]) => `<option value="${k}" ${k === 'user' ? 'selected' : ''}>${v}</option>`).join('')}</select></div>
        <div class="full"><button class="btn primary" id="nu-save">Add User</button></div></div>`);
      $('nu-save').onclick = async () => { try {
        await api('/api/auth/users', { body: { email: $('nu-email').value, name: $('nu-name').value, role: $('nu-role').value, rkz: $('nu-rkz').value } });
        closeModal(); flash('User added — they can now log in with an OTP'); renderUsers();
      } catch (e) { flash(e.message, false); } };
    };
    $('btn-login-history').onclick = () => loginHistory();
    const upd = async (u, patch) => { try {
      await api('/api/auth/users/' + u.id, { method: 'PUT', body: { email: u.email, name: u.name, role: patch.role ?? u.role, active: patch.active ?? u.active, rkz: patch.rkz ?? (u.rkz || '') } });
      renderUsers();
    } catch (e) { flash(e.message, false); renderUsers(); } };
    document.querySelectorAll('[data-rkz]').forEach(b => b.onclick = () => { const u = list.find(x => x.id == b.dataset.rkz);
      const code = prompt('RKZ code for ' + u.email + ' (blank = none):', u.rkz || ''); if (code === null) return; upd(u, { rkz: code.trim().toUpperCase() }); });
    document.querySelectorAll('[data-rolesel]').forEach(s => s.onchange = () => upd(list.find(x => x.id == s.dataset.rolesel), { role: s.value }));
    document.querySelectorAll('[data-toggle]').forEach(b => b.onclick = () => { const u = list.find(x => x.id == b.dataset.toggle); upd(u, { active: u.active ? 0 : 1 }); });
  }

  async function loginHistory(emailFilter = '', days = 30) {
    const rows = await api('/api/auth/login-history?days=' + days + (emailFilter ? '&email=' + encodeURIComponent(emailFilter) : ''));
    const lbl = { login: 'Logged in', logout: 'Logged out', session_expired: 'Session expired' };
    openModal('Login history', `
      <div class="filter-actions" style="margin-bottom:10px">
        <input id="lh-email" placeholder="filter by email" value="${esc(emailFilter)}" style="padding:6px 10px;border:1px solid var(--line);border-radius:6px">
        <select id="lh-days" class="btn small" style="text-transform:none"><option value="7" ${days == 7 ? 'selected' : ''}>Last 7 days</option><option value="30" ${days == 30 ? 'selected' : ''}>Last 30 days</option><option value="90" ${days == 90 ? 'selected' : ''}>Last 90 days</option></select>
        <button class="btn" id="lh-go">Apply</button>
        <a class="btn secondary" href="/api/export/logins.xlsx">Export Excel</a></div>
      <div class="table-wrap"><table><thead><tr><th>When</th><th>Event</th><th>User</th></tr></thead>
      <tbody>${rows.map(r => `<tr><td>${esc(r.at)}</td><td>${pill(r.action === 'login' ? 'won' : r.action === 'logout' ? 'sent' : 'cold', lbl[r.action] || r.action)}</td><td>${esc(r.email)}</td></tr>`).join('') || '<tr class="empty"><td colspan="3">No events in this period</td></tr>'}</tbody></table></div>
      <div class="muted small" style="margin-top:6px">${rows.length} event(s). Logins are recorded at OTP verification; logouts when the user clicks Logout; expiries when a 7-day session lapses.</div>`);
    $('lh-go').onclick = () => loginHistory($('lh-email').value.trim(), +$('lh-days').value);
  }

  // ================= targets =================
  const tval = (t, v) => t.measure.endsWith('_value') ? money(v) : String(Math.round(v));
  function targetCard(t) {
    const fill = t.state === 'done' ? 'done' : (t.pct + 10 < t.elapsed_pct ? 'behind' : '');
    return `<div class="target"><div class="t-head"><b>${esc(t.measure_label)}</b><span class="muted small">${esc(t.period_type)} · ${esc(t.period_start)} → ${esc(t.period_end)}</span></div>
      <div class="t-bar"><div class="t-fill ${fill}" style="width:${Math.min(100, t.pct)}%"></div><div class="t-elapsed" style="left:${Math.min(100, t.elapsed_pct)}%" title="time elapsed: ${t.elapsed_pct}% of the period"></div></div>
      <div class="t-meta"><span>Target <b>${tval(t, t.amount)}</b></span><span>Achieved <b>${tval(t, t.achieved)}</b> (${t.pct}%)</span><span>Remaining <b>${tval(t, t.remaining)}</b></span><span><b>${t.days_left}</b> day${t.days_left === 1 ? '' : 's'} left</span></div>
      ${isAdmin() ? `<div class="muted small" style="margin-top:4px">${esc(t.email)} · RKZ ${esc(t.rkz)}${t.note ? ' · ' + esc(t.note) : ''}</div>` : (t.note ? `<div class="muted small" style="margin-top:4px">${esc(t.note)}</div>` : '')}</div>`;
  }
  async function renderTargetBlock() {
    const host = $('tg-block'); if (!host) return;
    try {
      if (isAdmin()) {
        const ov = await api('/api/targets/overview');
        host.innerHTML = ov.targets.map(targetCard).join('') || `<div class="muted small">No target covers today. Set them in the <button class="link-btn" id="tg-go">Targets</button> tab.</div>`;
        const g = $('tg-go'); if (g) g.onclick = () => switchView('targets');
      } else {
        const m = await api('/api/targets/mine');
        host.innerHTML = m.current.map(targetCard).join('') || '<div class="muted small">No target has been set for you for the current period.</div>';
      }
    } catch (e) { host.innerHTML = `<div class="muted small">${esc(e.message)}</div>`; }
  }
  async function renderTargets() {
    const [ov, all, meta] = await Promise.all([api('/api/targets/overview'), api('/api/targets'), api('/api/targets/measures')]);
    const without = ov.engineers.filter(u => !ov.targets.some(t => t.email === u.email));
    $('view').innerHTML = `<section class="card filters"><div class="filter-actions"><button class="btn primary" id="btn-new-t">+ Set Target</button></div>
      <div class="muted small">One target per user, measure and period. Achievement is computed live from the user's RKZ records — orders by PO date, quotations by the date they were marked Sent, enquiries by enquiry date.</div></section>
      <section class="card"><h2>Running now <span class="muted small">(${ov.targets.length})</span></h2><div class="target-grid">${ov.targets.map(targetCard).join('') || '<div class="muted">No target covers today.</div>'}</div>
      ${without.length ? `<div class="muted small" style="margin-top:8px">No running target: ${without.map(u => esc(u.email) + ' (' + esc(u.rkz) + ')').join(', ')}</div>` : ''}</section>
      <section class="card"><h2>All targets <span class="muted small">(${all.length})</span></h2><div class="table-wrap"><table><thead><tr><th>User</th><th>RKZ</th><th>Measure</th><th>Period</th><th class="num">Target</th><th class="num">Achieved</th><th class="num">%</th><th>State</th><th></th></tr></thead>
      <tbody>${all.map(t => `<tr class="${t.state === 'expired' && t.pct < 100 ? 'row-critical' : ''}"><td>${esc(t.email)}</td><td>${esc(t.rkz)}</td><td>${esc(t.measure_label)}</td><td>${esc(t.period_type)} · ${esc(t.period_start)} → ${esc(t.period_end)}</td>
        <td class="num">${tval(t, t.amount)}</td><td class="num">${tval(t, t.achieved)}</td><td class="num">${t.pct}%</td><td>${pill(t.state === 'done' ? 'won' : t.state === 'expired' ? 'lost' : t.state === 'upcoming' ? 'draft' : 'sent', t.state)}</td>
        <td class="actions-cell"><button class="btn small" data-tedit="${t.id}">Edit</button><button class="btn small danger" data-tdel="${t.id}">Delete</button></td></tr>`).join('') || '<tr class="empty"><td colspan="9">No targets yet</td></tr>'}</tbody></table></div></section>`;
    $('btn-new-t').onclick = () => targetForm(null, ov.engineers, meta);
    document.querySelectorAll('[data-tedit]').forEach(b => b.onclick = () => targetForm(all.find(x => x.id == b.dataset.tedit), ov.engineers, meta));
    document.querySelectorAll('[data-tdel]').forEach(b => b.onclick = async () => { if (!confirm('Delete this target?')) return; try { await api('/api/targets/' + b.dataset.tdel, { method: 'DELETE' }); flash('Target deleted'); renderTargets(); } catch (e) { flash(e.message, false); } });
  }
  function targetForm(t, engineers, meta) {
    const q = t || {}; const users = engineers.map(u => u.email); if (q.email && !users.includes(q.email)) users.push(q.email);
    openModal(t ? 'Edit target' : 'Set target', `<div class="modal-form">
      <div class="full"><label>User</label><select id="t-email">${users.map(e => `<option ${e === q.email ? 'selected' : ''}>${esc(e)}</option>`).join('')}</select>${users.length ? '' : '<div class="muted small">No user has an RKZ code yet — assign codes in the Users tab first.</div>'}</div>
      <div><label>Measure</label><select id="t-measure">${Object.entries(meta.measures).map(([k, v]) => `<option value="${k}" ${(q.measure || meta.default) === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></div>
      <div><label>Period</label><select id="t-period">${meta.periods.map(p => `<option ${p === (q.period_type || 'monthly') ? 'selected' : ''}>${p}</option>`).join('')}</select></div>
      <div><label>Period start</label><input type="date" id="t-start" value="${esc(q.period_start || today().slice(0, 7) + '-01')}"></div>
      <div><label>Target amount</label><input type="number" id="t-amount" value="${q.amount || ''}" min="0" step="any" placeholder="e.g. 5000000"></div>
      <div class="full"><label>Note</label><input id="t-note" value="${esc(q.note || '')}" placeholder="optional"></div>
      <div class="full muted small">The start is snapped to the 1st of its month and the end is derived from the period (yearly = 12 months; start yearly targets in April for the financial year).</div>
      <div class="full"><button class="btn primary" id="t-save">${t ? 'Save' : 'Set target'}</button></div></div>`);
    $('t-save').onclick = async () => {
      const body = { email: $('t-email').value, measure: $('t-measure').value, period_type: $('t-period').value, period_start: $('t-start').value, amount: +$('t-amount').value || 0, note: $('t-note').value };
      try { const r = t ? await api('/api/targets/' + t.id, { method: 'PUT', body }) : await api('/api/targets', { body }); closeModal(); flash('Target ' + (t ? 'updated' : 'set') + ' · ' + r.period_start + ' → ' + r.period_end); renderTargets(); }
      catch (e) { flash(e.message, false); }
    };
  }

  // ================= products =================
  async function renderProducts() {
    const list = await api('/api/products');
    $('view').innerHTML = `<section class="card filters"><div class="filter-actions">${isAdmin() ? '<button class="btn primary" id="btn-new-p" data-write>+ New Product</button>' : ''}</div>
      <div class="muted small">${list.length} products. Pick a product on a quotation line to fill its description, HSN, unit and default rate; the specification prints on the quotation under "Technical Specifications".</div></section>
      <section class="card"><div class="table-wrap"><table><thead><tr><th>Code</th><th>Name</th><th>HSN</th><th>Unit</th><th class="num">Rate ₹</th><th>Specification</th><th class="num">Used on</th><th>Status</th>${isAdmin() ? '<th></th>' : ''}</tr></thead>
      <tbody>${list.map(p => `<tr class="${p.active ? '' : 'row-critical'}"><td><b>${esc(p.code)}</b></td><td class="wrap">${esc(p.name)}</td><td>${esc(p.hsn)}</td><td>${esc(p.unit)}</td><td class="num">${inr(p.rate)}</td><td class="spec">${esc(p.specification || '')}</td><td class="num">${p.used_on}</td><td>${p.active ? 'Active' : 'Retired'}</td>
        ${isAdmin() ? `<td class="actions-cell"><button class="btn small" data-pedit="${p.id}" data-write>Edit</button>${p.active ? `<button class="btn small danger" data-pret="${p.id}" data-write>Retire</button>` : ''}</td>` : ''}</tr>`).join('') || '<tr class="empty"><td colspan="9">No products yet</td></tr>'}</tbody></table></div></section>`;
    const nb = $('btn-new-p'); if (nb) nb.onclick = () => productForm();
    document.querySelectorAll('[data-pedit]').forEach(b => b.onclick = () => productForm(list.find(x => x.id == b.dataset.pedit)));
    document.querySelectorAll('[data-pret]').forEach(b => b.onclick = async () => { if (!confirm('Retire this product? Existing quotation lines keep it; it just disappears from the dropdown.')) return; try { await api('/api/products/' + b.dataset.pret, { method: 'DELETE' }); flash('Product retired'); renderProducts(); } catch (e) { flash(e.message, false); } });
  }
  function productForm(p) {
    const q = p || {};
    openModal(p ? 'Edit product ' + p.code : 'New Product', `<div class="modal-form">
      <div><label>Code</label><input id="p-code" value="${esc(q.code || '')}" style="text-transform:uppercase" placeholder="e.g. MB-50"></div><div><label>Name</label><input id="p-name" value="${esc(q.name || '')}"></div>
      <div><label>HSN / SAC</label><input id="p-hsn" value="${esc(q.hsn || '')}"></div><div><label>Unit</label><input id="p-unit" value="${esc(q.unit || 'Nos.')}"></div>
      <div><label>Default rate ₹ (0 = quote each time)</label><input type="number" id="p-rate" value="${q.rate || 0}" min="0" step="any"></div>
      <div><label>Status</label><select id="p-active"><option value="1" ${q.active !== 0 ? 'selected' : ''}>Active</option><option value="0" ${q.active === 0 ? 'selected' : ''}>Retired</option></select></div>
      <div class="full"><label>Specification (printed on quotations that use this product)</label><textarea id="p-spec" rows="7" placeholder="Capacity, throw distance, motor rating, materials, controls…">${esc(q.specification || '')}</textarea></div>
      <div class="full"><button class="btn primary" id="p-save">${p ? 'Save' : 'Add product'}</button></div></div>`);
    $('p-save').onclick = async () => {
      const body = { code: $('p-code').value, name: $('p-name').value, hsn: $('p-hsn').value, unit: $('p-unit').value, rate: +$('p-rate').value || 0, specification: $('p-spec').value, active: +$('p-active').value };
      try { if (p) await api('/api/products/' + p.id, { method: 'PUT', body }); else await api('/api/products', { body }); closeModal(); flash(p ? 'Product updated' : 'Product added'); renderProducts(); }
      catch (e) { flash(e.message, false); }
    };
  }

  // ================= nav =================
  const VIEWS = { dash: renderDash, enquiries: renderEnquiries, quotes: renderQuotes, orders: renderOrders, lost: renderLost, customers: renderCustomers, products: renderProducts, followups: renderFollowups, targets: renderTargets, users: renderUsers };
  const TITLES = { dash: 'Sales Dashboard', enquiries: 'Enquiries', quotes: 'Quotations', orders: 'Orders', lost: 'Lost Deals', customers: 'Customers', products: 'Products', followups: 'Follow-ups', targets: 'Targets', users: 'Users' };
  function switchView(v) {
    view = v;
    document.querySelectorAll('#nav button').forEach(b => b.classList.toggle('active', b.dataset.view === v));
    $('page-title').textContent = TITLES[v]; document.title = 'Duztec CRM — ' + TITLES[v];
    VIEWS[v]().catch(e => flash(e.message, false));
  }
  document.querySelectorAll('#nav button').forEach(b => b.onclick = () => switchView(b.dataset.view));

  (async () => { try {
    if (!(await initAuth())) return;          // login overlay shown; boot continues after verify
    CFG = await api('/api/config'); $('footer-text').textContent = CFG.company_name; switchView('dash');
  } catch (e) { flash(e.message, false); } })();
})();

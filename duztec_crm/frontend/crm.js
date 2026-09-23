/* Duztec Sales CRM frontend. */
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

  function flash(msg, ok = true) { const b = $(ok ? 'ok-box' : 'error-box'); b.textContent = msg; b.classList.remove('hidden'); setTimeout(() => b.classList.add('hidden'), ok ? 3500 : 8000); }
  async function api(path, opts = {}) {
    if (opts.body) { opts.method = opts.method || 'POST'; opts.headers = { 'Content-Type': 'application/json' }; opts.body = JSON.stringify(opts.body); }
    const r = await fetch(path, opts);
    if (r.status === 401 && !path.startsWith('/api/auth/')) { showLogin(); throw new Error('Please log in.'); }
    if (!r.ok) { let d; try { d = (await r.json()).detail; } catch (e) { d = { detail: r.statusText }; } throw new Error(typeof d === 'string' ? d : d.detail); }
    return r.json();
  }

  // ================= auth =================
  let ME = null;
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
    $('user-email').textContent = ME.email + (ME.role === 'admin' ? ' (admin)' : '');
    if (ME.role === 'admin') $('nav-users').classList.remove('hidden');
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

  const SP = { won: 'won', lost: 'lost', cold: 'cold', sent: 'sent', draft: 'draft', new: 'new', qualified: 'qualified', quoted: 'quoted', dropped: 'dropped' };
  const pill = st => `<span class="status-pill ${SP[st] || 'open'}">${esc(st)}</span>`;

  function openModal(title, html) { $('modal-title').textContent = title; $('modal-body').innerHTML = html; $('modal').classList.remove('hidden'); }
  function closeModal() { $('modal').classList.add('hidden'); }
  $('modal-close').onclick = closeModal;
  $('modal').addEventListener('click', e => { if (e.target === $('modal')) closeModal(); });

  async function loadCustomers() { customersCache = await api('/api/customers'); return customersCache; }
  const custOptions = sel => '<option value="">— select customer —</option>' + customersCache.map(c => `<option value="${c.id}" ${c.id == sel ? 'selected' : ''}>${esc(c.name)}</option>`).join('');

  // ================= DASHBOARD =================
  async function renderDash() {
    const s = await api('/api/summary');
    const enq = Object.fromEntries(s.enquiries.map(r => [r.status, r.n]));
    const openEnq = (enq.new || 0) + (enq.qualified || 0);
    const qs = Object.fromEntries(s.quotes.map(r => [r.status, r.n]));
    const decided = s.won + s.lost, wr = decided ? Math.round(100 * s.won / decided) : 0;
    $('view').innerHTML = `
      ${s.scope_rkz ? `<section class="card summary-strip">Showing only <b>RKZ ${esc(s.scope_rkz === '__UNASSIGNED__' ? '(none assigned — ask an admin)' : s.scope_rkz)}</b> data. Admins see all RKZ codes.</section>` : ''}
      <section class="kpis">
        <div class="kpi neutral"><div class="kpi-label">Open Enquiries</div><div class="kpi-value">${openEnq}</div><div class="kpi-sub">${s.enquiries_stale} idle &gt; 7 days</div></div>
        <div class="kpi overdue"><div class="kpi-label">Pipeline Value</div><div class="kpi-value">${money(s.pipeline_value)}</div><div class="kpi-sub">${(qs.sent || 0) + (qs.draft || 0)} live quotations</div></div>
        <div class="kpi success"><div class="kpi-label">Won</div><div class="kpi-value">${s.won}</div><div class="kpi-sub">win rate ${wr}%</div></div>
        <div class="kpi critical"><div class="kpi-label">Lost</div><div class="kpi-value">${s.lost}</div><div class="kpi-sub">of ${decided} decided</div></div>
        <div class="kpi warning"><div class="kpi-label">Follow-ups Due</div><div class="kpi-value">${s.followups_due}</div><div class="kpi-sub">today or overdue</div></div>
        <div class="kpi minor"><div class="kpi-label">Orders</div><div class="kpi-value">${s.orders.n}</div><div class="kpi-sub">${money(s.orders.v)} booked</div></div>
      </section>
      <div class="grid-3">
        <section class="card chart-card"><h2>Funnel</h2><div class="chart" id="ch-funnel"></div></section>
        <section class="card chart-card"><h2>Quotations by Month</h2><div class="chart" id="ch-month"></div></section>
        <section class="card"><h2>Recent Activity</h2><ul class="act-list">${s.recent.map(a => `<li>${esc(a.at.slice(5, 16))} · <b>${esc(a.action)}</b> ${esc(a.entity_type)} ${esc(a.detail)}</li>`).join('') || '<li>None yet</li>'}</ul></section>
      </div>
      <div class="grid-2" style="margin-bottom:16px">
        <section class="card chart-card"><h2 style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px">Region Heat Map
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
          <div class="muted small" style="margin-top:6px">States are taken from the customer master (auto-guessed from plant names; edit in the Customers tab).</div></section>
      </div>
      <section class="card"><div class="filter-actions">
        <button class="btn primary" id="go-enq">+ New Enquiry</button>
        <button class="btn secondary" id="go-quote">+ New Quotation</button>
        <a class="btn secondary" href="/api/export/quotations.xlsx">Export quotations.xlsx</a>
        <a class="btn secondary" href="/api/export/enquiries.xlsx">Export enquiries.xlsx</a>
        <button class="btn" id="btn-backup">Backup database</button>
      </div></section>`;
    const C = window.DzCharts;
    const totalEnq = s.enquiries.reduce((a, r) => a + r.n, 0);
    C.hbars($('ch-funnel'), [
      { label: 'Enquiries', value: totalEnq || 0.001, top: String(totalEnq), tip: totalEnq + ' enquiries', color: '#2260a4' },
      { label: 'Quoted', value: (qs.sent || 0) + (qs.draft || 0) + s.won + s.lost + (qs.cold || 0), top: String((qs.sent || 0) + (qs.draft || 0) + s.won + s.lost + (qs.cold || 0)), tip: 'quotations (all)', color: '#5b87c5' },
      { label: 'Won', value: s.won, top: String(s.won), tip: s.won + ' won', color: '#a1c138' },
    ], {});
    C.bars($('ch-month'), s.monthly_quotes.map(m => ({ label: m.m.slice(5), value: m.n, top: String(m.n), tip: m.m + ': ' + m.n })), {});
    initMap();
    $('go-enq').onclick = () => { switchView('enquiries'); setTimeout(newEnquiryForm, 150); };
    $('go-quote').onclick = () => { switchView('quotes'); setTimeout(() => quoteForm(null), 150); };
    $('btn-backup').onclick = async () => { const r = await api('/api/backup', { method: 'POST' }); flash('Backup written: ' + r.path); };
  }

  // ================= ENQUIRIES =================
  async function renderEnquiries() {
    await loadCustomers();
    const list = await api('/api/enquiries');
    const cols = [['new', 'New'], ['qualified', 'Qualified'], ['quoted', 'Quoted'], ['won,lost,dropped', 'Closed']];
    $('view').innerHTML = `
      <section class="card filters"><div class="filter-actions">
        <button class="btn primary" id="btn-new-enq">+ New Enquiry</button>
        <a class="btn secondary" href="/api/export/enquiries.xlsx">Export Excel</a></div>
        <div class="muted small">Click a card for actions. ${list.length} enquiries total.</div></section>
      <div class="kanban">${cols.map(([k, t]) => { const items = list.filter(e => k.split(',').includes(e.status));
        return `<div class="kcol"><h3>${t}<span>${items.length}</span></h3>${items.map(e => `
          <div class="kcard pri-${esc(e.priority)}" data-id="${e.id}"><b>${esc(e.enq_no)} ${pill(e.status)}</b>
          ${esc(e.customer)}<div class="muted">${esc(e.system)} · ${esc(e.date)}${e.expected_value ? ' · ' + money(e.expected_value) : ''}${e.next_followup ? ' · FU ' + esc(e.next_followup) : ''}</div></div>`).join('')}</div>`; }).join('')}</div>`;
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
      <div><label>Salesperson (RKZ)</label><input id="f-sp" placeholder="e.g. RV" value="${ME && ME.role !== 'admin' ? esc(ME.rkz) : ''}" ${ME && ME.role !== 'admin' ? 'readonly style="background:var(--gray)"' : ''}></div>
      <div><label>Priority</label><select id="f-pri"><option>Normal</option><option>High</option><option>Low</option></select></div>
      <div class="full"><button class="btn primary" id="f-save">Save Enquiry</button></div></div>`);
    $('f-cust').onchange = async () => { const cid = $('f-cust').value; if (!cid) return;
      const cs = await api('/api/contacts?customer_id=' + cid);
      $('f-contact').innerHTML = '<option value="">—</option>' + cs.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join(''); };
    $('f-addcust').onclick = e => { e.preventDefault(); customerForm(() => { newEnquiryForm(); }); };
    $('f-save').onclick = async () => {
      try {
        const r = await api('/api/enquiries', { body: { date: $('f-date').value, source: $('f-source').value,
          customer_id: +$('f-cust').value, contact_id: +$('f-contact').value || null, system: $('f-system').value,
          expected_value: +$('f-value').value || 0, requirement: $('f-req').value, salesperson: $('f-sp').value, priority: $('f-pri').value } });
        closeModal(); flash('Enquiry ' + r.enq_no + ' created' + (r.duplicate_warning ? ' — ⚠ ' + r.duplicate_warning : ''));
        renderEnquiries();
      } catch (e) { flash(e.message, false); }
    };
  }

  function enquiryActions(e) {
    openModal(e.enq_no + ' — ' + e.customer, `
      <p>${pill(e.status)} · ${esc(e.system)} · ${esc(e.date)} · ${esc(e.source)}${e.expected_value ? ' · ' + money(e.expected_value) : ''}<br>
      <span class="muted">${esc(e.requirement || '')}</span></p>
      <div class="filter-actions" style="flex-wrap:wrap">
        <button class="btn primary" id="a-quote">Create Quotation</button>
        ${ME && ME.role === 'admin' ? '<button class="btn secondary" id="a-rkz">Assign RKZ (' + esc(e.salesperson || 'none') + ')</button>' : ''}
        <button class="btn secondary" id="a-qualify">Mark Qualified</button>
        <button class="btn secondary" id="a-fu">Add Follow-up</button>
        <button class="btn danger" id="a-drop">Drop</button>
      </div>`);
    $('a-quote').onclick = () => { closeModal(); switchView('quotes'); setTimeout(() => quoteForm(e), 150); };
    $('a-qualify').onclick = async () => { await api(`/api/enquiries/${e.id}/status`, { body: { status: 'qualified' } }); closeModal(); renderEnquiries(); };
    $('a-drop').onclick = async () => { await api(`/api/enquiries/${e.id}/status`, { body: { status: 'dropped' } }); closeModal(); renderEnquiries(); };
    $('a-fu').onclick = () => followupForm('enquiry', e.id, e.enq_no);
    const ar = $('a-rkz'); if (ar) ar.onclick = () => { closeModal(); assignRkz('enquiry', [e.id], e.salesperson, renderEnquiries); };
  }

  // ================= QUOTATIONS =================
  async function renderQuotes() {
    await loadCustomers();
    const list = await api('/api/quotations');
    $('view').innerHTML = `
      <section class="card filters"><div class="filter-actions">
        <button class="btn primary" id="btn-new-q">+ New Quotation</button>
        <a class="btn secondary" href="/api/export/quotations.xlsx">Export Excel</a></div>
        <div class="muted small">${list.length} quotations (excluding superseded revisions).</div></section>
      <section class="card"><div class="table-wrap"><table><thead>
        <tr><th>No.</th><th>Date</th><th>Customer</th><th class="num">Items</th><th class="num">Total (incl. GST)</th><th>Status</th><th>Salesperson</th><th>Actions</th></tr></thead>
        <tbody>${list.map(q => `<tr>
          <td><b>${esc(q.quote_no)}${q.rev ? '-' + q.rev : ''}</b></td><td>${esc(q.date)}</td><td class="wrap">${esc(q.customer)}</td>
          <td class="num">${q.item_count}</td><td class="num">${inr(q.total)}</td><td>${pill(q.status)}${q.lost_reason ? `<div class="muted small">${esc(q.lost_reason)}</div>` : ''}</td>
          <td>${esc(q.salesperson || '')}${ME && ME.role === 'admin' ? ` <button class="btn small" data-qrkz="${q.id}" data-cur="${esc(q.salesperson || '')}" title="Assign RKZ">✎</button>` : ''}</td>
          <td class="actions-cell">
            <a class="btn small secondary" target="_blank" href="/api/quotations/${q.id}/print">Print</a>
            ${['draft', 'sent'].includes(q.status) ? `<button class="btn small" data-edit="${q.id}">Edit</button>` : ''}
            ${q.status === 'draft' ? `<button class="btn small secondary" data-sent="${q.id}">Mark Sent</button>` : ''}
            ${['sent', 'draft', 'cold'].includes(q.status) ? `<button class="btn small secondary" data-won="${q.id}">Won</button><button class="btn small danger" data-lost="${q.id}">Lost</button>` : ''}
            <button class="btn small" data-rev="${q.id}">Revise</button>
            <button class="btn small" data-fu="${q.id}" data-no="${esc(q.quote_no)}">FU</button>
          </td></tr>`).join('') || '<tr class="empty"><td colspan="8">No quotations yet</td></tr>'}</tbody></table></div></section>`;
    $('btn-new-q').onclick = () => quoteForm(null);
    document.querySelectorAll('[data-edit]').forEach(b => b.onclick = async () => quoteForm(null, await api('/api/quotations/' + b.dataset.edit)));
    document.querySelectorAll('[data-sent]').forEach(b => b.onclick = async () => { await api(`/api/quotations/${b.dataset.sent}/status`, { body: { status: 'sent' } }); renderQuotes(); });
    document.querySelectorAll('[data-won]').forEach(b => b.onclick = () => wonForm(b.dataset.won));
    document.querySelectorAll('[data-lost]').forEach(b => b.onclick = () => lostForm(b.dataset.lost));
    document.querySelectorAll('[data-rev]').forEach(b => b.onclick = async () => { const r = await api(`/api/quotations/${b.dataset.rev}/revise`, { method: 'POST' }); flash('Revision ' + r.rev + ' created (old copy kept)'); renderQuotes(); });
    document.querySelectorAll('[data-fu]').forEach(b => b.onclick = () => followupForm('quotation', +b.dataset.fu, b.dataset.no));
    document.querySelectorAll('[data-qrkz]').forEach(b => b.onclick = () => assignRkz('quotation', [+b.dataset.qrkz], b.dataset.cur, renderQuotes));
  }

  function itemRow(it = {}) {
    const d = CFG.quotation_defaults;
    return `<tr>
      <td><input class="i-desc" value="${esc(it.description || '')}" placeholder="Description"></td>
      <td style="width:90px"><input class="i-hsn" value="${esc(it.hsn || '')}" placeholder="HSN"></td>
      <td class="num" style="width:80px"><input type="number" class="i-qty" value="${it.qty ?? 1}" min="0" step="any"></td>
      <td style="width:80px"><input class="i-unit" value="${esc(it.unit || 'Nos.')}"></td>
      <td class="num" style="width:120px"><input type="number" class="i-rate" value="${it.rate ?? 0}" min="0" step="any"></td>
      <td class="num" style="width:80px"><input type="number" class="i-gst" value="${it.gst_pct ?? d.gst_pct ?? 18}" min="0" step="any"></td>
      <td style="width:40px"><button class="btn small danger i-del">×</button></td></tr>`;
  }

  function quoteForm(enq, existing) {
    const d = CFG.quotation_defaults;
    const q = existing || {};
    openModal(existing ? `Edit ${q.quote_no}${q.rev ? '-' + q.rev : ''}` : 'New Quotation' + (enq ? ' — from ' + enq.enq_no : ''), `
      <div class="modal-form">
        <div class="full"><label>Customer</label><select id="q-cust">${custOptions(q.customer_id || (enq && enq.customer_id))}</select></div>
        <div class="full"><label>Contact</label><select id="q-contact"><option value="">—</option></select></div>
        <div><label>Date</label><input type="date" id="q-date" value="${q.date || today()}"></div>
        <div><label>Validity (days)</label><input type="number" id="q-valid" value="${q.validity_days || d.validity_days || 30}"></div>
        <div><label>GST mode</label><select id="q-gst"><option value="intra" ${q.gst_mode !== 'inter' ? 'selected' : ''}>Within ${esc(CFG.company.home_state || 'state')} (CGST+SGST)</option><option value="inter" ${q.gst_mode === 'inter' ? 'selected' : ''}>Other state (IGST)</option></select></div>
        <div><label>Discount %</label><input type="number" id="q-disc" value="${q.discount_pct || 0}" min="0" step="any"></div>
        <div><label>Salesperson (RKZ)</label><input id="q-sp" value="${ME && ME.role !== 'admin' ? esc(ME.rkz) : esc(q.salesperson || (enq && enq.salesperson) || '')}" ${ME && ME.role !== 'admin' ? 'readonly style="background:var(--gray)"' : ''}></div>
        <div></div>
        <div class="full"><label>Delivery terms</label><input id="q-del" value="${esc(q.delivery_terms || d.delivery_terms || '')}"></div>
        <div class="full"><label>Payment terms</label><input id="q-pay" value="${esc(q.payment_terms || d.payment_terms || '')}"></div>
        <div class="full"><label>Notes</label><input id="q-notes" value="${esc(q.notes || d.notes || '')}"></div>
      </div>
      <div class="items-editor"><h3 style="margin:6px 0">Line items</h3>
        <div class="table-wrap"><table><thead><tr><th>Description</th><th>HSN</th><th class="num">Qty</th><th>Unit</th><th class="num">Rate ₹</th><th class="num">GST %</th><th></th></tr></thead>
        <tbody id="q-items">${(q.items && q.items.length ? q.items : [enq ? { description: enq.system, qty: 1, rate: enq.expected_value || 0 } : {}]).map(itemRow).join('')}</tbody></table></div>
        <button class="btn small secondary" id="q-add">+ Add line</button>
        <div class="totals-box" id="q-totals"></div>
        <div class="filter-actions"><button class="btn primary" id="q-save">${existing ? 'Save Changes' : 'Save Draft'}</button></div>
      </div>`);
    const loadContacts = async () => { const cid = $('q-cust').value; if (!cid) return;
      const cs = await api('/api/contacts?customer_id=' + cid);
      $('q-contact').innerHTML = '<option value="">—</option>' + cs.map(c => `<option value="${c.id}" ${c.id == (q.contact_id || (enq && enq.contact_id)) ? 'selected' : ''}>${esc(c.name)}</option>`).join(''); };
    $('q-cust').onchange = loadContacts; loadContacts();
    const recalc = () => { let sub = 0, gst = 0; const disc = +$('q-disc').value || 0;
      document.querySelectorAll('#q-items tr').forEach(tr => { const a = (+tr.querySelector('.i-qty').value || 0) * (+tr.querySelector('.i-rate').value || 0); sub += a; gst += a * (1 - disc / 100) * ((+tr.querySelector('.i-gst').value || 0) / 100); });
      const tot = sub * (1 - disc / 100) + gst;
      $('q-totals').innerHTML = `<span>Subtotal: ${money(sub)}</span><span>GST: ${money(gst)}</span><b>Total: ${money(tot)}</b>`; };
    $('modal-body').addEventListener('input', recalc);
    $('modal-body').addEventListener('click', e => { if (e.target.classList.contains('i-del')) { e.target.closest('tr').remove(); recalc(); } });
    $('q-add').onclick = () => { $('q-items').insertAdjacentHTML('beforeend', itemRow()); recalc(); };
    recalc();
    $('q-save').onclick = async () => {
      const items = [...document.querySelectorAll('#q-items tr')].map(tr => ({
        description: tr.querySelector('.i-desc').value.trim(), hsn: tr.querySelector('.i-hsn').value.trim(),
        qty: +tr.querySelector('.i-qty').value || 0, unit: tr.querySelector('.i-unit').value.trim(),
        rate: +tr.querySelector('.i-rate').value || 0, gst_pct: +tr.querySelector('.i-gst').value || 0,
      })).filter(i => i.description);
      if (!$('q-cust').value) return flash('Select a customer', false);
      if (!items.length) return flash('Add at least one line item', false);
      const body = { enquiry_id: enq ? enq.id : (q.enquiry_id || null), customer_id: +$('q-cust').value,
        contact_id: +$('q-contact').value || null, date: $('q-date').value, validity_days: +$('q-valid').value,
        gst_mode: $('q-gst').value, discount_pct: +$('q-disc').value || 0, salesperson: $('q-sp').value,
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
    openModal('Mark Won — customer PO details', `<div class="modal-form">
      <div><label>Customer PO No.</label><input id="w-po"></div>
      <div><label>PO Date</label><input type="date" id="w-date" value="${today()}"></div>
      <div><label>Order value ₹ (blank = quote total)</label><input type="number" id="w-val" min="0" step="any"></div>
      <div class="full"><button class="btn primary" id="w-save">Confirm Won → create Order</button></div></div>`);
    $('w-save').onclick = async () => { try {
      await api(`/api/quotations/${qid}/status`, { body: { status: 'won', po_no: $('w-po').value, po_date: $('w-date').value, value: +$('w-val').value || 0 } });
      closeModal(); flash('Marked Won — order created'); renderQuotes();
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

  // ================= ORDERS / CUSTOMERS / FOLLOWUPS =================
  async function renderOrders() {
    const list = await api('/api/orders');
    const total = list.reduce((a, o) => a + (o.value || 0), 0);
    $('view').innerHTML = `<section class="card"><h2>Orders <span class="muted small">(${list.length} · ${money(total)})</span></h2>
      <div class="filter-actions" style="margin-bottom:10px"><a class="btn secondary" href="/api/export/orders.xlsx">Export Excel</a></div>
      <div class="table-wrap"><table><thead><tr><th>PO No.</th><th>PO Date</th><th>Customer</th><th>Quote</th><th>SO No.</th><th>RKZ</th><th class="num">Value</th><th>Payment terms</th></tr></thead>
      <tbody>${list.map(o => `<tr><td class="wrap">${esc(o.po_no)}</td><td>${esc(o.po_date)}</td><td class="wrap">${esc(o.customer)}</td>
        <td>${esc(o.quote_no || '')}</td><td>${esc(o.so_no)}</td>
        <td>${esc(o.responsible || '—')}${ME && ME.role === 'admin' ? ` <button class="btn small" data-orkz="${o.id}" data-cur="${esc(o.responsible || '')}" title="Assign RKZ">✎</button>` : ''}</td>
        <td class="num">${inr(o.value)}</td><td class="wrap">${esc(o.payment_terms)}</td></tr>`).join('') || '<tr class="empty"><td colspan="8">No orders</td></tr>'}</tbody></table></div></section>`;
    document.querySelectorAll('[data-orkz]').forEach(b => b.onclick = () => assignRkz('order', [+b.dataset.orkz], b.dataset.cur, renderOrders));
  }

  function customerForm(after) {
    openModal('New Customer', `<div class="modal-form">
      <div class="full"><label>Name</label><input id="c-name"></div>
      <div><label>GSTIN</label><input id="c-gstin"></div><div><label>State</label><input id="c-state"></div>
      <div><label>Pincode</label><input id="c-pin" maxlength="6" inputmode="numeric" placeholder="e.g. 400604"></div>
      <div class="full"><label>Address</label><textarea id="c-addr"></textarea></div>
      <div><label>Segment</label><input id="c-seg" placeholder="Steel / Cement / OEM…"></div>
      <div><label>Contact person (optional)</label><input id="c-contact"></div>
      <div><label>Contact phone</label><input id="c-phone"></div><div></div>
      <div class="full"><button class="btn primary" id="c-save">Save Customer</button></div></div>`);
    $('c-save').onclick = async () => { try {
      const r = await api('/api/customers', { body: { name: $('c-name').value, gstin: $('c-gstin').value, state: $('c-state').value, pincode: $('c-pin').value, address: $('c-addr').value, segment: $('c-seg').value } });
      if ($('c-contact').value) await api('/api/contacts', { body: { customer_id: r.id, name: $('c-contact').value, phone: $('c-phone').value } });
      await loadCustomers(); closeModal(); flash('Customer saved');
      if (after) after(); else if (view === 'customers') renderCustomers();
    } catch (e) { flash(e.message, false); } };
  }

  async function renderCustomers() {
    const list = await loadCustomers();
    $('view').innerHTML = `<section class="card filters"><div class="filter-actions"><button class="btn primary" id="btn-new-c">+ New Customer</button>
      <a class="btn secondary" href="/api/export/customers.xlsx">Export Excel</a></div>
      <div class="muted small">${list.length} customers</div></section>
      <section class="card"><div class="table-wrap"><table><thead><tr><th>Name</th><th>GSTIN</th><th>State</th><th>Pincode</th><th>Segment</th><th class="num">Enquiries</th><th class="num">Quotes</th><th class="num">Order value</th></tr></thead>
      <tbody>${list.map(c => `<tr><td class="wrap"><b>${esc(c.name)}</b></td><td>${esc(c.gstin)}</td><td>${esc(c.state)} <button class="btn small" data-state="${c.id}" title="Edit state">✎</button></td>
        <td>${esc(c.pincode || '—')} <button class="btn small" data-pin="${c.id}" title="Edit pincode">✎</button></td><td>${esc(c.segment)}</td>
        <td class="num">${c.enquiries}</td><td class="num">${c.quotes}</td><td class="num">${inr(c.order_value)}</td></tr>`).join('')}</tbody></table></div></section>`;
    $('btn-new-c').onclick = () => customerForm();
    document.querySelectorAll('[data-state]').forEach(b => b.onclick = async () => {
      const c = list.find(x => x.id == b.dataset.state);
      const st = prompt('State for ' + c.name + ' (e.g. Maharashtra, Odisha, International):', c.state || '');
      if (st === null) return;
      await api('/api/customers/' + c.id, { method: 'PUT', body: { name: c.name, gstin: c.gstin, address: c.address, state: st.trim(), pincode: c.pincode || '', segment: c.segment } });
      flash('State updated'); renderCustomers();
    });
    document.querySelectorAll('[data-pin]').forEach(b => b.onclick = async () => {
      const c = list.find(x => x.id == b.dataset.pin);
      const pin = prompt('Pincode for ' + c.name + ' (6 digits, blank to clear):', c.pincode || '');
      if (pin === null) return;
      if (pin.trim() && !/^[1-8]\d{5}$/.test(pin.trim())) return flash('Enter a valid 6-digit Indian pincode', false);
      await api('/api/customers/' + c.id, { method: 'PUT', body: { name: c.name, gstin: c.gstin, address: c.address, state: c.state || '', pincode: pin.trim(), segment: c.segment } });
      flash('Pincode updated'); renderCustomers();
    });
  }

  function followupForm(type, id, ref) {
    openModal('Follow-up on ' + ref, `<div class="modal-form">
      <div><label>Due date</label><input type="date" id="u-date" value="${today()}"></div>
      <div><label>Channel</label><select id="u-ch"><option>Call</option><option>Email</option><option>Visit</option><option>WhatsApp</option></select></div>
      <div class="full"><label>Note</label><input id="u-note"></div>
      <div class="full"><button class="btn primary" id="u-save">Save Follow-up</button></div></div>`);
    $('u-save').onclick = async () => { await api('/api/followups', { body: { entity_type: type, entity_id: id, due_date: $('u-date').value, channel: $('u-ch').value, note: $('u-note').value } });
      closeModal(); flash('Follow-up saved'); };
  }

  async function renderFollowups() {
    const list = await api('/api/followups');
    $('view').innerHTML = `<section class="card"><h2>Open Follow-ups <span class="muted small">(${list.length})</span></h2>
      <div class="table-wrap"><table><thead><tr><th>Due</th><th>Ref</th><th>Channel</th><th>Note</th><th></th></tr></thead>
      <tbody>${list.map(f => `<tr><td class="${f.due_date <= today() ? 'due-overdue' : ''}">${esc(f.due_date)}</td>
        <td class="wrap">${esc(f.ref || f.entity_type + ' #' + f.entity_id)}</td><td>${esc(f.channel)}</td><td class="wrap">${esc(f.note)}</td>
        <td><button class="btn small secondary" data-done="${f.id}">Done</button></td></tr>`).join('') || '<tr class="empty"><td colspan="5">Nothing due — punch in some enquiries!</td></tr>'}</tbody></table></div></section>`;
    document.querySelectorAll('[data-done]').forEach(b => b.onclick = async () => { await api(`/api/followups/${b.dataset.done}/done`, { body: { status: 'done', reason: '' } }); renderFollowups(); });
  }

  // ================= region heat map =================
  let GEO = null, MAPJ = null;
  async function initMap() {
    try {
      if (!MAPJ) MAPJ = await api('/static/india_states.json');
      GEO = await api('/api/geo');
      $('map-metric').onchange = drawMap; $('map-mode').onchange = drawMap; $('map-view').onchange = drawMap;
      drawMap();
    } catch (e) { $('map-box').textContent = 'Map unavailable: ' + e.message; }
  }
  function heatColor(t) { // 0..1 -> light tint .. deep Duztec blue
    if (t <= 0) return '#e7ecea';
    const a = [219, 230, 242], b = [23, 74, 130];
    const c = a.map((v, i) => Math.round(v + (b[i] - v) * Math.sqrt(t)));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }
  function drawMap() {
    if (!MAPJ || !GEO) return;
    const metric = $('map-metric').value, mode = $('map-mode').value;
    const data = GEO[metric] || {};
    const max = Math.max(1e-9, ...Object.entries(data).filter(([k]) => k !== 'International' && k !== '(No state set)').map(([, d]) => d[mode]));
    // projection: x = lon * cos(22deg), y = -lat
    const K = Math.cos(22 * Math.PI / 180);
    let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
    MAPJ.states.forEach(st => st.p.forEach(r => r.forEach(([lo, la]) => {
      const x = lo * K, y = -la;
      if (x < minX) minX = x; if (x > maxX) maxX = x; if (y < minY) minY = y; if (y > maxY) maxY = y;
    })));
    const W = 640, H = W * (maxY - minY) / (maxX - minX);
    const sc = W / (maxX - minX);
    let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H.toFixed(0)}" width="100%" role="img" aria-label="India heat map">`;
    MAPJ.states.forEach(st => {
      const d = data[st.n] || { n: 0, value: 0 };
      const t = d[mode] / max;
      const path = st.p.map(r => 'M' + r.map(([lo, la]) => `${((lo * K - minX) * sc).toFixed(1)},${((-la - minY) * sc).toFixed(1)}`).join('L') + 'Z').join('');
      svg += `<path d="${path}" fill="${heatColor(t)}" stroke="#ffffff" stroke-width="0.7"><title>${esc(st.n)}: ${d.n} ${$('map-metric').selectedOptions[0].text.toLowerCase()} · ${money(d.value)}</title></path>`;
    });
    const viewMode = $('map-view') ? $('map-view').value : 'heat';
    if (viewMode === 'points') {
      // repaint states as a light base and draw pincode bubbles
      svg = svg.replace(/fill="rgb\([^"]*\)"/g, 'fill="#e7ecea"').replace(/fill="#e7ecea"/g, 'fill="#eef1ee"');
      const pts = (GEO.points && GEO.points[metric]) || [];
      const pmax = Math.max(1e-9, ...pts.map(p => p[mode]));
      const label = $('map-metric').selectedOptions[0].text.toLowerCase();
      pts.forEach(p => {
        const x = ((p.lon * K - minX) * sc).toFixed(1), y = ((-p.lat - minY) * sc).toFixed(1);
        const r = (4 + 14 * Math.sqrt(p[mode] / pmax)).toFixed(1);
        svg += `<circle cx="${x}" cy="${y}" r="${r}" fill="rgba(34,96,164,.55)" stroke="#174a82" stroke-width="1">` +
               `<title>PIN ${esc(p.pin)} — ${esc(p.customers.join(', '))}\n${p.n} ${label} · ${money(p.value)}</title></circle>`;
        if (p[mode] >= pmax * 0.5) svg += `<text x="${x}" y="${(+y - +r - 3).toFixed(1)}" text-anchor="middle" font-size="10" font-weight="700" fill="#174a82">${mode === 'n' ? p.n : window.DzCharts.short(p.value)}</text>`;
      });
    }
    svg += '</svg>';
    $('map-box').innerHTML = svg;
    if (viewMode === 'points') {
      const miss = (GEO.no_pincode && GEO.no_pincode[metric]) || 0;
      $('map-legend').innerHTML = 'Bubble size = ' + (mode === 'n' ? 'count' : 'value') + ' at that pincode · hover for details' +
        (miss ? ` &nbsp;·&nbsp; <span style="color:var(--warning);font-weight:700">${miss} record(s) have no pincode</span> — set pincodes in the Customers tab` : '');
    } else {
    const steps = [0, .25, .5, .75, 1];
    $('map-legend').innerHTML = 'Low ' + steps.map(t => `<span style="display:inline-block;width:26px;height:11px;background:${heatColor(t)};border:1px solid var(--line)"></span>`).join('') +
      ' High &nbsp;·&nbsp; max = ' + (mode === 'n' ? Math.round(max) : money(max));
    }
    $('map-title').textContent = '(' + $('map-metric').selectedOptions[0].text + ')';
    if (viewMode === 'points') {
      const pts = [...((GEO.points && GEO.points[metric]) || [])].sort((a, b) => b[mode] - a[mode]).slice(0, 12);
      $('map-rows').innerHTML = pts.map(p => `<tr><td>${esc(p.pin)} · ${esc(p.customers[0] || '')}${p.customers.length > 1 ? ' +' + (p.customers.length - 1) : ''}</td><td class="num">${p.n}</td><td class="num">${inr(p.value)}</td></tr>`).join('') || '<tr class="empty"><td colspan="3">No pincodes set yet — add pincodes to customers</td></tr>';
    } else {
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
  async function renderUsers() {
    const list = await api('/api/auth/users');
    const ov = await api('/api/rkz-overview').catch(() => null);
    const active = list.filter(u => u.active);
    $('view').innerHTML = `<section class="card filters"><div class="filter-actions"><button class="btn primary" id="btn-new-user">+ Add User</button></div>
      <div class="muted small">${active.length} active user(s) of ${list.length}. Only @duztec.in emails can be added; deactivated users are logged out immediately.</div></section>
      ${ov ? `<section class="card"><h2>RKZ Coverage</h2>
        <div class="table-wrap"><table><thead><tr><th>RKZ</th><th class="num">Enquiries</th><th class="num">Quotations</th><th class="num">Orders</th></tr></thead>
        <tbody>${ov.by_rkz.map(r => `<tr><td><b>${esc(r.rkz)}</b></td><td class="num">${r.enquiries}</td><td class="num">${r.quotations}</td><td class="num">${r.orders}</td></tr>`).join('')}
        <tr class="row-warning"><td><b>Unassigned</b></td><td class="num">${ov.unassigned.enquiries}</td><td class="num">${ov.unassigned.quotations}</td><td class="num">${ov.unassigned.orders}</td></tr></tbody></table></div>
        <div class="muted small" style="margin-top:6px">To assign old records: use the ✎ next to Salesperson/RKZ in the Quotations and Orders tables, or "Assign RKZ" on an enquiry card. Records without an RKZ are invisible to sales engineers (admins always see them).</div></section>` : ''}
      <section class="card"><div class="table-wrap"><table><thead><tr><th>Email</th><th>Name</th><th>RKZ</th><th>Role</th><th>Status</th><th>Last login</th><th>Actions</th></tr></thead>
      <tbody>${list.map(u => `<tr class="${u.active ? '' : 'row-critical'}"><td><b>${esc(u.email)}</b></td><td>${esc(u.name)}</td>
        <td><b>${esc(u.rkz || '—')}</b> <button class="btn small" data-rkz="${u.id}" title="Edit RKZ code">✎</button></td>
        <td>${pill(u.role === 'admin' ? 'won' : 'sent').replace('>won<', '>admin<').replace('>sent<', '>user<')}</td>
        <td>${u.active ? 'Active' : 'Deactivated'}</td><td>${esc(u.last_login || 'never')}</td>
        <td class="actions-cell">
          <button class="btn small" data-role="${u.id}" data-cur="${u.role}">${u.role === 'admin' ? 'Make user' : 'Make admin'}</button>
          <button class="btn small ${u.active ? 'danger' : 'secondary'}" data-toggle="${u.id}">${u.active ? 'Deactivate' : 'Reactivate'}</button>
        </td></tr>`).join('')}</tbody></table></div></section>
      <div class="muted small" style="margin-top:8px">RKZ = sales engineer code (e.g. RV). A sales engineer sees only enquiries, quotations and orders carrying their own RKZ; admins see everything.</div>`;
    $('btn-new-user').onclick = () => {
      openModal('Add User', `<div class="modal-form">
        <div class="full"><label>Duztec email</label><input id="nu-email" type="email" placeholder="name@duztec.in"></div>
        <div><label>Name</label><input id="nu-name"></div>
        <div><label>RKZ code</label><input id="nu-rkz" placeholder="e.g. RV" style="text-transform:uppercase"></div>
        <div><label>Role</label><select id="nu-role"><option value="user">Sales engineer (own RKZ data only)</option><option value="admin">Admin (sees everything)</option></select></div>
        <div class="full"><button class="btn primary" id="nu-save">Add User</button></div></div>`);
      $('nu-save').onclick = async () => { try {
        await api('/api/auth/users', { body: { email: $('nu-email').value, name: $('nu-name').value, role: $('nu-role').value, rkz: $('nu-rkz').value } });
        closeModal(); flash('User added — they can now log in with an OTP'); renderUsers();
      } catch (e) { flash(e.message, false); } };
    };
    const upd = async (u, patch) => { try {
      await api('/api/auth/users/' + u.id, { method: 'PUT', body: { email: u.email, name: u.name, role: patch.role ?? u.role, active: patch.active ?? u.active, rkz: patch.rkz ?? (u.rkz || '') } });
      renderUsers();
    } catch (e) { flash(e.message, false); } };
    document.querySelectorAll('[data-rkz]').forEach(b => b.onclick = () => { const u = list.find(x => x.id == b.dataset.rkz);
      const code = prompt('RKZ code for ' + u.email + ' (blank = none):', u.rkz || ''); if (code === null) return; upd(u, { rkz: code.trim().toUpperCase() }); });
    document.querySelectorAll('[data-role]').forEach(b => b.onclick = () => upd(list.find(x => x.id == b.dataset.role), { role: b.dataset.cur === 'admin' ? 'user' : 'admin' }));
    document.querySelectorAll('[data-toggle]').forEach(b => b.onclick = () => { const u = list.find(x => x.id == b.dataset.toggle); upd(u, { active: u.active ? 0 : 1 }); });
  }

  // ================= nav =================
  const VIEWS = { dash: renderDash, enquiries: renderEnquiries, quotes: renderQuotes, orders: renderOrders, customers: renderCustomers, followups: renderFollowups, users: renderUsers };
  const TITLES = { dash: 'Sales Dashboard', enquiries: 'Enquiries', quotes: 'Quotations', orders: 'Orders', customers: 'Customers', followups: 'Follow-ups', users: 'Users' };
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

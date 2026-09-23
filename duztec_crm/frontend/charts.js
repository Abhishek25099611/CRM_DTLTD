/* Tiny dependency-free SVG charts for the Duztec dashboard (shared by live page and snapshot). */
window.DzCharts = (function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const BLUE = '#2260a4', GREEN = '#a1c138', INK = '#191919', MUTED = '#667987', GRID = '#e3e7ec';
  const STATUS = { ok: '#16a34a', minor: '#eab308', warning: '#f59e0b', critical: '#dc2626' };
  const short = v => { const a = Math.abs(v); if (a >= 1e7) return (v / 1e7).toFixed(2).replace(/\.?0+$/, '') + ' Cr'; if (a >= 1e5) return (v / 1e5).toFixed(2).replace(/\.?0+$/, '') + ' L'; if (a >= 1e3) return (v / 1e3).toFixed(1).replace(/\.?0+$/, '') + ' K'; return String(Math.round(v)); };
  const nice = m => { if (m <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(m))); const f = m / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; };

  /* Vertical bars: items [{label, value, sub}] — single hue (magnitude) */
  function bars(el, items, opts = {}) {
    const W = el.clientWidth || 560, H = opts.height || 220, L = 52, R = 12, T = 22, B = 44;
    const max = nice(Math.max(1, ...items.map(i => i.value))); const n = items.length;
    const iw = (W - L - R) / n, bw = Math.max(6, Math.min(56, iw * 0.62));
    const y = v => T + (H - T - B) * (1 - v / max);
    let s = `<svg xmlns="${NS}" viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="${esc(opts.title || '')}">`;
    for (let k = 0; k <= 4; k++) { const v = max * k / 4, yy = y(v); s += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="${GRID}"/><text x="${L - 6}" y="${yy + 4}" text-anchor="end" font-size="11" fill="${MUTED}">${short(v)}</text>`; }
    items.forEach((it, i) => {
      const x = L + iw * i + (iw - bw) / 2, yy = y(it.value), h = Math.max(0, H - B - yy);
      s += `<g><title>${esc(it.label)}: ${esc(it.tip || it.value)}</title>`;
      s += `<rect x="${x}" y="${yy}" width="${bw}" height="${h}" rx="3" fill="${it.color || BLUE}"/>`;
      if (it.value > 0) s += `<text x="${x + bw / 2}" y="${yy - 5}" text-anchor="middle" font-size="11" font-weight="600" fill="${INK}">${esc(it.top ?? short(it.value))}</text>`;
      const lab = it.label.replace(/\s*days?$/i, '').replace(/^Not yet due$/i, 'Not due');
      s += `<text x="${x + bw / 2}" y="${H - B + 15}" text-anchor="middle" font-size="${n > 5 ? 10 : 11}" fill="${MUTED}">${esc(lab)}</text>`;
      if (it.sub) s += `<text x="${x + bw / 2}" y="${H - B + 29}" text-anchor="middle" font-size="10" fill="${MUTED}">${esc(it.sub)}</text>`;
      s += '</g>';
    });
    el.innerHTML = s + '</svg>';
  }

  /* Horizontal bars: items [{label, value, tip}] */
  function hbars(el, items, opts = {}) {
    const W = el.clientWidth || 560, rowH = 26, L = Math.min(230, Math.round(W * 0.46)), R = 64, T = 8; const maxChars = Math.max(12, Math.floor((L - 12) / 7.4));
    const H = T + rowH * Math.max(1, items.length) + 8; const max = Math.max(1, ...items.map(i => i.value));
    let s = `<svg xmlns="${NS}" viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="${esc(opts.title || '')}">`;
    items.forEach((it, i) => {
      const yy = T + rowH * i, w = Math.max(2, (W - L - R) * it.value / max); const lab = it.label.length > maxChars ? it.label.slice(0, maxChars - 1).trimEnd() + '…' : it.label;
      s += `<g><title>${esc(it.label)}: ${esc(it.tip || it.value)}</title><text x="${L - 8}" y="${yy + 17}" text-anchor="end" font-size="12" fill="${INK}">${esc(lab)}</text>`;
      s += `<rect x="${L}" y="${yy + 5}" width="${w}" height="${rowH - 10}" rx="3" fill="${it.color || BLUE}"/>`;
      s += `<text x="${L + w + 6}" y="${yy + 17}" font-size="11" font-weight="600" fill="${INK}">${esc(it.top ?? short(it.value))}</text></g>`;
    });
    if (!items.length) s += `<text x="${W / 2}" y="${H / 2}" text-anchor="middle" font-size="12" fill="${MUTED}">No data</text>`;
    el.innerHTML = s + '</svg>';
  }

  /* Stacked 100% status bars: rows [{label, parts:[{key,label,value,fmt}]}] */
  function stacked(el, rows, opts = {}) {
    const W = el.clientWidth || 560, rowH = 40, L = 70, R = 12, T = 6, LEG = 24;
    const H = T + rowH * rows.length + LEG + 4; let s = `<svg xmlns="${NS}" viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="${esc(opts.title || '')}">`;
    rows.forEach((r, i) => {
      const tot = r.parts.reduce((a, p) => a + p.value, 0) || 1; let x = L; const yy = T + rowH * i;
      s += `<text x="${L - 8}" y="${yy + 21}" text-anchor="end" font-size="12" font-weight="600" fill="${INK}">${esc(r.label)}</text>`;
      r.parts.forEach(p => { const w = (W - L - R) * p.value / tot; if (w <= 0) return; const pct = Math.round(1000 * p.value / tot) / 10;
        s += `<g><title>${esc(p.label)}: ${esc(p.fmt ?? p.value)} (${pct}%)</title><rect x="${x + 1}" y="${yy + 6}" width="${Math.max(0, w - 2)}" height="${rowH - 14}" rx="3" fill="${STATUS[p.key] || BLUE}"/>`;
        if (w > 44) s += `<text x="${x + w / 2}" y="${yy + 23}" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">${pct}%</text>`; s += '</g>'; x += w; });
    });
    let lx = L, ly = T + rowH * rows.length + 14; const legend = opts.legend || []; let lines = 1;
    legend.forEach(p => { const w = 14 + p.label.length * 6.2 + 16; if (lx + w > W - R && lx > L) { lx = L; ly += 18; lines++; }
      s += `<rect x="${lx}" y="${ly - 9}" width="10" height="10" rx="2" fill="${STATUS[p.key] || BLUE}"/><text x="${lx + 14}" y="${ly}" font-size="11" fill="${MUTED}">${esc(p.label)}</text>`; lx += w; });
    const H2 = H + (lines - 1) * 18;
    el.innerHTML = s.replace(`viewBox="0 0 ${W} ${H}" width="100%" height="${H}"`, `viewBox="0 0 ${W} ${H2}" width="100%" height="${H2}"`) + '</svg>';
  }
  return { bars, hbars, stacked, short, STATUS };
})();

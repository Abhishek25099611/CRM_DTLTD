"""Quotation -> print-ready HTML on the Duztec letterhead."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from .config import SETTINGS

_LOGO = Path(__file__).resolve().parent.parent / "frontend" / "duztec-logo.png"

ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
        "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _2d(n: int) -> str:
    if n < 20:
        return ONES[n]
    return (TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")).strip()


def _3d(n: int) -> str:
    s = ""
    if n >= 100:
        s = ONES[n // 100] + " Hundred"
        if n % 100:
            s += " " + _2d(n % 100)
        return s
    return _2d(n)


def amount_in_words(v: float) -> str:
    n = int(round(v))
    if n == 0:
        return "Zero Rupees Only"
    parts = []
    for div, name in ((10**7, "Crore"), (10**5, "Lakh"), (1000, "Thousand")):
        if n >= div:
            parts.append(_3d(n // div) + " " + name)
            n %= div
    if n:
        parts.append(_3d(n))
    return "Rupees " + " ".join(parts) + " Only"


def inr(v: float) -> str:
    neg = v < 0
    v = abs(round(float(v), 2))
    whole, frac = divmod(v, 1)
    s = str(int(whole))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        p = []
        while len(head) > 2:
            p.insert(0, head[-2:]); head = head[:-2]
        if head:
            p.insert(0, head)
        s = ",".join(p) + "," + tail
    return ("-" if neg else "") + f"{s}.{int(round(frac * 100)):02d}"


def render(q: dict, items: list[dict], customer: dict, contact: dict | None) -> str:
    c = SETTINGS.company
    logo = "data:image/png;base64," + base64.b64encode(_LOGO.read_bytes()).decode()
    items = [{**i, "qty": i["qty"] or 0, "rate": i["rate"] or 0, "gst_pct": i["gst_pct"] or 0} for i in items]
    sub = sum(i["qty"] * i["rate"] for i in items)
    disc = sub * (q.get("discount_pct") or 0) / 100
    taxable = sub - disc
    gst_amt = sum(i["qty"] * i["rate"] * (1 - (q.get("discount_pct") or 0) / 100) * (i.get("gst_pct") or 0) / 100 for i in items)
    total = taxable + gst_amt
    intra = (q.get("gst_mode") or "intra") == "intra"
    valid_till = ""
    try:
        valid_till = (datetime.strptime(q["date"], "%Y-%m-%d") + timedelta(days=int(q.get("validity_days") or 30))).strftime("%d-%b-%Y")
    except ValueError:
        pass
    rows = "".join(
        f"<tr><td class='num'>{i['sr']}</td><td>{escape(i['description'])}</td><td>{escape(i.get('hsn') or '')}</td>"
        f"<td class='num'>{i['qty']:g}</td><td>{escape(i.get('unit') or '')}</td><td class='num'>{inr(i['rate'])}</td>"
        f"<td class='num'>{i.get('gst_pct') or 0:g}%</td><td class='num'>{inr(i['qty'] * i['rate'])}</td></tr>"
        for i in items)
    gst_rows = (f"<tr><td colspan='7' class='num lbl'>CGST</td><td class='num'>{inr(gst_amt / 2)}</td></tr>"
                f"<tr><td colspan='7' class='num lbl'>SGST</td><td class='num'>{inr(gst_amt / 2)}</td></tr>") if intra else \
               f"<tr><td colspan='7' class='num lbl'>IGST</td><td class='num'>{inr(gst_amt)}</td></tr>"
    disc_row = f"<tr><td colspan='7' class='num lbl'>Discount ({q.get('discount_pct'):g}%)</td><td class='num'>-{inr(disc)}</td></tr>" if disc else ""
    ref = f"{q['quote_no']}{('-' + q['rev']) if q.get('rev') else ''}"
    ct = f"<br>Kind Attn: {escape(contact['name'])}" + (f" · {escape(contact['phone'])}" if contact and contact.get("phone") else "") if contact else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Quotation {escape(ref)}</title>
<style>
 body{{font-family:Nunito,Segoe UI,Arial,sans-serif;color:#191919;margin:32px;font-size:13px}}
 .lh{{border-bottom:3px solid #a1c138;padding-bottom:10px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:flex-end}}
 .lh img{{height:58px}} .lh small{{color:#667987;display:block;max-width:420px}}
 .qh{{text-align:right}} .qh b{{color:#2260a4;font-size:18px}}
 table{{border-collapse:collapse;width:100%;margin:10px 0}} th,td{{border:1px solid #bbb;padding:5px 8px;text-align:left;vertical-align:top}}
 th{{background:#eceff8;color:#2260a4}} td.num,th.num{{text-align:right}} td.lbl{{font-weight:bold;background:#f7f7f7}}
 .total td{{font-weight:bold;background:#f0f4e4}}
 .terms td{{border:0;padding:2px 4px;font-size:12.5px}} .terms td:first-child{{color:#667987;width:130px}}
 .foot{{margin-top:30px;display:flex;justify-content:space-between}} .sign{{text-align:center;color:#333}}
 .sign .line{{margin-top:52px;border-top:1px solid #999;padding-top:4px}}
 .noprint{{margin-bottom:10px}} @media print{{.noprint{{display:none}} body{{margin:10mm}}}}
</style></head><body>
<div class="noprint"><button onclick="window.print()">Print / Save as PDF</button></div>
<div class="lh"><div><img src="{logo}" alt="{escape(SETTINGS.company_name)}"><small>{escape(c.get('address',''))}</small>
<small>CIN: {escape(c.get('cin',''))} · GSTIN: {escape(c.get('gstin',''))}</small></div>
<div class="qh"><b>QUOTATION</b><br>No: <b>{escape(ref)}</b><br>Date: {escape(q['date'])}<br>Valid till: {valid_till}</div></div>
<p><b>To:</b> {escape(customer['name'])}<br>{escape(customer.get('address') or '')}{ct}</p>
<p>Dear Sir/Madam,<br>With reference to your enquiry, we are pleased to submit our offer as under:</p>
<table><thead><tr><th class="num">#</th><th>Description</th><th>HSN</th><th class="num">Qty</th><th>Unit</th><th class="num">Rate (₹)</th><th class="num">GST</th><th class="num">Amount (₹)</th></tr></thead>
<tbody>{rows}
<tr><td colspan='7' class='num lbl'>Sub Total</td><td class='num'>{inr(sub)}</td></tr>
{disc_row}{gst_rows}
<tr class="total"><td colspan='7' class='num'>Grand Total</td><td class='num'>₹ {inr(total)}</td></tr>
</tbody></table>
<p><i>{escape(amount_in_words(total))}</i></p>
<table class="terms">
<tr><td>Delivery</td><td>{escape(q.get('delivery_terms') or '')}</td></tr>
<tr><td>Payment</td><td>{escape(q.get('payment_terms') or '')}</td></tr>
<tr><td>Validity</td><td>{q.get('validity_days')} days from quotation date</td></tr>
<tr><td>Notes</td><td>{escape(q.get('notes') or '')}</td></tr>
<tr><td>Bank details</td><td>{escape(c.get('bank_details') or '')}</td></tr>
</table>
<div class="foot"><div>Thanking you,<br>Yours faithfully,</div>
<div class="sign">For <b>{escape(SETTINGS.company_name)}</b><div class="line">Authorised Signatory{(' · ' + escape(q['salesperson'])) if q.get('salesperson') else ''}</div></div></div>
</body></html>"""

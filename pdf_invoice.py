"""English A4 invoice PDF matching the official POSCO Group University form."""

from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import HexColor, white, black, Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from config import Config, POSCO_CI_PATH, STAMP_PATH


def _soft_fonts():
    fonts = Path(r"C:\Windows\Fonts")
    regular = fonts / "calibri.ttf"
    bold = fonts / "calibrib.ttf"
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont("SoftSans", str(regular)))
        pdfmetrics.registerFont(TTFont("SoftSans-Bold", str(bold)))
        return "SoftSans", "SoftSans-Bold"
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = _soft_fonts()

NAVY = HexColor("#001B4D")
INK = HexColor("#1A2332")
MUTED = HexColor("#7B8594")
RULE = HexColor("#E6E9EE")
BAND = HexColor("#F4F6F8")
RED_SEAL = HexColor("#C41E3A")


def _money(currency: str, value) -> str:
    return f"{currency} {float(value):,.2f}"


def _num(value) -> str:
    return f"{float(value):,.2f}"


def money_fx_amount(amount_krw, rate) -> float:
    if not rate:
        return 0.0
    return round(float(amount_krw) / float(rate), 2)


def _width(text, font, size):
    return pdfmetrics.stringWidth(str(text or ""), font, size)


def _wrap_width(text, font, size, max_w):
    raw = str(text or "").replace("\r", "").strip()
    if not raw:
        return [""]
    lines = []
    for para in raw.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = ""
        for word in words:
            trial = (cur + " " + word).strip()
            if _width(trial, font, size) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
    return lines or [""]


def _draw_posco_ci(c, x, y, height_pt):
    """Official POSCO wordmark. y is the bottom of the logo."""
    if POSCO_CI_PATH.exists():
        img = ImageReader(str(POSCO_CI_PATH))
        iw, ih = img.getSize()
        w = height_pt * (iw / ih)
        c.drawImage(str(POSCO_CI_PATH), x, y, width=w, height=height_pt, mask="auto", preserveAspectRatio=True)
        return w
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 16)
    c.drawString(x, y + 1.2 * mm, "posco")
    return _width("posco", FONT_BOLD, 16)


def generate_invoice_pdf(invoice, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 18 * mm
    content_w = width - 2 * margin
    header_h = 26 * mm

    c.setFillColor(NAVY)
    c.rect(0, height - header_h, width, header_h, fill=1, stroke=0)

    _draw_posco_ci(c, margin, height - 17.6 * mm, 12.4 * mm)
    c.setFillColor(white)
    c.setFont(FONT, 7)
    c.drawString(margin, height - 22.2 * mm, "Education Service")

    c.setFont(FONT_BOLD, 18)
    c.drawRightString(width - margin, height - 10.4 * mm, "INVOICE")
    c.setFont(FONT, 7.5)
    date_label = "Document Date"
    ref_label = "Ref. No."
    date_val = invoice.document_date.strftime("%Y-%m-%d") if invoice.document_date else ""
    label_x = width - margin - 42 * mm
    c.drawString(label_x, height - 16.2 * mm, date_label)
    c.drawString(label_x, height - 20.6 * mm, ref_label)
    c.setFont(FONT_BOLD, 8)
    c.drawRightString(width - margin, height - 16.2 * mm, date_val)
    c.drawRightString(width - margin, height - 20.6 * mm, invoice.invoice_no)

    y = height - header_h - 12 * mm
    col_gap = 10 * mm
    col_w = (content_w - col_gap) / 2
    left_x = margin
    right_x = margin + col_w + col_gap

    sub = invoice.subsidiary
    billed = [sub.name_en or ""]
    if getattr(sub, "code", ""):
        billed.append(f"Entity Code: {sub.code}")
    billed.extend(str(sub.address_en or "").replace("\r", "").splitlines())
    billed = [line.strip() for line in billed if str(line).strip()]

    issued = [Config.PGU_NAME]
    issued.extend(str(Config.PGU_ADDRESS or "").replace("\r", "").splitlines())
    phone = (getattr(Config, "PGU_PHONE", "") or "").strip()
    if phone:
        issued.append(f"Tel: {phone}")
    issued = [line.strip() for line in issued if str(line).strip()]

    def party_block(x, title, lines, name_first=True):
        c.setFillColor(MUTED)
        c.setFont(FONT, 7)
        c.drawString(x, y, title)
        ty = y - 5.4 * mm
        for i, line in enumerate(lines):
            wrapped = _wrap_width(line, FONT_BOLD if i == 0 and name_first else FONT, 10 if i == 0 and name_first else 8, col_w)
            for j, part in enumerate(wrapped):
                if i == 0 and j == 0 and name_first:
                    c.setFillColor(NAVY)
                    c.setFont(FONT_BOLD, 11)
                else:
                    c.setFillColor(INK)
                    c.setFont(FONT, 8)
                c.drawString(x, ty, part)
                ty -= 4.0 * mm if i == 0 and j == 0 and name_first else 3.6 * mm
        return ty

    left_bottom = party_block(left_x, "BILLED TO", billed)
    right_bottom = party_block(right_x, "ISSUED BY", issued)
    y = min(left_bottom, right_bottom) - 5 * mm

    band_h = 13 * mm
    c.setFillColor(BAND)
    c.roundRect(margin, y - band_h, content_w, band_h, 1.5, fill=1, stroke=0)
    fx_text = f"1 {invoice.currency} = {float(invoice.exchange_rate):,.2f} KRW"
    meta = [
        ("CURRENCY", invoice.currency or ""),
        ("FX RATE", fx_text),
        ("RATE DATE", invoice.rate_date.strftime("%Y-%m-%d") if invoice.rate_date else ""),
        ("VAT", "Exempt 0%"),
    ]
    meta_w = content_w / 4
    for i, (label, value) in enumerate(meta):
        mx = margin + i * meta_w
        if i:
            c.setStrokeColor(HexColor("#E0E4EA"))
            c.setLineWidth(0.5)
            c.line(mx, y - 2.6 * mm, mx, y - band_h + 2.6 * mm)
        c.setFillColor(MUTED)
        c.setFont(FONT, 6.5)
        c.drawString(mx + 4 * mm, y - 4.4 * mm, label)
        c.setFillColor(NAVY)
        c.setFont(FONT_BOLD, 9)
        c.drawString(mx + 4 * mm, y - 9.6 * mm, str(value))

    y = y - band_h - 7 * mm
    c.setFillColor(INK)
    c.setFont(FONT, 9)
    c.drawString(margin, y, "I request it as follows :")

    y -= 6 * mm
    cur = invoice.currency or "USD"
    col_no = 10 * mm
    col_period = 38 * mm
    col_qty = 12 * mm
    col_unit = 28 * mm
    col_amt = 26 * mm
    col_desc = content_w - (col_no + col_period + col_qty + col_unit + col_amt)
    headers = [
        ("No.", col_no, "c"),
        ("Education Service Descriptions", col_desc, "l"),
        ("Activity Period", col_period, "c"),
        ("Qty", col_qty, "c"),
        (f"Unit Price ({cur})", col_unit, "r"),
        (f"Amount ({cur})", col_amt, "r"),
    ]

    head_h = 8 * mm
    c.setFillColor(BAND)
    c.rect(margin, y - head_h, content_w, head_h, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.setFont(FONT, 7)
    x = margin
    for label, w, align in headers:
        ty = y - 5 * mm
        if align == "c":
            c.drawCentredString(x + w / 2, ty, label)
        elif align == "r":
            c.drawRightString(x + w - 1.5 * mm, ty, label)
        else:
            c.drawString(x + 2 * mm, ty, label)
        x += w

    y -= head_h
    period = ""
    if invoice.period_start and invoice.period_end:
        period = f"{invoice.period_start.strftime('%Y-%m-%d')} ~ {invoice.period_end.strftime('%Y-%m-%d')}"
    items = list(invoice.items or []) or [None]
    compact = len(items) > 5
    body_size = 7.4 if compact else 8
    for idx, it in enumerate(items):
        if it is None:
            title = invoice.education_name
            ps = invoice.period_start
            pe = invoice.period_end
            qty = invoice.qty
            amount_krw = invoice.amount_krw
        else:
            title = it.description or invoice.education_name
            ps = it.period_start or invoice.period_start
            pe = it.period_end or invoice.period_end
            qty = it.qty
            amount_krw = it.amount_krw
        line_period = (
            f"{ps.strftime('%Y-%m-%d')} ~ {pe.strftime('%Y-%m-%d')}" if ps and pe else period
        )
        line_fx = money_fx_amount(amount_krw, invoice.exchange_rate)
        unit_fx = (float(line_fx) / qty) if qty else 0
        desc_lines = _wrap_width(title, FONT, body_size, col_desc - 4 * mm)
        row_h = max((8.5 if compact else 10) * mm, 3.4 * mm * len(desc_lines) + 4.2 * mm)
        if y - row_h < 62 * mm:
            c.showPage()
            y = height - 16 * mm
        c.setStrokeColor(RULE)
        c.setLineWidth(0.4)
        c.line(margin, y - row_h, margin + content_w, y - row_h)
        mid = y - row_h / 2 - 1.1 * mm
        c.setFillColor(INK)
        c.setFont(FONT, body_size)
        c.drawCentredString(margin + col_no / 2, mid, str(idx + 1))
        ty = y - 4.2 * mm
        for line in desc_lines:
            c.drawString(margin + col_no + 2 * mm, ty, line)
            ty -= 3.4 * mm
        px = margin + col_no + col_desc
        c.drawCentredString(px + col_period / 2, mid, line_period)
        c.drawCentredString(px + col_period + col_qty / 2, mid, str(qty))
        c.drawRightString(px + col_period + col_qty + col_unit - 2 * mm, mid, _num(unit_fx))
        c.setFont(FONT_BOLD, body_size)
        c.drawRightString(margin + content_w - 2 * mm, mid, _num(line_fx))
        y -= row_h

    y -= 7 * mm
    total_x = margin + content_w
    label_x = total_x - 62 * mm
    c.setFillColor(MUTED)
    c.setFont(FONT, 8)
    c.drawString(label_x, y, "VAT (Exempt)")
    c.drawRightString(total_x, y, _money(cur, 0))
    y -= 6.2 * mm
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.7)
    c.line(label_x, y + 3.4 * mm, total_x, y + 3.4 * mm)
    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 9.5)
    c.drawString(label_x, y, "TOTAL AMOUNT DUE (NET)")
    c.setFont(FONT_BOLD, 11)
    c.drawRightString(total_x, y, _money(cur, invoice.amount_fx))

    y -= 12 * mm
    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 8.5)
    c.drawString(margin, y, "WIRE TRANSFER PROTOCOL")
    y -= 3.2 * mm
    box_h = 22 * mm
    c.setFillColor(BAND)
    c.roundRect(margin, y - box_h, content_w, box_h, 1.5, fill=1, stroke=0)

    left_bank = [
        ("BANK", Config.BANK_NAME),
        ("BRANCH", Config.BANK_BRANCH),
        ("ACCOUNT NAME", Config.BANK_ACCOUNT_NAME),
    ]
    right_bank = [
        ("ACCOUNT NO.", Config.BANK_ACCOUNT_NO),
        ("SWIFT CODE", Config.BANK_SWIFT),
    ]
    row_gap = 6.2 * mm
    for i, (label, value) in enumerate(left_bank):
        yy = y - 5.4 * mm - i * row_gap
        c.setFillColor(MUTED)
        c.setFont(FONT, 6.8)
        c.drawString(margin + 4 * mm, yy, label)
        c.setFillColor(NAVY)
        c.setFont(FONT_BOLD, 8.5)
        c.drawString(margin + 32 * mm, yy, value or "")
    for i, (label, value) in enumerate(right_bank):
        yy = y - 5.4 * mm - i * row_gap
        c.setFillColor(MUTED)
        c.setFont(FONT, 6.8)
        c.drawString(margin + content_w / 2 + 4 * mm, yy, label)
        c.setFillColor(NAVY)
        c.setFont(FONT_BOLD, 8.5)
        c.drawString(margin + content_w / 2 + 32 * mm, yy, value or "")

    y = y - box_h - 10 * mm
    sig_x = width - margin - 58 * mm
    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 8)
    c.drawRightString(width - margin, y, "AUTHORIZED EXECUTIVE")
    stamp_y = y - 32 * mm
    if STAMP_PATH.exists():
        c.drawImage(
            str(STAMP_PATH),
            sig_x + 16 * mm,
            stamp_y,
            width=26 * mm,
            height=26 * mm,
            mask="auto",
            preserveAspectRatio=True,
        )
    else:
        cx, cy, r = sig_x + 29 * mm, stamp_y + 13 * mm, 11 * mm
        c.setStrokeColor(RED_SEAL)
        c.setFillColor(Color(1, 1, 1, alpha=0))
        c.setLineWidth(1.3)
        c.circle(cx, cy, r, stroke=1, fill=0)
        c.setLineWidth(0.6)
        c.circle(cx, cy, r - 2.1 * mm, stroke=1, fill=0)
        c.setFillColor(RED_SEAL)
        c.setFont(FONT, 5.2)
        c.drawCentredString(cx, cy + 2.2 * mm, "POSCO GROUP")
        c.drawCentredString(cx, cy - 1.2 * mm, "UNIVERSITY")
        c.setFont(FONT, 4.6)
        c.drawCentredString(cx, cy - 5.2 * mm, "OFFICIAL SEAL")

    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 10)
    c.drawRightString(width - margin, stamp_y - 1.5 * mm, Config.PGU_SIGNATORY)
    c.setFillColor(MUTED)
    c.setFont(FONT, 7.5)
    c.drawRightString(width - margin, stamp_y - 5.4 * mm, Config.PGU_TITLE)

    y = min(y - 4 * mm, stamp_y - 10 * mm)
    if y < 42 * mm:
        c.showPage()
        y = height - 18 * mm
    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 8)
    c.drawString(margin, y, "LEGAL DISCLAIMERS")
    notes = [
        "Late payment may incur interest and/or administrative fees in accordance with the applicable education service arrangement.",
        "Foreign currency amounts are converted from the KRW cost basis using the exchange rate and rate-determination date stated on this invoice.",
        f"This invoice is issued for education services provided by {Config.PGU_NAME} and is not subject to Value Added Tax (VAT 0%, exempt).",
        "Please quote the Reference No. on the wire remittance.",
        "This document constitutes an official request for payment.",
    ]
    c.setFillColor(MUTED)
    c.setFont(FONT, 6.6)
    y -= 4.2 * mm
    for i, note in enumerate(notes, 1):
        wrapped = _wrap_width(note, FONT, 6.6, content_w - 7 * mm)
        c.drawString(margin, y, f"{i}")
        for part in wrapped:
            c.drawString(margin + 4.2 * mm, y, part)
            y -= 3.15 * mm
        y -= 0.6 * mm

    c.showPage()
    c.save()
    output_path.write_bytes(buf.getvalue())
    return output_path

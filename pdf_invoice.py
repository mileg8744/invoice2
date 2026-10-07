"""English A4 invoice PDF (ReportLab)."""

from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from config import Config, STAMP_PATH


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

NAVY = HexColor("#002060")
STEEL = HexColor("#1F4E79")
LIGHT = HexColor("#F0F4F8")
LINE = HexColor("#C5D0DC")
MUTED = HexColor("#5B6770")
GOLD = HexColor("#C5A46E")


def _money(currency: str, value) -> str:
    return f"{currency} {float(value):,.2f}"


def _krw(value) -> str:
    return f"KRW {int(value):,}"


def money_fx_amount(amount_krw, rate) -> float:
    if not rate:
        return 0.0
    return round(float(amount_krw) / float(rate), 2)


def generate_invoice_pdf(invoice, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 16 * mm

    # Header bar
    c.setFillColor(NAVY)
    c.rect(0, height - 28 * mm, width, 28 * mm, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(0, height - 29.4 * mm, width, 1.4 * mm, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont(FONT_BOLD, 22)
    c.drawString(margin, height - 14 * mm, "INVOICE")
    c.setFont(FONT, 8.5)
    c.drawString(margin, height - 20 * mm, "POSCO GROUP UNIVERSITY  ·  EDUCATION SERVICE")
    c.setFont(FONT, 8)
    c.drawRightString(width - margin, height - 12 * mm, "Document Date")
    c.setFont(FONT_BOLD, 10)
    c.drawRightString(
        width - margin,
        height - 16.5 * mm,
        invoice.document_date.strftime("%Y-%m-%d"),
    )
    c.setFont(FONT, 8)
    c.drawRightString(width - margin, height - 21.5 * mm, "Reference No.")
    c.setFont(FONT_BOLD, 11)
    c.drawRightString(width - margin, height - 26 * mm, invoice.invoice_no)

    content_w = width - 2 * margin
    gap = 8 * mm
    box_w = (content_w - gap) / 2
    wrap_chars = max(28, int(box_w / (2.05 * mm)))

    sub = invoice.subsidiary
    billed_lines = []
    for line in [sub.name_en, sub.address_en or ""]:
        billed_lines.extend(_wrap(line, wrap_chars))
    sender_lines = []
    for line in [
        Config.PGU_NAME,
        getattr(Config, "PGU_DEPT", "") or "",
        *str(Config.PGU_ADDRESS or "").replace("\r", "").splitlines(),
        f"Tel: {Config.PGU_PHONE.strip()}" if (getattr(Config, "PGU_PHONE", "") or "").strip() else "",
    ]:
        text = (line or "").strip()
        if text:
            sender_lines.extend(_wrap(text, wrap_chars))
    line_h = 3.6 * mm
    box_h = max(32 * mm, 10 * mm + line_h * max(len(billed_lines), len(sender_lines), 4))
    y = height - 38 * mm

    def party_box(x, title, lines):
        bottom = y - box_h + 8 * mm
        c.setFillColor(LIGHT)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.roundRect(x, bottom, box_w, box_h, 3, fill=1, stroke=1)
        c.setFillColor(NAVY)
        c.rect(x, y + 1 * mm, box_w, 7 * mm, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 8)
        c.drawString(x + 4 * mm, y + 3.2 * mm, title)
        c.setFillColor(black)
        c.setFont(FONT, 8)
        ty = y - 3.2 * mm
        for wrapped in lines:
            if ty < bottom + 2.5 * mm:
                break
            c.drawString(x + 4 * mm, ty, wrapped)
            ty -= line_h

    party_box(margin, "BILLED ENTITY", billed_lines)
    party_box(margin + box_w + gap, "AUTHORIZED SENDER", sender_lines)

    # Meta strip
    y = y - box_h - 2 * mm
    c.setFillColor(STEEL)
    c.roundRect(margin, y - 10 * mm, width - 2 * margin, 12 * mm, 2, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FONT, 7.5)
    period = f"{invoice.period_start.strftime('%Y-%m-%d')}  ~  {invoice.period_end.strftime('%Y-%m-%d')}"
    meta = [
        ("Currency", invoice.currency),
        ("FX Rate", f"1 {invoice.currency} = {invoice.exchange_rate:,.4f} KRW"),
        ("Rate Date", invoice.rate_date.strftime("%Y-%m-%d")),
        ("VAT", "Exempt 0%"),
    ]
    col_w = (width - 2 * margin) / 4
    for i, (k, v) in enumerate(meta):
        c.setFont(FONT, 7)
        c.drawString(margin + 4 * mm + i * col_w, y - 1.5 * mm, k.upper())
        c.setFont(FONT_BOLD, 8.5)
        c.drawString(margin + 4 * mm + i * col_w, y - 6.2 * mm, str(v))

    # Table (same overall width as the two party boxes)
    y = y - 22 * mm
    col_desc = content_w * 0.42
    col_period = content_w * 0.20
    col_qty = content_w * 0.08
    col_unit = content_w * 0.15
    col_amount = content_w - (col_desc + col_period + col_qty + col_unit)
    headers = [
        ("Education Service Descriptions", col_desc),
        ("Activity Period", col_period),
        ("Qty", col_qty),
        ("Unit Price", col_unit),
        ("Amount", col_amount),
    ]
    table_w = content_w
    c.setFillColor(NAVY)
    c.rect(margin, y - 1 * mm, table_w, 8 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 7.2)
    x = margin
    for label, w in headers:
        c.drawString(x + 2 * mm, y + 1.6 * mm, label)
        x += w

    y -= 8 * mm
    items = list(invoice.items or []) or [None]
    compact = len(items) > 4
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
        line_period = f"{ps.strftime('%Y-%m-%d')}  ~  {pe.strftime('%Y-%m-%d')}" if ps and pe else period
        line_fx = money_fx_amount(amount_krw, invoice.exchange_rate)
        unit_fx = (float(line_fx) / qty) if qty else 0
        desc_lines = [title]
        row_h = 9 * mm if compact else max(11 * mm, 3.6 * mm * (len(desc_lines) + 0.6))
        bg = HexColor("#FAFCFF") if idx % 2 == 0 else white
        c.setFillColor(bg)
        c.rect(margin, y - row_h + 6 * mm, table_w, row_h, fill=1, stroke=0)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.3)
        c.rect(margin, y - row_h + 6 * mm, table_w, row_h, fill=0, stroke=1)
        ty = y + 1.2 * mm
        for i, line in enumerate(desc_lines):
            c.setFont(FONT_BOLD if i == 0 else FONT, 7.2 if i else 8)
            c.setFillColor(NAVY if i == 0 else MUTED)
            for wrapped in _wrap(line, max(24, int(headers[0][1] / (1.7 * mm)))):
                c.drawString(margin + 2 * mm, ty, wrapped)
                ty -= 3.2 * mm
        c.setFillColor(black)
        c.setFont(FONT, 7.4)
        c.drawString(margin + headers[0][1] + 1.5 * mm, y - 1 * mm, line_period)
        c.drawRightString(margin + sum(h[1] for h in headers[:3]) - 2 * mm, y - 1 * mm, str(qty))
        c.drawRightString(
            margin + sum(h[1] for h in headers[:4]) - 2 * mm,
            y - 1 * mm,
            _money(invoice.currency, unit_fx),
        )
        c.setFont(FONT_BOLD, 8)
        c.drawRightString(margin + table_w - 2 * mm, y - 1 * mm, _money(invoice.currency, line_fx))
        y = y - row_h

    y -= 5 * mm
    c.setFillColor(LIGHT)
    c.rect(margin, y - 14 * mm, table_w, 16 * mm, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.setFont(FONT, 8)
    c.drawString(margin + 3 * mm, y - 3 * mm, "VAT (Exempt)")
    c.drawRightString(margin + table_w - 3 * mm, y - 3 * mm, _money(invoice.currency, 0))
    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 12)
    c.drawString(margin + 3 * mm, y - 10 * mm, "NET AGGREGATE DUE")
    c.drawRightString(margin + table_w - 3 * mm, y - 10 * mm, _money(invoice.currency, invoice.amount_fx))

    # Wire transfer
    y = y - 26 * mm
    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 8)
    c.drawString(margin, y + 6 * mm, "WIRE TRANSFER PROTOCOLS")
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(margin, y + 4.5 * mm, margin + 55 * mm, y + 4.5 * mm)

    c.setFillColor(LIGHT)
    c.roundRect(margin, y - 28 * mm, width - 2 * margin, 32 * mm, 3, fill=1, stroke=0)
    bank_rows = [
        ("Bank", Config.BANK_NAME),
        ("Branch", Config.BANK_BRANCH),
        ("Account Name", Config.BANK_ACCOUNT_NAME),
        ("Account No.", Config.BANK_ACCOUNT_NO),
        ("BIC (Swift Code)", Config.BANK_SWIFT),
    ]
    c.setFillColor(black)
    col1 = margin + 4 * mm
    col2 = margin + (width - 2 * margin) / 2 + 2 * mm
    for i, (k, v) in enumerate(bank_rows):
        xx = col1 if i < 3 else col2
        yy = y - 2 * mm - (i % 3) * 8 * mm
        c.setFont(FONT, 7)
        c.setFillColor(MUTED)
        c.drawString(xx, yy, k.upper())
        c.setFont(FONT_BOLD, 9)
        c.setFillColor(NAVY)
        c.drawString(xx, yy - 3.6 * mm, v)

    # Disclaimer + signature
    y = y - 38 * mm
    c.setFillColor(MUTED)
    c.setFont(FONT, 6.6)
    legal = (
        "Legal Disclaimers: Late payment may incur interest and/or administrative fees in accordance with the applicable "
        f"education service arrangement. Foreign currency amounts are converted from the KRW cost basis using the exchange "
        f"rate and rate-determination date stated on this invoice. This invoice is issued for education services provided by "
        f"{Config.PGU_NAME} and is not subject to Value Added Tax (VAT 0%, exempt). Please quote the Reference No. on "
        "the wire remittance. This document constitutes an official request for payment."
    )
    text_obj = c.beginText(margin, y + 8 * mm)
    text_obj.setFont(FONT, 6.6)
    text_obj.setFillColor(MUTED)
    for line in _wrap(legal, 128):
        text_obj.textLine(line)
    c.drawText(text_obj)

    # Signature block
    sig_x = width - margin - 62 * mm
    sig_y = 18 * mm
    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 8)
    c.drawString(sig_x, sig_y + 28 * mm, "AUTHORIZED EXECUTIVE")
    if STAMP_PATH.exists():
        c.drawImage(
            str(STAMP_PATH),
            sig_x + 18 * mm,
            sig_y + 6 * mm,
            width=28 * mm,
            height=28 * mm,
            mask="auto",
            preserveAspectRatio=True,
        )
    c.setStrokeColor(LINE)
    c.line(sig_x, sig_y + 8 * mm, sig_x + 58 * mm, sig_y + 8 * mm)
    c.setFillColor(black)
    c.setFont(FONT_BOLD, 10)
    c.drawString(sig_x, sig_y + 3.2 * mm, Config.PGU_SIGNATORY)
    c.setFont(FONT, 7)
    c.setFillColor(MUTED)
    c.drawString(sig_x, sig_y - 1 * mm, Config.PGU_TITLE)

    c.setFillColor(NAVY)
    c.rect(0, 0, width, 8 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FONT, 6.5)
    c.drawString(margin, 3 * mm, "Confidential  ·  For the billed entity only  ·  Page 1 of 1")
    c.drawRightString(width - margin, 3 * mm, invoice.invoice_no)

    c.showPage()
    c.save()
    output_path.write_bytes(buf.getvalue())
    return output_path


def _wrap(text: str, width: int):
    text = (text or "").replace("\n", " ").strip()
    if not text:
        return [""]
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]

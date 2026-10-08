"""Invoice email sender via Gmail SMTP. Falls back to local outbox copies."""

from datetime import date, datetime
from base64 import b64encode
from html import escape
from io import BytesIO
from pathlib import Path
import logging
import re

from PIL import Image

from config import Config, OUTBOX_DIR, POSCO_CI_PATH
from smtp_mail import SmtpMailError, sanitize_mail_error, send_smtp_mail, smtp_configured

log = logging.getLogger("pgu.mail")

MAIL_KINDS = ("issue", "remind", "resend", "hq")

DEFAULT_MAIL_TEMPLATES = {
    "issue": {
        "subject": "POSCO Group University Invoice {invoice_no}",
        "headline": "Education Service Invoice",
        "body": (
            "Dear Sir/Madam,\n\n"
            "Greetings from POSCO Group University.\n\n"
            "Please review the attached invoice for the training programs listed below.\n\n"
            "Action required\n"
            "1. Review the company information and participant details.\n"
            "2. If corrections are needed, reply to this email.\n"
            "3. If everything is correct, click Confirm on the portal.\n\n"
            "Please quote the Reference No. on your wire transfer.\n\n"
            "Thank you for your cooperation.\n\n"
            "Best regards,\n"
            "POSCO Group University"
        ),
    },
    "remind": {
        "subject": "[Reminder] POSCO Group University Invoice {invoice_no}",
        "headline": "Invoice Review & Payment Reminder",
        "body": (
            "Dear Sir/Madam,\n\n"
            "Greetings from POSCO Group University.\n\n"
            "Please review the attached invoice for the training programs listed below.\n\n"
            "Action required\n"
            "1. Review the company information and participant details.\n"
            "2. If corrections are needed, reply to this email.\n"
            "3. If everything is correct, click Confirm on the portal.\n\n"
            "Please quote the Reference No. on your wire transfer.\n\n"
            "Thank you for your cooperation.\n\n"
            "Best regards,\n"
            "POSCO Group University"
        ),
    },
    "resend": {
        "subject": "[Updated] POSCO Group University Invoice {invoice_no}",
        "headline": "Updated Invoice",
        "body": (
            "Dear Sir/Madam,\n\n"
            "Greetings from POSCO Group University.\n\n"
            "Please find attached the updated official invoice. Please use this version "
            "in place of any previous copy.\n\n"
            "Action required\n"
            "1. Review the company information and participant details.\n"
            "2. If corrections are needed, reply to this email.\n"
            "3. If everything is correct, click Confirm on the portal.\n\n"
            "Please quote the Reference No. on your wire transfer.\n\n"
            "Thank you for your cooperation.\n\n"
            "Best regards,\n"
            "POSCO Group University"
        ),
    },
    "hq": {
        "subject": "[HQ Copy] POSCO Group University Invoice {invoice_no}",
        "headline": "HQ Copy — Issued Invoice",
        "body": (
            "Dear PGU Coordinator,\n\n"
            "This is a copy of an issued invoice for PGU internal records.\n\n"
            "Please keep this copy for PGU internal records.\n\n"
            "Best regards,\n"
            "POSCO Group University"
        ),
    },
}


def parse_emails(raw: str) -> list[str]:
    if not raw:
        return []
    parts = raw.replace("\n", ";").replace(",", ";").split(";")
    return [p.strip() for p in parts if p.strip() and "@" in p]


def hq_copy_emails() -> list[str]:
    return parse_emails(getattr(Config, "HQ_COPY_EMAIL", "") or "")


_URL_RE = re.compile(r"(https?://[^\s<>]+)")


def portal_url() -> str:
    return (getattr(Config, "PORTAL_URL", "") or "https://invoice2-icp0.onrender.com").strip()


def mail_placeholder_help() -> str:
    return "{invoice_no} {entity} {entity_code} {education} {period} {qty} {amount} {currency} {amount_krw} {portal_url}"


def invoice_mail_context(invoice) -> dict[str, str]:
    period = ""
    if getattr(invoice, "period_start", None) and getattr(invoice, "period_end", None):
        period = f"{invoice.period_start.strftime('%Y-%m-%d')} ~ {invoice.period_end.strftime('%Y-%m-%d')}"
    amount_fx = float(getattr(invoice, "amount_fx", 0) or 0)
    amount_krw = int(getattr(invoice, "amount_krw", 0) or 0)
    billed_name = (getattr(invoice, "billed_name", None) or "").strip()
    billed_code = (getattr(invoice, "billed_code", None) or "").strip()
    return {
        "invoice_no": getattr(invoice, "invoice_no", "") or "",
        "entity": billed_name or getattr(getattr(invoice, "subsidiary", None), "name_en", "") or "",
        "entity_code": billed_code or getattr(getattr(invoice, "subsidiary", None), "code", "") or "",
        "education": getattr(invoice, "education_name", "") or "",
        "period": period,
        "qty": str(getattr(invoice, "qty", "") or ""),
        "amount": f"{amount_fx:,.2f}",
        "currency": getattr(invoice, "currency", "") or "",
        "amount_krw": f"{amount_krw:,}",
        "portal_url": portal_url(),
    }


def apply_mail_placeholders(text: str, invoice=None) -> str:
    raw = text or ""
    raw = raw.replace("{portal_url}", portal_url())
    if invoice is None:
        return raw
    ctx = invoice_mail_context(invoice)
    for key, value in ctx.items():
        raw = raw.replace("{" + key + "}", value)
    return raw


def get_mail_template(kind: str) -> dict[str, str]:
    key = kind if kind in DEFAULT_MAIL_TEMPLATES else "issue"
    base = dict(DEFAULT_MAIL_TEMPLATES[key])
    prefix = f"MAIL_TPL_{key.upper()}"
    subject = (getattr(Config, f"{prefix}_SUBJECT", "") or "").strip()
    body = (getattr(Config, f"{prefix}_BODY", "") or "").replace("\r\n", "\n").strip()
    if subject:
        base["subject"] = subject
    if body:
        base["body"] = body
    return base


def draft_mail_content(kind: str, invoice=None, fill: bool = True) -> dict[str, str]:
    tpl = get_mail_template(kind)
    subject = tpl["subject"]
    body = tpl["body"]
    if fill and invoice is not None:
        subject = apply_mail_placeholders(subject, invoice)
        body = apply_mail_placeholders(body, invoice)
    return {
        "kind": kind if kind in DEFAULT_MAIL_TEMPLATES else "issue",
        "subject": subject,
        "body": body,
        "headline": tpl["headline"],
    }


_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}\b"
)
_ITEM_RE = re.compile(r"^\d+\.\s+")


def _header_logo_html() -> str:
    if not POSCO_CI_PATH.exists():
        return (
            '<div style="font-size:13px;letter-spacing:1px;font-weight:700;color:#ffffff;">'
            "POSCO GROUP UNIVERSITY</div>"
        )
    img = Image.open(POSCO_CI_PATH).convert("RGBA")
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    img.thumbnail((200, 36), resample)
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = b64encode(buf.getvalue()).decode("ascii")
    width, height = img.size
    return (
        f'<img src="data:image/png;base64,{b64}" alt="POSCO Group University" width="{width}" '
        f'height="{height}" style="display:block;width:{width}px;height:{height}px;border:0;">'
    )


def _english_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%B %d, %Y").replace(" 0", " ")


def invoice_payment_deadline(invoice) -> str:
    try:
        year = int(getattr(invoice, "year", 0) or 0)
        half = int(getattr(invoice, "half", 0) or 0)
    except (TypeError, ValueError):
        year = 0
        half = 0
    if year < 2000:
        end = getattr(invoice, "period_end", None)
        return _english_date(end)
    deadline = date(year, 6, 30) if half == 1 else date(year, 12, 31)
    return _english_date(deadline)


def invoice_half_label(invoice) -> str:
    try:
        half = int(getattr(invoice, "half", 0) or 0)
    except (TypeError, ValueError):
        half = 0
    if half == 1:
        return "First Half"
    if half == 2:
        return "Second Half"
    return ""


def invoice_header_subtitle(invoice) -> str:
    year = getattr(invoice, "year", "") or ""
    half_label = invoice_half_label(invoice)
    lead = " ".join(str(part) for part in (year, half_label) if part)
    if lead:
        return f"{lead} \u00b7 Global Training Programs"
    return "Global Training Programs"


def format_mail_period(start, end) -> str:
    if not start or not end:
        return ""
    if start.year == end.year and start.month == end.month:
        return f"{start.strftime('%b')} {start.day}-{end.day}"
    if start.year == end.year:
        return f"{start.strftime('%b')} {start.day} - {end.strftime('%b')} {end.day}"
    return f"{start.strftime('%b')} {start.day}, {start.year} - {end.strftime('%b')} {end.day}, {end.year}"


def linkify_text(text: str) -> str:
    raw = text or ""
    parts = []
    last = 0
    for match in _URL_RE.finditer(raw):
        parts.append(escape(raw[last:match.start()]))
        url = match.group(1).rstrip(").,;]")
        parts.append(
            f'<a href="{escape(url, quote=True)}" style="color:#002060;font-weight:700;text-decoration:underline;" '
            f'target="_blank" rel="noopener">{escape(url)}</a>'
        )
        last = match.end()
    parts.append(escape(raw[last:]))
    marked = "".join(parts)
    return _DATE_RE.sub(
        lambda m: f'<strong style="color:#002060;">{m.group(0)}</strong>',
        marked,
    )


def text_to_html_blocks(text: str) -> str:
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return ""
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    html = []
    for block in blocks:
        lines = [ln.rstrip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        numbered = [ln for ln in lines if _ITEM_RE.match(ln)]
        title = lines[0] if lines and not _ITEM_RE.match(lines[0]) else ""
        is_action = bool(numbered) or title.lower().startswith("action required")
        if is_action and (numbered or len(lines) > 1):
            items = numbered or lines[1:]
            title_html = (
                f'<div style="font-size:13px;font-weight:700;color:#002060;margin:0 0 8px;letter-spacing:0.02em;">'
                f"{linkify_text(title)}</div>"
                if title
                else ""
            )
            item_html = "".join(
                f'<tr><td valign="top" style="width:22px;padding:0 0 6px;font-size:14px;line-height:1.5;color:#1b2a4e;">{escape(item.split(".", 1)[0] + ".")}</td>'
                f'<td valign="top" style="padding:0 0 6px;font-size:14px;line-height:1.5;color:#1b2a4e;">{linkify_text(item.split(".", 1)[-1].strip())}</td></tr>'
                if _ITEM_RE.match(item)
                else f'<tr><td colspan="2" style="padding:0 0 6px;font-size:14px;line-height:1.5;color:#1b2a4e;">{linkify_text(item)}</td></tr>'
                for item in items
            )
            html.append(
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                'style="margin:16px 0;background:#F4F6F8;border:1px solid #E4E8EE;">'
                f'<tr><td style="padding:14px 16px;">{title_html}'
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{item_html}</table>'
                "</td></tr></table>"
            )
            continue
        html.append(
            f'<p style="margin:0 0 12px;font-size:14px;line-height:1.6;color:#1b2a4e;">{linkify_text(block).replace(chr(10), "<br>")}</p>'
        )
    return "".join(html)


def wrap_invoice_html(invoice, headline: str, body_text: str) -> str:
    period = f"{invoice.period_start.strftime('%Y-%m-%d')} ~ {invoice.period_end.strftime('%Y-%m-%d')}"
    items = list(invoice.items or [])
    program_rows = []
    for it in items:
        start = it.period_start or invoice.period_start
        end = it.period_end or invoice.period_end
        program_rows.append(
            "<tr>"
            f'<td style="padding:10px 12px;border-bottom:1px solid #E4E8EE;font-size:13px;line-height:1.45;color:#1b2a4e;word-break:break-word;">{escape(str(it.description))}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #E4E8EE;font-size:13px;line-height:1.45;color:#1b2a4e;white-space:nowrap;">{escape(format_mail_period(start, end))}</td>'
            f'<td align="right" style="padding:10px 12px;border-bottom:1px solid #E4E8EE;font-size:13px;line-height:1.45;color:#1b2a4e;">{it.qty}</td>'
            "</tr>"
        )
    if not program_rows:
        program_rows.append(
            "<tr>"
            f'<td style="padding:10px 12px;border-bottom:1px solid #E4E8EE;font-size:13px;line-height:1.45;color:#1b2a4e;word-break:break-word;">{escape(str(invoice.education_name))}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #E4E8EE;font-size:13px;line-height:1.45;color:#1b2a4e;white-space:nowrap;">{escape(format_mail_period(invoice.period_start, invoice.period_end) or period)}</td>'
            f'<td align="right" style="padding:10px 12px;border-bottom:1px solid #E4E8EE;font-size:13px;line-height:1.45;color:#1b2a4e;">{invoice.qty}</td>'
            "</tr>"
        )
    program_html = "".join(program_rows)
    logo = _header_logo_html()
    body_html = text_to_html_blocks(body_text)
    portal = portal_url()
    portal_href = escape(portal, quote=True)
    subtitle = invoice_header_subtitle(invoice)
    amount = f"{escape(str(invoice.currency))} {float(invoice.amount_fx):,.2f}"
    pay_deadline = invoice_payment_deadline(invoice)
    try:
        vat_rate = float(getattr(invoice, "vat_rate", 0) or 0)
    except (TypeError, ValueError):
        vat_rate = 0.0
    vat_label = "VAT Exempt (0%)" if vat_rate == 0 else f"VAT {vat_rate:g}%"
    navy = "#002060"
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0;padding:0;background:#F4F6F8;">
  <tr>
    <td align="center" style="padding:16px 8px;">
      <table role="presentation" width="650" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:650px;background:#ffffff;">
        <tr>
          <td style="background:{navy};padding:18px 24px 16px;">
            {logo}
            <div style="margin:10px 0 0;font-family:Calibri,'Segoe UI',Arial,sans-serif;font-size:18px;line-height:1.3;font-weight:700;color:#ffffff;">{escape(headline or "")}</div>
            <div style="margin:4px 0 0;font-family:Calibri,'Segoe UI',Arial,sans-serif;font-size:12px;line-height:1.4;color:#D6DEE8;">{escape(subtitle)}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 24px 8px;font-family:Calibri,'Segoe UI',Arial,sans-serif;color:#1b2a4e;text-align:left;">
            {body_html}
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:8px 24px 20px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td align="center" bgcolor="{navy}" style="background:{navy};border-radius:6px;">
                  <a href="{portal_href}" target="_blank" rel="noopener" style="display:inline-block;padding:12px 28px;font-family:Calibri,'Segoe UI',Arial,sans-serif;font-size:14px;line-height:1.2;font-weight:700;color:#ffffff;text-decoration:none;">Open PGU Invoice Portal</a>
                </td>
              </tr>
            </table>
            <div style="margin:10px 0 0;font-family:Calibri,'Segoe UI',Arial,sans-serif;font-size:12px;line-height:1.4;color:#5B6770;">
              <a href="{portal_href}" target="_blank" rel="noopener" style="color:#5B6770;text-decoration:underline;">{escape(portal)}</a>
            </div>
          </td>
        </tr>
        <tr>
          <td style="padding:0 24px 8px;font-family:Calibri,'Segoe UI',Arial,sans-serif;">
            <div style="font-size:14px;line-height:1.4;font-weight:700;color:{navy};margin:0 0 10px;">Invoice Summary</div>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 14px;">
              <tr>
                <td width="38%" style="padding:6px 0;font-size:13px;line-height:1.45;color:#5B6770;">Reference No.</td>
                <td style="padding:6px 0;font-size:13px;line-height:1.45;color:#1b2a4e;font-weight:700;">{escape(str(invoice.invoice_no))}</td>
              </tr>
              <tr>
                <td style="padding:6px 0;font-size:13px;line-height:1.45;color:#5B6770;">Billed Entity</td>
                <td style="padding:6px 0;font-size:13px;line-height:1.45;color:#1b2a4e;">{escape(str((getattr(invoice, "billed_name", None) or "").strip() or invoice.subsidiary.name_en))}</td>
              </tr>
            </table>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #E4E8EE;">
              <tr>
                <th align="left" width="50%" style="background:#F4F6F8;padding:9px 12px;font-size:12px;line-height:1.3;color:#5B6770;font-weight:700;">Program</th>
                <th align="left" width="35%" style="background:#F4F6F8;padding:9px 12px;font-size:12px;line-height:1.3;color:#5B6770;font-weight:700;">Period</th>
                <th align="right" width="15%" style="background:#F4F6F8;padding:9px 12px;font-size:12px;line-height:1.3;color:#5B6770;font-weight:700;">Qty</th>
              </tr>
              {program_html}
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 24px 8px;font-family:Calibri,'Segoe UI',Arial,sans-serif;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F4F6F8;border:1px solid #E4E8EE;">
              <tr>
                <td style="padding:16px 18px;">
                  <div style="font-size:12px;line-height:1.3;color:#5B6770;font-weight:700;letter-spacing:0.03em;">Net Aggregate Due</div>
                  <div style="margin:6px 0 10px;font-size:26px;line-height:1.2;font-weight:700;color:{navy};">{amount}</div>
                  <div style="font-size:13px;line-height:1.5;color:#1b2a4e;">{escape(vat_label)}</div>
                  {f'<div style="margin-top:4px;font-size:13px;line-height:1.5;color:#1b2a4e;">Payment Deadline: <strong>{escape(pay_deadline)}</strong></div>' if pay_deadline else ""}
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 24px 20px;font-family:Calibri,'Segoe UI',Arial,sans-serif;">
            <div style="font-size:14px;line-height:1.4;font-weight:700;color:{navy};margin:0 0 8px;">Payment Information</div>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td width="38%" style="padding:4px 0;font-size:13px;line-height:1.45;color:#5B6770;">Bank</td>
                <td style="padding:4px 0;font-size:13px;line-height:1.45;color:#1b2a4e;">{escape(str(Config.BANK_NAME))}{', ' + escape(str(Config.BANK_BRANCH)) if Config.BANK_BRANCH else ''}</td>
              </tr>
              <tr>
                <td style="padding:4px 0;font-size:13px;line-height:1.45;color:#5B6770;">SWIFT Code</td>
                <td style="padding:4px 0;font-size:13px;line-height:1.45;color:#1b2a4e;">{escape(str(Config.BANK_SWIFT))}</td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:0 24px 24px;font-family:Calibri,'Segoe UI',Arial,sans-serif;font-size:11px;line-height:1.5;color:#8A93A0;">
            This message was generated by the PGU Education Invoice Portal.
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
"""


def send_invoice_email(
    invoice,
    pdf_path: Path,
    remind: bool = False,
    updated: bool = False,
    extra_recipients=None,
    hq_only: bool = False,
    kind: str | None = None,
    subject: str | None = None,
    body_text: str | None = None,
    to_recipients=None,
    cc_recipients=None,
) -> dict:
    hq_recipients = hq_copy_emails()
    extra = [e for e in (extra_recipients or []) if e]
    if to_recipients is not None or cc_recipients is not None:
        to_recipients = list(dict.fromkeys(to_recipients or []))
        cc_recipients = [e for e in dict.fromkeys(cc_recipients or []) if e not in to_recipients]
        if extra:
            for email in extra:
                if email not in to_recipients and email not in cc_recipients:
                    to_recipients.append(email)
    elif hq_only:
        to_recipients = list(dict.fromkeys(hq_recipients + extra))
        cc_recipients = []
    else:
        to_recipients = parse_emails(getattr(invoice.subsidiary, "emails", "") or "")
        for email in extra:
            if email not in to_recipients:
                to_recipients.append(email)
        hr = parse_emails(getattr(invoice.subsidiary, "hr_emails", "") or "")
        cc_recipients = [e for e in hr if e not in to_recipients]
    recipients = to_recipients + cc_recipients
    if not to_recipients:
        return {"ok": False, "error": "no_email", "recipients": [], "to": [], "cc": []}

    if kind not in DEFAULT_MAIL_TEMPLATES:
        if hq_only:
            kind = "hq"
        elif remind:
            kind = "remind"
        elif updated:
            kind = "resend"
        else:
            kind = "issue"
    draft = draft_mail_content(kind, invoice, fill=True)
    subject = apply_mail_placeholders((subject if subject is not None else draft["subject"]).strip(), invoice)
    body_text = apply_mail_placeholders(
        (body_text if body_text is not None else draft["body"]).replace("\r\n", "\n").strip(),
        invoice,
    )
    if not subject or not body_text:
        return {"ok": False, "error": "mail_body_required", "recipients": recipients, "to": to_recipients, "cc": cc_recipients}
    headline = draft["headline"]
    body_html = wrap_invoice_html(invoice, headline, body_text)

    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_hq" if hq_only else ""
    out_file = OUTBOX_DIR / f"{invoice.invoice_no}{suffix}_{stamp}.html"
    out_file.write_text(
        f"<!-- To: {', '.join(to_recipients)} -->\n<!-- Cc: {', '.join(cc_recipients)} -->\n<!-- Subject: {subject} -->\n{body_html}",
        encoding="utf-8",
    )
    pdf_file = Path(pdf_path) if pdf_path else None
    pdf_bytes = pdf_file.read_bytes() if pdf_file and pdf_file.exists() else b""
    if pdf_bytes:
        (OUTBOX_DIR / f"{invoice.invoice_no}{suffix}_{stamp}.pdf").write_bytes(pdf_bytes)

    return _deliver(
        subject=subject,
        html=body_html,
        to_recipients=to_recipients,
        cc_recipients=cc_recipients,
        pdf_bytes=pdf_bytes or None,
        pdf_name=f"{invoice.invoice_no}.pdf",
        out_file=out_file,
        recipients=recipients,
        plain=body_text,
    )


def send_test_email(to_addr: str) -> dict:
    to_recipients = parse_emails(to_addr)
    if not to_recipients:
        return {"ok": False, "error": "no_email", "recipients": [], "to": [], "cc": []}
    subject = "[Test] POSCO Group University Invoice Portal"
    body_html = """
    <div style="font-family:Calibri,'Segoe UI',Arial,sans-serif;color:#1b2a4e;line-height:1.5">
      <div style="background:#002060;color:#fff;padding:16px 20px">
        <div style="font-size:20px;font-weight:700">Gmail connection test</div>
      </div>
      <div style="padding:20px;background:#F0F4F8">
        <p>This is a test message from the PGU Education Invoice Portal.</p>
        <p>Gmail SMTP (STARTTLS) is configured and sending from the dedicated mailbox.</p>
        <p style="color:#5B6770;font-size:12px">This message was generated by the PGU Education Invoice Portal.</p>
      </div>
    </div>
    """
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = OUTBOX_DIR / f"gmail_test_{stamp}.html"
    out_file.write_text(
        f"<!-- To: {', '.join(to_recipients)} -->\n<!-- Subject: {subject} -->\n{body_html}",
        encoding="utf-8",
    )
    return _deliver(
        subject=subject,
        html=body_html,
        to_recipients=to_recipients,
        cc_recipients=[],
        pdf_bytes=None,
        pdf_name="invoice.pdf",
        out_file=out_file,
        recipients=to_recipients,
        plain="This is a test message from the PGU Education Invoice Portal.",
    )


def _deliver(
    *,
    subject: str,
    html: str,
    to_recipients: list[str],
    cc_recipients: list[str],
    pdf_bytes: bytes | None,
    pdf_name: str,
    out_file: Path,
    recipients: list[str],
    plain: str = "",
) -> dict:
    if not smtp_configured():
        log.error("Invoice email not sent: Gmail SMTP env vars are missing")
        return {
            "ok": False,
            "error": "smtp_not_configured",
            "recipients": recipients,
            "to": to_recipients,
            "cc": cc_recipients,
            "via": "outbox",
            "outbox": str(out_file),
        }

    try:
        send_smtp_mail(
            subject=subject,
            html=html,
            to_recipients=to_recipients,
            cc_recipients=cc_recipients,
            pdf_bytes=pdf_bytes,
            pdf_name=pdf_name,
            plain=plain,
        )
    except SmtpMailError as exc:
        return {
            "ok": False,
            "error": sanitize_mail_error(exc.safe_message),
            "recipients": recipients,
            "to": to_recipients,
            "cc": cc_recipients,
            "via": "outbox",
            "outbox": str(out_file),
        }
    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected mail send error: %s", sanitize_mail_error(str(exc)))
        return {
            "ok": False,
            "error": "Gmail SMTP send failed",
            "recipients": recipients,
            "to": to_recipients,
            "cc": cc_recipients,
            "via": "outbox",
            "outbox": str(out_file),
        }

    return {
        "ok": True,
        "recipients": recipients,
        "to": to_recipients,
        "cc": cc_recipients,
        "via": "smtp",
        "outbox": str(out_file),
        "error": None,
    }

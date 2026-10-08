"""Gmail SMTP send via App Password. Password is read only from env."""

from __future__ import annotations

import logging
import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from config import Config

log = logging.getLogger("pgu.mail")

_SECRET_RE = re.compile(r"(?i)(password|passwd|pwd|secret)[=:]\s*\S+")


class SmtpMailError(Exception):
    def __init__(self, safe_message: str):
        super().__init__(safe_message)
        self.safe_message = safe_message


def sanitize_mail_error(text: str) -> str:
    raw = str(text or "")
    secret = smtp_password()
    if secret:
        raw = raw.replace(secret, "[redacted]")
    raw = _SECRET_RE.sub(r"\1=[redacted]", raw)
    return raw[:500]


def smtp_password() -> str:
    return re.sub(r"\s+", "", getattr(Config, "MAIL_PASSWORD", "") or "")


def smtp_configured() -> bool:
    return bool(
        (getattr(Config, "MAIL_SERVER", "") or "").strip()
        and int(getattr(Config, "MAIL_PORT", 0) or 0)
        and (getattr(Config, "MAIL_USERNAME", "") or "").strip()
        and smtp_password()
        and (getattr(Config, "MAIL_FROM", "") or "").strip()
    )


def send_smtp_mail(
    *,
    subject: str,
    html: str,
    to_recipients: list[str],
    cc_recipients: list[str] | None = None,
    pdf_bytes: bytes | None = None,
    pdf_name: str = "invoice.pdf",
    plain: str = "",
) -> None:
    if not smtp_configured():
        raise SmtpMailError("smtp_not_configured")
    to_list = [a.strip() for a in (to_recipients or []) if a and "@" in a]
    if not to_list:
        raise SmtpMailError("no_email")
    cc_list = [a.strip() for a in (cc_recipients or []) if a and "@" in a and a not in to_list]

    sender = (Config.MAIL_FROM or "").strip()
    display = (getattr(Config, "MAIL_FROM_NAME", "") or "").strip()
    msg = EmailMessage()
    msg["From"] = formataddr((display, sender)) if display else sender
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject
    msg.set_content(plain or "Please view this message in HTML.")
    msg.add_alternative(html, subtype="html")
    if pdf_bytes:
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=pdf_name,
        )

    host = (Config.MAIL_SERVER or "").strip()
    port = int(Config.MAIL_PORT or 587)
    user = (Config.MAIL_USERNAME or "").strip()
    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(user, smtp_password())
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        log.error("Gmail SMTP login failed")
        raise SmtpMailError("smtp_auth_failed") from None
    except smtplib.SMTPException as exc:
        log.error("Gmail SMTP send failed: %s", sanitize_mail_error(str(exc)))
        raise SmtpMailError(f"Gmail SMTP send failed ({exc.__class__.__name__})") from None
    except OSError as exc:
        log.error("Gmail SMTP connection failed: %s", sanitize_mail_error(str(exc)))
        raise SmtpMailError("Gmail SMTP connection failed") from None
    log.info("Gmail SMTP accepted: to_count=%s", len(to_list))

"""Gmail SMTP send via App Password. Password is read only from env."""

from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from config import BASE_DIR, Config
from dotenv import load_dotenv

log = logging.getLogger("pgu.mail")

_SECRET_RE = re.compile(r"(?i)(password|passwd|pwd|secret)[=:]\s*\S+")
_MAIL_DICT_KEYS = {
    "MAIL_PORT": ("MAIL_PORT", "port", "PORT", "smtp_port"),
    "MAIL_SERVER": ("MAIL_SERVER", "server", "host", "HOST", "smtp_server"),
    "MAIL_USERNAME": ("MAIL_USERNAME", "username", "user", "USER"),
    "MAIL_PASSWORD": ("MAIL_PASSWORD", "password", "PASSWORD"),
    "MAIL_FROM": ("MAIL_FROM", "from", "sender", "email"),
    "MAIL_FROM_NAME": ("MAIL_FROM_NAME", "from_name", "name", "display"),
}


class SmtpMailError(Exception):
    def __init__(self, safe_message: str):
        super().__init__(safe_message)
        self.safe_message = safe_message


def refresh_mail_env() -> None:
    load_dotenv(BASE_DIR / ".env", override=True)


def _mail_scalar(value) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else ""
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    if isinstance(value, str):
        return value.strip()
    return ""


def _mail_from_mapping(name: str, value: dict) -> str:
    for key in _MAIL_DICT_KEYS.get(name, (name,)):
        if key not in value:
            continue
        inner = value[key]
        if isinstance(inner, dict):
            continue
        text = _mail_scalar(inner)
        if text:
            return text
    return ""


def _coerce_mail_value(name: str, value) -> str:
    if isinstance(value, dict):
        return _mail_from_mapping(name, value)
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _coerce_mail_value(name, item)
            if text:
                return text
        return ""
    return _mail_scalar(value)


def _mail_val(name: str, default: str = "") -> str:
    text = _coerce_mail_value(name, os.environ.get(name))
    if text:
        return text
    refresh_mail_env()
    text = _coerce_mail_value(name, os.environ.get(name))
    if text:
        return text
    text = _coerce_mail_value(name, getattr(Config, name, None))
    if text:
        return text
    return _coerce_mail_value(name, default)


def mail_from_address() -> str:
    return _mail_val("MAIL_FROM") or "mileg8744@gmail.com"


def sanitize_mail_error(text: str) -> str:
    raw = str(text or "")
    secret = smtp_password()
    if secret:
        raw = raw.replace(secret, "[redacted]")
    raw = _SECRET_RE.sub(r"\1=[redacted]", raw)
    return raw[:500]


def smtp_password() -> str:
    return re.sub(r"\s+", "", _mail_val("MAIL_PASSWORD"))


def smtp_configured() -> bool:
    try:
        try:
            port = int(_mail_val("MAIL_PORT") or "0")
        except (TypeError, ValueError):
            port = 0
        if port <= 0:
            return False
        return bool(
            _mail_val("MAIL_SERVER")
            and _mail_val("MAIL_USERNAME")
            and smtp_password()
            and _mail_val("MAIL_FROM")
        )
    except Exception:
        log.warning("smtp_configured check failed; treating mail as not live")
        return False


def _build_message(
    *,
    subject: str,
    html: str,
    to_list: list[str],
    cc_list: list[str],
    sender: str,
    display: str,
    pdf_bytes: bytes | None,
    pdf_name: str,
    plain: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((display, sender)) if display else sender
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1] if "@" in sender else "localhost")
    msg.set_content(plain or "Please view this message in HTML.")
    msg.add_alternative(html, subtype="html")
    if pdf_bytes:
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=pdf_name or "invoice.pdf",
        )
    return msg


def _try_send(msg: EmailMessage, host: str, user: str, password: str, sender: str, recipients: list[str]) -> None:
    ctx = ssl.create_default_context()
    last_error = None

    try:
        with smtplib.SMTP(host, 587, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
            smtp.login(user, password)
            smtp.sendmail(sender, recipients, msg.as_bytes())
        log.info("Gmail SMTP accepted via 587 STARTTLS: to_count=%s", len(recipients))
        return
    except smtplib.SMTPAuthenticationError:
        raise
    except smtplib.SMTPRecipientsRefused as exc:
        log.error("Gmail rejected recipients: %s", sanitize_mail_error(str(exc)))
        raise SmtpMailError("smtp_recipient_refused") from None
    except (smtplib.SMTPException, OSError) as exc:
        last_error = exc
        log.warning("Gmail SMTP 587 failed: %s", sanitize_mail_error(str(exc)))

    try:
        with smtplib.SMTP_SSL(host, 465, timeout=30, context=ctx) as smtp:
            smtp.ehlo()
            smtp.login(user, password)
            smtp.sendmail(sender, recipients, msg.as_bytes())
        log.info("Gmail SMTP accepted via 465 SSL: to_count=%s", len(recipients))
        return
    except smtplib.SMTPAuthenticationError:
        raise
    except smtplib.SMTPRecipientsRefused:
        raise SmtpMailError("smtp_recipient_refused") from None
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("Gmail SMTP 465 failed: %s", sanitize_mail_error(str(exc)))
        detail = sanitize_mail_error(str(last_error or exc))
        raise SmtpMailError(detail or "Gmail SMTP connection failed") from None


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

    sender = _mail_val("MAIL_FROM")
    user = _mail_val("MAIL_USERNAME")
    display = _mail_val("MAIL_FROM_NAME")
    host = _mail_val("MAIL_SERVER") or "smtp.gmail.com"
    msg = _build_message(
        subject=subject,
        html=html,
        to_list=to_list,
        cc_list=cc_list,
        sender=sender,
        display=display,
        pdf_bytes=pdf_bytes,
        pdf_name=pdf_name,
        plain=plain,
    )
    envelope_from = user or sender
    recipients = to_list + cc_list

    try:
        _try_send(msg, host, user, smtp_password(), envelope_from, recipients)
    except smtplib.SMTPAuthenticationError:
        log.error("Gmail SMTP login failed")
        raise SmtpMailError("smtp_auth_failed") from None
    except SmtpMailError:
        raise
    except smtplib.SMTPException as exc:
        log.error("Gmail SMTP send failed: %s", sanitize_mail_error(str(exc)))
        raise SmtpMailError(f"Gmail SMTP send failed ({exc.__class__.__name__})") from None
    except OSError:
        log.error("Gmail SMTP connection failed")
        raise SmtpMailError("Gmail SMTP connection failed") from None

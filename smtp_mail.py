"""Gmail SMTP send via App Password. Password is read only from env."""

from __future__ import annotations

import logging
import os
import re
import socket
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
    "MAIL_USE_TLS": ("MAIL_USE_TLS", "use_tls", "tls", "STARTTLS"),
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


def _on_render() -> bool:
    return (os.environ.get("RENDER") or "").strip().lower() in {"1", "true", "yes"}


def _smtp_timeout() -> int:
    return 8 if _on_render() else 90


def mail_use_tls() -> bool:
    raw = _mail_val("MAIL_USE_TLS").lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def _classify_os_error(exc: BaseException) -> str:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "smtp_timeout"
    if isinstance(exc, ConnectionRefusedError):
        return "smtp_port_blocked"
    text = str(exc).lower()
    if "timed out" in text or "timeout" in text:
        return "smtp_timeout"
    errno = getattr(exc, "errno", None)
    if errno in {101, 110, 111, 113, 10060, 10061}:
        return "smtp_port_blocked"
    if "connection refused" in text or "network is unreachable" in text:
        return "smtp_port_blocked"
    return "smtp_connect_failed"


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


def _attachment_types(filename: str) -> tuple[str, str]:
    name = (filename or "").lower()
    if name.endswith(".pptx"):
        return "application", "vnd.openxmlformats-officedocument.presentationml.presentation"
    if name.endswith(".pdf"):
        return "application", "pdf"
    return "application", "octet-stream"


def _add_file_attachment(msg: EmailMessage, data: bytes | None, filename: str) -> None:
    if not data:
        return
    maintype, subtype = _attachment_types(filename)
    msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename or "file.bin")


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
    extra_attachments=None,
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
    _add_file_attachment(msg, pdf_bytes, pdf_name or "invoice.pdf")
    for item in extra_attachments or []:
        if not item:
            continue
        data, name = item
        _add_file_attachment(msg, data, name)
    return msg


def _try_send(msg: EmailMessage, host: str, user: str, password: str, sender: str, recipients: list[str]) -> None:
    ctx = ssl.create_default_context()
    timeout = _smtp_timeout()
    last_code = "smtp_connect_failed"
    render = _on_render()

    def note_connect(port: int, exc: BaseException) -> None:
        nonlocal last_code
        last_code = _classify_os_error(exc)
        log.warning(
            "SMTP connect failed host=%s port=%s timeout=%ss render=%s class=%s code=%s detail=%s",
            host,
            port,
            timeout,
            render,
            exc.__class__.__name__,
            last_code,
            sanitize_mail_error(str(exc)),
        )
        if render and last_code in {"smtp_timeout", "smtp_port_blocked", "smtp_connect_failed"}:
            log.warning(
                "Render free web services often block outbound SMTP ports 25/465/587; this is a network restriction, not an App Password parse error"
            )

    if mail_use_tls():
        try:
            with smtplib.SMTP(host, 587, timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
                smtp.login(user, password)
                smtp.sendmail(sender, recipients, msg.as_bytes())
            log.info("Gmail SMTP accepted via 587 STARTTLS: to_count=%s", len(recipients))
            return
        except smtplib.SMTPAuthenticationError:
            log.error("Gmail SMTP authentication failed via 587 STARTTLS")
            raise
        except smtplib.SMTPRecipientsRefused as exc:
            log.error("Gmail rejected recipients via 587: %s", sanitize_mail_error(str(exc)))
            raise SmtpMailError("smtp_recipient_refused") from None
        except smtplib.SMTPDataError:
            raise
        except (smtplib.SMTPException, OSError) as exc:
            note_connect(587, exc)

    try:
        with smtplib.SMTP_SSL(host, 465, timeout=timeout, context=ctx) as smtp:
            smtp.ehlo()
            smtp.login(user, password)
            smtp.sendmail(sender, recipients, msg.as_bytes())
        log.info("Gmail SMTP accepted via 465 SSL: to_count=%s", len(recipients))
        return
    except smtplib.SMTPAuthenticationError:
        log.error("Gmail SMTP authentication failed via 465 SSL")
        raise
    except smtplib.SMTPRecipientsRefused:
        raise SmtpMailError("smtp_recipient_refused") from None
    except smtplib.SMTPDataError:
        raise
    except (smtplib.SMTPException, OSError) as exc:
        note_connect(465, exc)
        raise SmtpMailError(last_code) from None


def send_smtp_mail(
    *,
    subject: str,
    html: str,
    to_recipients: list[str],
    cc_recipients: list[str] | None = None,
    pdf_bytes: bytes | None = None,
    pdf_name: str = "invoice.pdf",
    plain: str = "",
    extra_attachments=None,
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
        extra_attachments=extra_attachments,
    )
    envelope_from = user or sender
    recipients = to_list + cc_list

    try:
        log.info(
            "SMTP send start host=%s from_set=%s user_set=%s to_count=%s render=%s",
            host,
            bool(sender),
            bool(user),
            len(recipients),
            _on_render(),
        )
        _try_send(msg, host, user, smtp_password(), envelope_from, recipients)
    except smtplib.SMTPAuthenticationError:
        log.error("Gmail SMTP login failed (App Password or 2-Step Verification)")
        raise SmtpMailError("smtp_auth_failed") from None
    except SmtpMailError:
        raise
    except smtplib.SMTPDataError as exc:
        text = str(exc).lower()
        if getattr(exc, "smtp_code", 0) in {552, 552} or "size" in text or "limit" in text:
            log.error("Gmail rejected the message as too large")
            raise SmtpMailError("smtp_too_large") from None
        log.error("Gmail SMTP send failed: %s", sanitize_mail_error(str(exc)))
        raise SmtpMailError("smtp_send_failed") from None
    except smtplib.SMTPException as exc:
        log.error("Gmail SMTP send failed: %s", sanitize_mail_error(str(exc)))
        raise SmtpMailError("smtp_send_failed") from None
    except OSError as exc:
        code = _classify_os_error(exc)
        log.error("Gmail SMTP connection failed code=%s", code)
        raise SmtpMailError(code) from None

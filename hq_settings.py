"""Persisted HQ profile that overrides Config defaults at runtime."""

from __future__ import annotations

import json

from config import Config, INSTANCE_DIR

HQ_SETTINGS_PATH = INSTANCE_DIR / "hq_settings.json"

HQ_FIELDS = (
    "HQ_COPY_EMAIL",
    "GOOGLE_MAPS_API_KEY",
    "PGU_NAME",
    "PGU_DEPT",
    "PGU_ADDRESS",
    "PGU_PHONE",
    "PGU_SIGNATORY",
    "PGU_TITLE",
    "BANK_NAME",
    "BANK_BRANCH",
    "BANK_ACCOUNT_NAME",
    "BANK_ACCOUNT_NO",
    "BANK_SWIFT",
    "MAIL_TPL_ISSUE_SUBJECT",
    "MAIL_TPL_ISSUE_BODY",
    "MAIL_TPL_REMIND_SUBJECT",
    "MAIL_TPL_REMIND_BODY",
    "MAIL_TPL_RESEND_SUBJECT",
    "MAIL_TPL_RESEND_BODY",
    "MAIL_TPL_HQ_SUBJECT",
    "MAIL_TPL_HQ_BODY",
)

BOOL_KEYS = set()
INT_KEYS = set()


def _factory_value(key):
    if key.startswith("MAIL_TPL_"):
        from mailer import DEFAULT_MAIL_TEMPLATES

        rest = key[len("MAIL_TPL_") :]
        kind, _, field = rest.partition("_")
        return DEFAULT_MAIL_TEMPLATES.get(kind.lower(), {}).get(field.lower(), "")
    val = getattr(Config, key, "")
    if key in BOOL_KEYS:
        return bool(val)
    if key in INT_KEYS:
        try:
            return int(val or 587)
        except (TypeError, ValueError):
            return 587
    return val or ""


FACTORY_DEFAULTS = {key: _factory_value(key) for key in HQ_FIELDS}


def default_hq_settings() -> dict:
    return dict(FACTORY_DEFAULTS)


def load_hq_settings() -> dict:
    data = default_hq_settings()
    if HQ_SETTINGS_PATH.exists():
        try:
            saved = json.loads(HQ_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                for key in HQ_FIELDS:
                    if key in saved and saved[key] is not None:
                        data[key] = saved[key]
        except (OSError, json.JSONDecodeError):
            pass
    apply_hq_settings(data)
    return data


def coerce_setting(key, val):
    if key in BOOL_KEYS:
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in {"1", "true", "yes", "on"}
    if key in INT_KEYS:
        try:
            return int(val)
        except (TypeError, ValueError):
            return 587
    return str(val if val is not None else "").strip()


def apply_hq_settings(data: dict) -> None:
    for key in HQ_FIELDS:
        if key in data:
            setattr(Config, key, coerce_setting(key, data[key]))


def save_hq_settings(data: dict) -> dict:
    payload = default_hq_settings()
    for key in HQ_FIELDS:
        if key in data and data[key] is not None:
            payload[key] = coerce_setting(key, data[key])
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    HQ_SETTINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    apply_hq_settings(payload)
    return payload

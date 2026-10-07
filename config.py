import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = BASE_DIR / "uploads"
PDF_DIR = BASE_DIR / "generated_pdfs"
OUTBOX_DIR = BASE_DIR / "outbox"
STATIC_DIR = BASE_DIR / "static"
STAMP_PATH = INSTANCE_DIR / "pgu_stamp.png"
POSCO_CI_PATH = STATIC_DIR / "img" / "posco_ci_white.png"


def resolve_database_uri() -> str:
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    if not raw:
        return f"sqlite:///{(INSTANCE_DIR / 'pgu_invoices.db').as_posix()}"
    if raw.startswith("postgres://"):
        raw = "postgresql+psycopg2://" + raw[len("postgres://") :]
    elif raw.startswith("postgresql://"):
        raw = "postgresql+psycopg2://" + raw[len("postgresql://") :]
    return raw


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "pgu-invoice-portal-dev-key-2026")
    SQLALCHEMY_DATABASE_URI = resolve_database_uri()
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    DATE_FORMAT = "%Y-%m-%d"

    MAIL_ENABLED = os.environ.get("MAIL_ENABLED", "false").lower() == "true"
    MAIL_HOST = os.environ.get("MAIL_HOST", "smtp.office365.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "pgu.invoice@posco.com")
    MAIL_USE_TLS = True
    HQ_COPY_EMAIL = os.environ.get("HQ_COPY_EMAIL", "hoan3532@poscohrd.com")
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    BANK_NAME = "KEB HANA BANK"
    BANK_BRANCH = "Songdosindosi Branch"
    BANK_ACCOUNT_NAME = "POSCO Group University"
    BANK_ACCOUNT_NO = os.environ.get("BANK_ACCOUNT_NO", "123-890012-12345")
    BANK_SWIFT = "KOEXKRSE"

    PGU_NAME = "POSCO Group University"
    PGU_DEPT = "POSCO Human Resources & Innovation Institute"
    PGU_ADDRESS = (
        "57, Songdogwahak-ro, Yeonsu-gu,\nIncheon 21985, Republic of Korea"
    )
    PGU_PHONE = ""
    PGU_SIGNATORY = "YANG, BYEONGHO"
    PGU_TITLE = "PRESIDENT & CEO, PGU"

    INITIAL_SUBSIDIARY_PASSWORD = "posco1234"
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin1004"

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = BASE_DIR / "uploads"
PDF_DIR = BASE_DIR / "generated_pdfs"
OUTBOX_DIR = BASE_DIR / "outbox"
STATIC_DIR = BASE_DIR / "static"
STAMP_PATH = INSTANCE_DIR / "pgu_stamp.png"
POSCO_CI_PATH = STATIC_DIR / "img" / "pgu_ci_white.png"

load_dotenv(BASE_DIR / ".env", override=True)


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

    MAIL_SERVER = (os.environ.get("MAIL_SERVER") or "smtp.gmail.com").strip()
    MAIL_PORT = int(os.environ.get("MAIL_PORT") or 587)
    MAIL_USERNAME = (os.environ.get("MAIL_USERNAME") or "mileg8744@gmail.com").strip()
    MAIL_PASSWORD = (os.environ.get("MAIL_PASSWORD") or "").strip()
    MAIL_FROM = (os.environ.get("MAIL_FROM") or "mileg8744@gmail.com").strip()
    MAIL_FROM_NAME = (os.environ.get("MAIL_FROM_NAME") or "POSCO Group University").strip()
    PORTAL_URL = (os.environ.get("PORTAL_URL") or "https://invoice2-icp0.onrender.com").strip()
    HQ_COPY_EMAIL = os.environ.get("HQ_COPY_EMAIL", "hoan3532@poscohrd.com")

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

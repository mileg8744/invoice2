"""Refresh local SQLite from the Excel master. Does not touch Render Postgres.

Default is dry-run. Pass --apply only after explicit approval.
Temporary subsidiary password is {code}1234, stored only as a Werkzeug hash.
"""
from __future__ import annotations

import argparse
import os
import shutil
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from config import INSTANCE_DIR, Config
from models import Invoice, InvoiceItem, Subsidiary, Training, User

EXCEL_PATH = Path(r"c:\Users\junge\OneDrive\Desktop\인보이스_DB_전체데이터_업로드용_ver.1.xlsx")
PASSWORD_SUFFIX = "1234"
REMAP_OLD_TO_NEW = {"02TH01": "02TH25", "02VN01": "02VN20"}
REMAP_NEW_TO_OLD = {v: k for k, v in REMAP_OLD_TO_NEW.items()}
# Section 2 requested deleting the 2 demo invoices with the 4 trainings.
# Additional note asked to preserve them. Recommended default is DELETE.
DELETE_DEMO_INVOICES = True


def refuse_if_not_local_sqlite() -> str:
    if (os.environ.get("RENDER") or "").strip().lower() in {"1", "true", "yes"}:
        raise SystemExit("REFUSE: RENDER is set. This script only updates local SQLite.")
    uri = Config.SQLALCHEMY_DATABASE_URI
    if not uri.startswith("sqlite:///"):
        raise SystemExit(f"REFUSE: database is not SQLite: {uri[:40]}")
    return uri


def sqlite_paths(uri: str) -> dict:
    db_path = Path(uri.replace("sqlite:///", "", 1))
    flask_fallback = INSTANCE_DIR / "pgu_invoices.db"
    return {
        "uri": uri,
        "resolved": db_path.resolve(),
        "instance_file": flask_fallback.resolve(),
        "same_file": db_path.resolve() == flask_fallback.resolve(),
        "backup_dir": (INSTANCE_DIR / "backups").resolve(),
        "exists": db_path.exists(),
        "size": db_path.stat().st_size if db_path.exists() else 0,
    }


def backup_sqlite(db_path: Path) -> Path:
    dest_dir = INSTANCE_DIR / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"pgu_invoices_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(db_path, dest)
    return dest


def temp_password(code: str) -> str:
    raw = f"{code.strip().upper()}{PASSWORD_SUFFIX}"
    if len(raw) < 8:
        raise RuntimeError(f"temporary password shorter than 8 characters: {code}")
    return raw


def hash_temp_password(code: str) -> str:
    return generate_password_hash(temp_password(code))


def sheet_rows(wb, name: str) -> list[dict]:
    ws = wb[name]
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    out = []
    for r in rows[1:]:
        if r is None or all(v is None or str(v).strip() == "" for v in r):
            continue
        out.append({headers[i]: r[i] if i < len(r) else None for i in range(len(headers))})
    return out


def norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    if s.lower() in {"none", "null"}:
        return ""
    return s


def as_date(v):
    if v is None or v == "":
        raise ValueError("missing date")
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def as_decimal_price(v) -> Decimal:
    if v is None or v == "":
        raw = Decimal("0")
    elif isinstance(v, Decimal):
        raw = v
    elif isinstance(v, int):
        raw = Decimal(v)
    elif isinstance(v, float):
        raw = Decimal(str(v))
    else:
        raw = Decimal(str(v).replace(",", "").strip())
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def as_int_or_none(v):
    if v is None or v == "":
        return None
    return int(v)


def excel_company(row: dict) -> str:
    return norm(row.get("Company") or row.get("company"))


def excel_list_no(row: dict):
    return as_int_or_none(row.get("code num.") if row.get("code num.") not in (None, "") else row.get("list_no"))


def fill_sub_from_excel(sub: Subsidiary, row: dict, code: str) -> list[str]:
    mapping = {
        "code": code,
        "list_no": excel_list_no(row),
        "company": excel_company(row),
        "region": norm(row.get("region")) or sub.region,
        "region_en": norm(row.get("region_en")) or sub.region_en,
        "country": norm(row.get("country")) or sub.country,
        "country_en": norm(row.get("country_en")) or sub.country_en,
        "entity_type": norm(row.get("entity_type")),
        "name_ko": norm(row.get("Official Company Name") or row.get("name_ko")),
        "name_en": norm(row.get("Company Name on Invoice") or row.get("name_en")),
        "address_en": norm(row.get("address_en")),
        "notes": norm(row.get("notes")),
        "phone": norm(row.get("phone")),
        "status": norm(row.get("status")) or "active",
        "emails": "",
        "hr_emails": "",
    }
    changed = []
    for key, new in mapping.items():
        old = getattr(sub, key)
        if old != new:
            changed.append(f"{key}: {old!r} -> {new!r}")
            setattr(sub, key, new)
    return changed


def load_excel():
    wb = load_workbook(EXCEL_PATH, data_only=True)
    return sheet_rows(wb, "해외법인"), sheet_rows(wb, "교육과정")


def plan(session) -> dict:
    excel_subs, excel_tr = load_excel()
    excel_by_code = {norm(r.get("code")).upper(): r for r in excel_subs}
    db_subs = session.query(Subsidiary).all()
    db_by_code = {norm(s.code).upper(): s for s in db_subs}

    insert_codes = []
    update_rows = []
    remap_rows = []
    for code, row in sorted(excel_by_code.items()):
        if code in REMAP_NEW_TO_OLD:
            old = REMAP_NEW_TO_OLD[code]
            if old not in db_by_code:
                raise SystemExit(f"remap source missing: {old}")
            remap_rows.append((old, code, db_by_code[old], row))
            continue
        if code in db_by_code:
            update_rows.append((code, db_by_code[code], row))
        else:
            insert_codes.append(code)

    keep_codes = sorted(
        c for c in db_by_code if c not in excel_by_code and c not in REMAP_OLD_TO_NEW
    )
    decimal_prices = []
    for r in excel_tr:
        price = as_decimal_price(r.get("unit_price_krw"))
        if price != price.to_integral_value():
            decimal_prices.append((norm(r.get("title")), as_decimal_price(r.get("unit_price_krw")), r.get("unit_price_krw")))
    return {
        "excel_subs": excel_by_code,
        "excel_tr": excel_tr,
        "insert_codes": insert_codes,
        "update_rows": update_rows,
        "remap_rows": remap_rows,
        "keep_codes": keep_codes,
        "db_by_code": db_by_code,
        "decimal_prices": decimal_prices,
    }


def print_plan(p: dict, session, paths: dict) -> None:
    invoices = session.query(Invoice).all()
    items = session.query(InvoiceItem).all()
    users = session.query(User).all()
    trainings = session.query(Training).all()
    print("=== SQLITE PATH ===")
    print("uri", paths["uri"])
    print("resolved", paths["resolved"])
    print("flask instance file", paths["instance_file"])
    print("same_file", paths["same_file"])
    print("backup_dir", paths["backup_dir"])
    print("size_bytes", paths["size"])
    print()
    print("=== ACTION COUNTS ===")
    print("subsidiary INSERT", len(p["insert_codes"]))
    print("subsidiary UPDATE same-code", len(p["update_rows"]))
    print("subsidiary REMAP keep-id", len(p["remap_rows"]))
    print("subsidiary KEEP", len(p["keep_codes"]))
    print("subsidiary DELETE", 0)
    print("user INSERT", len(p["insert_codes"]))
    print("user RENAME", len(p["remap_rows"]))
    print("temp password pattern", "{code}1234 hashed, min 8 chars, must_change_password=True")
    print("admin KEEP (password unchanged)", sum(1 for u in users if u.username == "admin"))
    print("training DELETE", len(trainings))
    print("training INSERT", len(p["excel_tr"]))
    if DELETE_DEMO_INVOICES:
        print("invoice DELETE", len(invoices), "item DELETE", len(items))
        print("audit_logs KEEP (not rewritten)")
    else:
        print("invoice KEEP", len(invoices), "item KEEP", len(items))
    print("non-integer excel unit prices stored as Numeric(14,2)", len(p["decimal_prices"]))
    for title, stored, original in p["decimal_prices"]:
        print(f"  {title}: excel={original} stored={stored}")
    print()
    print("REMAP")
    for old, new, sub, row in p["remap_rows"]:
        print(f"  id={sub.id} {old} -> {new} | {sub.name_en} -> {norm(row.get('Company Name on Invoice'))}")
    print("UPDATE")
    for code, sub, row in p["update_rows"]:
        print(f"  id={sub.id} {code} | {sub.name_en} -> {norm(row.get('Company Name on Invoice'))}")
    print("INSERT", ", ".join(p["insert_codes"]))
    print("KEEP", ", ".join(p["keep_codes"]))
    print()
    print("INVOICES")
    for inv in invoices:
        print(
            f"  {inv.invoice_no} status={inv.status} sub_id={inv.subsidiary_id} "
            f"billed_code={inv.billed_code} issued_at={inv.issued_at} amount_krw={inv.amount_krw}"
        )
    print("INVOICE ITEMS")
    for it in items:
        print(
            f"  item {it.id} invoice_id={it.invoice_id} training_id={it.training_id} "
            f"{it.description} qty={it.qty} unit={it.unit_price_krw}"
        )
    print("OLD TRAININGS TO DELETE")
    for t in trainings:
        print(f"  id={t.id} {t.title} unit={t.unit_price_krw}")
    print("NEW TRAININGS (excel unit_price as Decimal, not rounded)")
    for r in p["excel_tr"]:
        print(
            f"  {r.get('title')} | {r.get('start_date')} | "
            f"{r.get('Program Coordinator')} | price={as_decimal_price(r.get('unit_price_krw'))}"
        )


def rebuild_amount_tables(engine) -> None:
    InvoiceItem.__table__.drop(engine, checkfirst=True)
    Invoice.__table__.drop(engine, checkfirst=True)
    Training.__table__.drop(engine, checkfirst=True)
    Training.__table__.create(engine)
    Invoice.__table__.create(engine)
    InvoiceItem.__table__.create(engine)


def apply_entity_changes(session, p: dict) -> None:
    for old, new, sub, row in p["remap_rows"]:
        fill_sub_from_excel(sub, row, new)
        user = session.query(User).filter_by(username=old).one()
        if session.query(User).filter(User.username == new, User.id != user.id).first():
            raise RuntimeError(f"username already taken: {new}")
        user.username = new
        user.password_hash = hash_temp_password(new)
        user.must_change_password = True
        user.is_active = True
        user.role = "subsidiary"
        user.subsidiary_id = sub.id
        if not DELETE_DEMO_INVOICES:
            for inv in session.query(Invoice).filter_by(subsidiary_id=sub.id).all():
                if (inv.billed_code or "").strip().upper() == old:
                    inv.billed_code = new

    for _code, sub, row in p["update_rows"]:
        fill_sub_from_excel(sub, row, _code)

    for code in p["insert_codes"]:
        row = p["excel_subs"][code]
        sub = Subsidiary(
            code=code,
            region=norm(row.get("region")) or "기타",
            region_en=norm(row.get("region_en")) or "Other",
            country=norm(row.get("country")) or "",
            country_en=norm(row.get("country_en")) or "",
            name_ko=norm(row.get("Official Company Name") or row.get("name_ko")) or code,
            name_en=norm(row.get("Company Name on Invoice") or row.get("name_en")) or code,
        )
        fill_sub_from_excel(sub, row, code)
        session.add(sub)
        session.flush()
        if session.query(User).filter_by(username=code).first():
            raise RuntimeError(f"username already exists: {code}")
        session.add(
            User(
                username=code,
                password_hash=hash_temp_password(code),
                role="subsidiary",
                subsidiary_id=sub.id,
                must_change_password=True,
                is_active=True,
            )
        )

    for user in session.query(User).filter(User.role == "subsidiary").all():
        sub = session.get(Subsidiary, user.subsidiary_id) if user.subsidiary_id else None
        code = (sub.code if sub else user.username).strip().upper()
        user.password_hash = hash_temp_password(code)
        user.must_change_password = True

    admin = session.query(User).filter_by(username="admin").one()
    if admin.role != "admin":
        raise RuntimeError("admin role changed unexpectedly")

    session.query(InvoiceItem).delete()
    session.query(Invoice).delete()
    session.query(Training).delete()
    session.flush()


def insert_trainings(session, p: dict) -> None:
    for row in p["excel_tr"]:
        price = as_decimal_price(row.get("unit_price_krw"))
        session.add(
            Training(
                title=norm(row.get("title")),
                title_en=norm(row.get("title_en") or row.get("title")),
                start_date=as_date(row.get("start_date")),
                end_date=as_date(row.get("end_date")),
                instructor=norm(row.get("Program Coordinator") or row.get("instructor")),
                unit_price_krw=price,
                learner_count=as_int_or_none(row.get("learner_count")) or 0,
                session_no=as_int_or_none(row.get("session_no")) or 0,
                learners=norm(row.get("learners")),
            )
        )
    session.flush()


def verify(session) -> None:
    problems = []
    codes = [c for (c,) in session.query(Subsidiary.code).all()]
    if len(codes) != len(set(c.upper() for c in codes)):
        problems.append("duplicate subsidiary codes")
    if session.query(Subsidiary).filter_by(code="01US02").one().name_en != "POSCO America Corporation":
        problems.append("01US02 is not POSCO America")
    if session.query(Subsidiary).filter_by(code="02US40").one().name_en != "POSCO America Alabama Processing Center Co., Ltd.":
        problems.append("02US40 is not AAPC Alabama")
    if session.query(Subsidiary).filter_by(code="02TH25").count() != 1:
        problems.append("02TH25 missing")
    if session.query(Subsidiary).filter_by(code="02TH01").count() != 0:
        problems.append("02TH01 still present")
    if session.query(Subsidiary).filter_by(code="02VN20").count() != 1:
        problems.append("02VN20 missing")
    if session.query(Subsidiary).filter_by(code="02VN01").count() != 0:
        problems.append("02VN01 still present")
    if session.query(Training).count() != 29:
        problems.append(f"trainings {session.query(Training).count()} != 29")
    ptkp = session.query(Training).filter(Training.title.contains("PTKP")).first()
    if not ptkp or Decimal(str(ptkp.unit_price_krw)) != Decimal("349925.28"):
        problems.append(f"PTKP price {getattr(ptkp, 'unit_price_krw', None)}")
    job4 = session.query(Training).filter(Training.title.contains("Carbon Neutrality ④")).first()
    if not job4 or Decimal(str(job4.unit_price_krw)) != Decimal("768929.60"):
        problems.append(f"JobSchool4 price {getattr(job4, 'unit_price_krw', None)}")
    if DELETE_DEMO_INVOICES:
        if session.query(Invoice).count() != 0:
            problems.append("demo invoices not deleted")
        if session.query(InvoiceItem).count() != 0:
            problems.append("demo invoice items not deleted")
        th = session.query(Subsidiary).filter_by(code="02TH25").one()
        vn = session.query(Subsidiary).filter_by(code="02VN20").one()
        if session.query(User).filter_by(username="02TH25").one().subsidiary_id != th.id:
            problems.append("02TH25 user not linked")
        if session.query(User).filter_by(username="02VN20").one().subsidiary_id != vn.id:
            problems.append("02VN20 user not linked")
    else:
        if session.query(Invoice).count() != 2:
            problems.append("invoice count changed")
        inv1 = session.query(Invoice).filter_by(invoice_no="PGU-2026-02-001").one()
        inv2 = session.query(Invoice).filter_by(invoice_no="PGU-2026-02-002").one()
        if inv1.status != "issued" or inv2.status != "issued":
            problems.append("invoice status changed")
        if inv1.billed_code != "02TH25" or inv2.billed_code != "02VN20":
            problems.append("invoice billed_code not remapped")
        if inv1.issued_at is None or inv2.issued_at is None:
            problems.append("issued_at lost")
        if session.query(InvoiceItem).count() != 4:
            problems.append("invoice items lost")
    admin = session.query(User).filter_by(username="admin").one()
    if admin.role != "admin":
        problems.append("admin role")
    if session.query(User).filter_by(username="02TH01").first():
        problems.append("old username 02TH01 remains")
    if session.query(User).filter(User.role == "subsidiary").count() != session.query(Subsidiary).count():
        problems.append("user/subsidiary count mismatch")
    if problems:
        raise RuntimeError("VERIFY FAIL: " + "; ".join(problems))
    print("VERIFY OK")
    print(" subsidiaries", session.query(Subsidiary).count())
    print(" users", session.query(User).count())
    print(" trainings", session.query(Training).count())
    print(" invoices", session.query(Invoice).count())
    print(" items", session.query(InvoiceItem).count())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write local SQLite. Default is dry-run.")
    args = parser.parse_args()
    uri = refuse_if_not_local_sqlite()
    paths = sqlite_paths(uri)
    if not paths["exists"]:
        raise SystemExit(f"DB not found: {paths['resolved']}")
    if not paths["same_file"]:
        raise SystemExit("REFUSE: resolved SQLite path is not Flask instance/pgu_invoices.db")

    engine = create_engine(uri, future=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        p = plan(session)
        print_plan(p, session, paths)
        if not args.apply:
            print("\nDRY-RUN only. No backup, no writes. Re-run with --apply after approval.")
            return
        backup = backup_sqlite(Path(paths["resolved"]))
        print("BACKUP", backup)
        admin_hash = session.query(User).filter_by(username="admin").one().password_hash
        apply_entity_changes(session, p)
        session.commit()
        session.close()
        rebuild_amount_tables(engine)
        session = Session()
        insert_trainings(session, p)
        verify(session)
        if session.query(User).filter_by(username="admin").one().password_hash != admin_hash:
            raise RuntimeError("admin password_hash changed")
        session.commit()
        print("COMMITTED local SQLite only")
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        print("ROLLED BACK")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()

"""Copy local SQLite into Render Postgres via MIGRATION_DATABASE_URL only.

Does not change DATABASE_URL, Flask config, Git, or Render web settings.
Never prints credentials. SSL verification is not disabled.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dotenv import load_dotenv
from sqlalchemy import Boolean, Date, DateTime, Float, Numeric, create_engine, inspect, text
from sqlalchemy.engine import Engine

from config import INSTANCE_DIR
from inspect_migration_postgres import (
    APP_TABLES,
    describe_target,
    normalize_migration_url,
    redact,
    sqlite_path,
)
from models import (
    AuditLog,
    Base,
    Invoice,
    InvoiceItem,
    Subsidiary,
    Training,
    User,
)

INSERT_ORDER = [
    Subsidiary.__table__,
    Training.__table__,
    User.__table__,
    Invoice.__table__,
    InvoiceItem.__table__,
    AuditLog.__table__,
]
EXPECTED_COUNTS = {
    "subsidiaries": 128,
    "users": 129,
    "trainings": 29,
    "invoices": 0,
    "invoice_items": 0,
    "audit_logs": 140,
}
MONEY_COLS = {
    "unit_price_krw",
    "amount_krw",
    "amount_fx",
}
CHECK_CODES = ["01US02", "02US40", "02TH25", "02VN20"]


def load_migration_url() -> str:
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
    raw = (os.environ.get("MIGRATION_DATABASE_URL") or "").strip()
    if not raw:
        raise SystemExit("MIGRATION_DATABASE_URL is missing.")
    if raw.lower().startswith(("postgres://", "postgresql://")) and "=" not in raw.split("\n", 1)[0]:
        pass
    return normalize_migration_url(raw)


def pg_engine(url: str) -> Engine:
    sslmode = parse_qs(urlsplit(url).query).get("sslmode", ["require"])[-1]
    return create_engine(url, future=True, pool_pre_ping=True, connect_args={"sslmode": sslmode})


def backup_sqlite() -> Path:
    src = sqlite_path()
    dest_dir = INSTANCE_DIR / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"pgu_invoices_pre_pg_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(src, dest)
    src_con = sqlite3.connect(str(src))
    bak_con = sqlite3.connect(str(dest))
    try:
        src_ok = src_con.execute("PRAGMA integrity_check").fetchone()[0]
        bak_ok = bak_con.execute("PRAGMA integrity_check").fetchone()[0]
        if src_ok != "ok" or bak_ok != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: src={src_ok} backup={bak_ok}")
        for table in APP_TABLES:
            a = src_con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            b = bak_con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if a != b:
                raise RuntimeError(f"backup count mismatch {table}: {a} vs {b}")
            if a != EXPECTED_COUNTS[table]:
                raise RuntimeError(f"source count unexpected {table}: {a} != {EXPECTED_COUNTS[table]}")
    finally:
        src_con.close()
        bak_con.close()
    return dest


def sqlite_counts() -> dict[str, int]:
    con = sqlite3.connect(str(sqlite_path()))
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in APP_TABLES}
    finally:
        con.close()


def coerce(col, value):
    if value is None:
        return None
    if col.name in MONEY_COLS or isinstance(col.type, Numeric):
        if isinstance(value, Decimal):
            raw = value
        else:
            raw = Decimal(str(value))
        return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(col.type, Boolean):
        return bool(value)
    if isinstance(col.type, DateTime):
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("T", " ").strip())
    if isinstance(col.type, Date):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    if isinstance(col.type, Float) and not isinstance(value, float):
        return float(value)
    return value


def read_sqlite_rows(table) -> list[dict]:
    con = sqlite3.connect(str(sqlite_path()))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(f"SELECT * FROM {table.name} ORDER BY id").fetchall()
    finally:
        con.close()
    out = []
    for row in rows:
        item = {}
        mapping = {k.lower(): row[k] for k in row.keys()}
        for col in table.columns:
            if col.name not in mapping:
                continue
            item[col.name] = coerce(col, mapping[col.name])
        out.append(item)
    return out


def sqlite_hashes() -> dict[str, str]:
    con = sqlite3.connect(str(sqlite_path()))
    try:
        return {r[0]: r[1] for r in con.execute("SELECT username, password_hash FROM users")}
    finally:
        con.close()


def assert_postgres_empty(engine: Engine) -> None:
    with engine.connect() as conn:
        tables = inspect(conn).get_table_names()
        extra = [t for t in tables if t not in {"spatial_ref_sys"}]
        if extra:
            raise SystemExit(f"ABORT: Postgres public schema already has tables: {extra}")
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("target_database", db)
        print("postgres_public_tables", extra or "(none)")


def reset_sequences(conn) -> dict[str, str]:
    result = {}
    for table in APP_TABLES:
        seq = conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table}).scalar()
        if not seq:
            result[table] = "no sequence"
            continue
        max_id = conn.execute(text(f'SELECT MAX(id) FROM "{table}"')).scalar()
        if max_id is None:
            conn.execute(text("SELECT setval(:s, 1, false)"), {"s": seq})
            result[table] = "setval 1 is_called=false"
        else:
            conn.execute(text("SELECT setval(:s, :v, true)"), {"s": seq, "v": int(max_id)})
            result[table] = f"setval {max_id} is_called=true"
    return result


def verify(engine: Engine, src_counts: dict[str, int], src_hashes: dict[str, str]) -> list[str]:
    problems = []
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        for name in APP_TABLES:
            if name not in tables:
                problems.append(f"missing table {name}")
                continue
            n = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
            if n != src_counts[name]:
                problems.append(f"count {name}: postgres {n} != sqlite {src_counts[name]}")
        for code in CHECK_CODES:
            row = conn.execute(
                text("SELECT code, name_en FROM subsidiaries WHERE code = :c"),
                {"c": code},
            ).first()
            if not row:
                problems.append(f"missing code {code}")
        ptkp = conn.execute(
            text("SELECT unit_price_krw FROM trainings WHERE title LIKE :q"),
            {"q": "%PTKP%"},
        ).scalar()
        if ptkp is None or Decimal(str(ptkp)) != Decimal("349925.28"):
            problems.append(f"PTKP price {ptkp}")
        pg_hashes = {
            r[0]: r[1]
            for r in conn.execute(text("SELECT username, password_hash FROM users"))
        }
        if set(pg_hashes) != set(src_hashes):
            problems.append("username set mismatch")
        changed = sum(1 for u, h in src_hashes.items() if pg_hashes.get(u) != h)
        if changed:
            problems.append(f"password_hash changed for {changed} users")
        fk_ok = conn.execute(text("SELECT COUNT(*) FROM users u LEFT JOIN subsidiaries s ON u.subsidiary_id = s.id WHERE u.subsidiary_id IS NOT NULL AND s.id IS NULL")).scalar()
        if fk_ok:
            problems.append(f"orphan users.subsidiary_id {fk_ok}")
        name_us = conn.execute(text("SELECT name_en FROM subsidiaries WHERE code='01US02'")).scalar()
        name_aapc = conn.execute(text("SELECT name_en FROM subsidiaries WHERE code='02US40'")).scalar()
        if name_us != "POSCO America Corporation":
            problems.append(f"01US02 name_en {name_us}")
        if name_aapc != "POSCO America Alabama Processing Center Co., Ltd.":
            problems.append(f"02US40 name_en {name_aapc}")
        for table in APP_TABLES:
            seq = conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table}).scalar()
            max_id = conn.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')).scalar()
            if seq and max_id:
                last = conn.execute(text(f"SELECT last_value FROM {seq}")).scalar()
                if last is not None and int(last) < int(max_id):
                    problems.append(f"sequence {table} {last} < max {max_id}")
        money_type = str(
            next(c["type"] for c in inspector.get_columns("trainings") if c["name"] == "unit_price_krw")
        )
        if "NUMERIC" not in money_type.upper() and "DECIMAL" not in money_type.upper():
            problems.append(f"trainings.unit_price_krw type {money_type}")
        conn.rollback()
    return problems


def migrate() -> None:
    url = load_migration_url()
    target = describe_target(url)
    print("=== SQLITE BACKUP ===")
    backup = backup_sqlite()
    print("backup", backup)
    src_counts = sqlite_counts()
    src_hashes = sqlite_hashes()
    print("sqlite_counts", src_counts)
    print("hash_count", len(src_hashes))
    print("=== POSTGRES TARGET ===")
    print("host", target["host"])
    print("database", target["database"])
    print("sslmode", target["sslmode"])
    engine = pg_engine(url)
    created = False
    copied = False
    try:
        assert_postgres_empty(engine)
        print("schema create_all from Flask models")
        Base.metadata.create_all(engine)
        created = True
        inspector = inspect(engine)
        code_unique = False
        for uq in inspector.get_unique_constraints("subsidiaries"):
            if list(uq.get("column_names") or []) == ["code"]:
                code_unique = True
        for idx in inspector.get_indexes("subsidiaries"):
            if idx.get("unique") and list(idx.get("column_names") or []) == ["code"]:
                code_unique = True
        if code_unique:
            raise RuntimeError("subsidiaries.code is UNIQUE; aborting (must be non-unique index only)")
        print("copying rows")
        with engine.begin() as conn:
            for table in INSERT_ORDER:
                rows = read_sqlite_rows(table)
                print(f"  {table.name}", len(rows))
                if not rows:
                    continue
                conn.execute(table.insert(), rows)
            seq_info = reset_sequences(conn)
            print("sequences", seq_info)
        copied = True
        print("=== VERIFY (same connection pool) ===")
        problems = verify(engine, src_counts, src_hashes)
        if problems:
            raise RuntimeError("VERIFY FAIL: " + "; ".join(problems))
        engine.dispose()
        print("=== VERIFY (reconnect) ===")
        engine2 = pg_engine(url)
        try:
            problems = verify(engine2, src_counts, src_hashes)
            if problems:
                raise RuntimeError("RECONNECT VERIFY FAIL: " + "; ".join(problems))
            with engine2.connect() as conn:
                print("reconnect_counts", {t: conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() for t in APP_TABLES})
                print(
                    "sample_codes",
                    list(
                        conn.execute(
                            text("SELECT code, name_en FROM subsidiaries WHERE code IN ('01US02','02US40','02TH25','02VN20') ORDER BY code")
                        )
                    ),
                )
                print(
                    "ptkp",
                    conn.execute(text("SELECT unit_price_krw FROM trainings WHERE title LIKE '%PTKP%'")).scalar(),
                )
        finally:
            engine2.dispose()
        print("MIGRATION OK")
        print("sqlite", src_counts)
        print("postgres matches sqlite counts")
        print("password hashes copied verbatim")
    except Exception:
        if created and not copied:
            print("ERROR before data commit — dropping tables created in this run to restore empty DB")
            try:
                Base.metadata.drop_all(engine)
            except Exception as drop_exc:
                print("drop_all failed:", redact(str(drop_exc)))
            print("target restored empty")
        elif copied:
            print("DATA COMMITTED; tables were not dropped. Inspect verify errors above.")
        else:
            print("No Postgres schema changes applied")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        migrate()
    except Exception as exc:
        print("FAILED:", redact(f"{type(exc).__name__}: {exc}"))
        raise SystemExit(1) from None

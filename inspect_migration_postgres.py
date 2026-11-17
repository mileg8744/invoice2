"""Read-only inspection of Render Postgres via MIGRATION_DATABASE_URL.

Never prints credentials. Never writes. Never uses DATABASE_URL.
Does not disable SSL certificate checks (sslmode=disable is refused).
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from config import INSTANCE_DIR

APP_TABLES = [
    "users",
    "subsidiaries",
    "trainings",
    "invoices",
    "invoice_items",
    "audit_logs",
]
EXPECTED_FK = [
    ("users", "subsidiary_id", "subsidiaries", "id"),
    ("invoices", "subsidiary_id", "subsidiaries", "id"),
    ("invoices", "training_id", "trainings", "id"),
    ("invoice_items", "invoice_id", "invoices", "id"),
]
MONEY_COLUMNS = [
    ("trainings", "unit_price_krw"),
    ("invoices", "unit_price_krw"),
    ("invoices", "amount_krw"),
    ("invoices", "amount_fx"),
    ("invoice_items", "unit_price_krw"),
    ("invoice_items", "amount_krw"),
]


def redact(text_value: str) -> str:
    value = str(text_value or "")
    value = re.sub(r"postgres(?:ql)?(?:\+psycopg2)?://[^\s'\"<>]+", "postgresql://***", value, flags=re.I)
    value = re.sub(r":[^:@/\s]+@", ":***@", value)
    return value


def describe_target(raw: str) -> dict:
    parsed = urlsplit(raw)
    query = parse_qs(parsed.query)
    sslmode = (query.get("sslmode") or [""])[0] or "(none in URL)"
    return {
        "scheme": parsed.scheme.split("+")[0],
        "host": parsed.hostname or "",
        "port": parsed.port,
        "database": (parsed.path or "").lstrip("/").split("?")[0],
        "sslmode": sslmode,
        "user_present": bool(parsed.username),
    }


def normalize_migration_url(raw: str) -> str:
    url = raw.strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    elif url.startswith("postgresql+psycopg2://"):
        pass
    else:
        raise SystemExit("MIGRATION_DATABASE_URL must be a postgres connection URL.")

    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    sslmode = (query.get("sslmode") or [""])[0].strip().lower()
    if sslmode in {"disable", "allow"}:
        raise SystemExit(f"REFUSE: sslmode={sslmode} disables or weakens TLS. Use require or verify-full.")
    if not sslmode:
        query["sslmode"] = ["require"]
    new_query = urlencode({k: v[-1] if v else "" for k, v in query.items()})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))


def sqlite_path() -> Path:
    return INSTANCE_DIR / "pgu_invoices.db"


def inspect_sqlite() -> dict:
    path = sqlite_path()
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY 1")]
    counts = {}
    for name in APP_TABLES:
        if name in tables:
            counts[name] = cur.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        else:
            counts[name] = None
    columns = {}
    fks = []
    uniques = []
    for name in tables:
        columns[name] = [(r["name"], r["type"], r["pk"], r["notnull"]) for r in cur.execute(f"PRAGMA table_info({name})")]
        for fk in cur.execute(f"PRAGMA foreign_key_list({name})"):
            fks.append((name, fk["from"], fk["table"], fk["to"]))
    for r in cur.execute("SELECT tbl_name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
        sql = r["sql"] or ""
        if "UNIQUE" in sql.upper():
            uniques.append((r["tbl_name"], sql))
    hash_sample = []
    if "users" in tables:
        for row in cur.execute("SELECT username, substr(password_hash,1,12) AS prefix, length(password_hash) AS n FROM users ORDER BY id LIMIT 5"):
            hash_sample.append({"username": row["username"], "prefix": row["prefix"], "len": row["n"]})
        plaintext = cur.execute(
            "SELECT COUNT(*) FROM users WHERE password_hash IN ('1234','posco1234') OR password_hash NOT LIKE '%$%'"
        ).fetchone()[0]
    else:
        plaintext = None
    money = {}
    if "trainings" in tables:
        ptkp = cur.execute(
            "SELECT title, typeof(unit_price_krw), unit_price_krw FROM trainings WHERE title LIKE '%PTKP%'"
        ).fetchone()
        lo_hi = cur.execute("SELECT MIN(unit_price_krw), MAX(unit_price_krw) FROM trainings").fetchone()
        money["ptkp"] = {"title" : ptkp[0], "typeof": ptkp[1], "value": ptkp[2]} if ptkp else None
        money["unit_min_max"] = list(lo_hi) if lo_hi else None
    con.close()
    return {
        "path": str(path.resolve()),
        "tables": tables,
        "counts": counts,
        "columns": columns,
        "fks": fks,
        "uniques": uniques,
        "hash_sample": hash_sample,
        "plaintext_or_unhashed": plaintext,
        "money": money,
    }


def inspect_postgres(engine: Engine) -> dict:
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        inspector = inspect(conn)
        tables = sorted(inspector.get_table_names())
        counts = {}
        columns = {}
        fks = []
        uniques = []
        indexes = []
        for name in tables:
            columns[name] = [
                (c["name"], str(c["type"]), c.get("nullable"), c.get("default"))
                for c in inspector.get_columns(name)
            ]
            for fk in inspector.get_foreign_keys(name):
                referred = fk.get("referred_table")
                for src, dst in zip(fk.get("constrained_columns") or [], fk.get("referred_columns") or []):
                    fks.append((name, src, referred, dst))
            for uq in inspector.get_unique_constraints(name):
                uniques.append((name, uq.get("name"), list(uq.get("column_names") or [])))
            for idx in inspector.get_indexes(name):
                indexes.append((name, idx.get("name"), idx.get("unique"), list(idx.get("column_names") or [])))
            if name in APP_TABLES:
                counts[name] = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
        nonempty = {k: v for k, v in counts.items() if v}
        version = conn.execute(text("SHOW server_version")).scalar()
        db_name = conn.execute(text("SELECT current_database()")).scalar()
        hash_info = None
        if "users" in tables and counts.get("users"):
            hash_info = conn.execute(
                text(
                    "SELECT COUNT(*) AS n, "
                    "SUM(CASE WHEN password_hash LIKE 'scrypt:%' THEN 1 ELSE 0 END) AS scrypt, "
                    "SUM(CASE WHEN password_hash LIKE 'pbkdf2:%' THEN 1 ELSE 0 END) AS pbkdf2 "
                    "FROM users"
                )
            ).mappings().first()
        conn.rollback()
    return {
        "server_version": version,
        "database": db_name,
        "tables": tables,
        "counts": counts,
        "nonempty_app_tables": nonempty,
        "columns": columns,
        "fks": fks,
        "uniques": uniques,
        "indexes": indexes,
        "hash_info": dict(hash_info) if hash_info else None,
    }


def print_sqlite(info: dict) -> None:
    print("=== LOCAL SQLITE (source) ===")
    print("path", info["path"])
    print("tables", info["tables"])
    print("counts", info["counts"])
    print("foreign keys", info["fks"])
    print("unique indexes")
    for item in info["uniques"]:
        print(" ", item[0], item[1])
    print("password hash samples", info["hash_sample"])
    print("unhashed/plaintext users", info["plaintext_or_unhashed"])
    print("money", info["money"])
    for table, col in MONEY_COLUMNS:
        cols = info["columns"].get(table) or []
        match = [c for c in cols if c[0] == col]
        print(f"  sqlite {table}.{col}", match[0][1] if match else "MISSING")


def print_postgres(target: dict, info: dict) -> None:
    print("=== RENDER POSTGRES (MIGRATION_DATABASE_URL, read-only) ===")
    print("host", target["host"])
    print("port", target["port"])
    print("database", info["database"])
    print("sslmode", target["sslmode"])
    print("server", info["server_version"])
    print("tables", info["tables"] or "(none in public schema)")
    print("app table counts", {k: info["counts"].get(k) for k in APP_TABLES})
    print("foreign keys", info["fks"] or "(none)")
    print("unique constraints", info["uniques"] or "(none)")
    if info["nonempty_app_tables"]:
        print("EXISTING DATA — do not overwrite")
        print(" nonempty", info["nonempty_app_tables"])
    else:
        print("app tables empty or missing — safe to plan a later load")
    if info["hash_info"]:
        print("password hashes", info["hash_info"])
    for table, col in MONEY_COLUMNS:
        cols = info["columns"].get(table) or []
        match = [c for c in cols if c[0] == col]
        print(f"  postgres {table}.{col}", match[0][1] if match else "MISSING")


def compare(sqlite_info: dict, pg_info: dict | None) -> None:
    print("=== COMPATIBILITY ===")
    print("SQLite BOOLEAN/INTEGER vs Postgres BOOLEAN/INTEGER: SQLAlchemy maps both.")
    print("SQLite DATETIME vs Postgres TIMESTAMP: copy as naive UTC timestamps.")
    print("SQLite TEXT vs Postgres TEXT/VARCHAR: compatible.")
    print("Numeric(14,2): SQLite stores REAL; Postgres NUMERIC(14,2) is exact scale.")
    print("  Load must use Decimal, not float, so 349925.28 stays 349925.28.")
    print("password_hash VARCHAR(255): Werkzeug scrypt strings fit; copy verbatim, do not re-hash.")
    print("Expected FKs:", EXPECTED_FK)
    print("invoice_items.training_id has no FK in the model (plain INTEGER). Keep it that way.")
    print("subsidiaries.code is indexed, not UNIQUE — Postgres must not add UNIQUE(code).")
    print("users.username UNIQUE, invoices.invoice_no UNIQUE — preserve.")
    if not pg_info:
        print("Postgres schema not available yet (MIGRATION_DATABASE_URL missing or connection failed).")
        return
    sqlite_tables = set(sqlite_info["tables"])
    pg_tables = set(pg_info["tables"])
    print("tables only in SQLite", sorted(sqlite_tables - pg_tables))
    print("tables only in Postgres", sorted(pg_tables - sqlite_tables))
    print("sqlite counts", sqlite_info["counts"])
    print("postgres counts", {k: pg_info["counts"].get(k) for k in APP_TABLES})


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
    if (os.environ.get("RENDER") or "").strip():
        print("NOTE: RENDER is set in this process. This script still ignores DATABASE_URL.")

    sqlite_info = inspect_sqlite()
    print_sqlite(sqlite_info)

    raw = (os.environ.get("MIGRATION_DATABASE_URL") or "").strip()
    if not raw:
        print()
        print("=== RENDER POSTGRES ===")
        print("MIGRATION_DATABASE_URL is missing. DATABASE_URL was not used.")
        print("Set MIGRATION_DATABASE_URL in the gitignored .env, then re-run this script.")
        compare(sqlite_info, None)
        return

    try:
        url = normalize_migration_url(raw)
        target = describe_target(url)
        engine = create_engine(
            url,
            future=True,
            pool_pre_ping=True,
            connect_args={"sslmode": parse_qs(urlsplit(url).query).get("sslmode", ["require"])[-1]},
        )
        pg_info = inspect_postgres(engine)
        print()
        print_postgres(target, pg_info)
        compare(sqlite_info, pg_info)
    except SystemExit:
        raise
    except Exception as exc:
        print()
        print("=== RENDER POSTGRES CONNECTION FAILED ===")
        print(redact(f"{type(exc).__name__}: {exc}"))
        compare(sqlite_info, None)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

"""Overseas-entity master helpers: emails, matching, JSON import."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from config import Config
from entity_types import resolve_entity_type
from mailer import parse_emails
from models import Invoice, Subsidiary, User, utcnow
from regions import resolve_region
from werkzeug.security import generate_password_hash

MASTER_JSON = Path(__file__).resolve().parent / "portal_corporations.json"

COUNTRY_KO_EN = {
    "아르헨티나": "Argentina",
    "미국": "USA",
    "독일": "Germany",
    "중국": "China",
    "일본": "Japan",
    "홍콩": "Hong Kong",
    "인도네시아": "Indonesia",
    "폴란드": "Poland",
    "베트남": "Vietnam",
    "태국": "Thailand",
    "말레이시아": "Malaysia",
    "필리핀": "Philippines",
    "인도": "India",
    "멕시코": "Mexico",
    "캐나다": "Canada",
    "브라질": "Brazil",
    "이탈리아": "Italy",
    "터키": "Turkey",
    "튀르키예": "Turkey",
    "호주": "Australia",
}


def emails_from_text(raw) -> list[str]:
    return parse_emails(raw or "")


def emails_to_text(items) -> str:
    seen = []
    for item in items or []:
        addr = str(item or "").strip()
        if not addr or "@" not in addr:
            continue
        if addr.lower() in {x.lower() for x in seen}:
            continue
        seen.append(addr)
    return "; ".join(seen)


def split_email_roles(to_items, cc_items) -> tuple[list[str], list[str]]:
    to_list = emails_from_text(emails_to_text(to_items))
    cc_list = []
    to_l = {e.lower() for e in to_list}
    for addr in emails_from_text(emails_to_text(cc_items)):
        if addr.lower() in to_l:
            continue
        if addr.lower() in {e.lower() for e in cc_list}:
            continue
        cc_list.append(addr)
    return to_list, cc_list


def contact_emails(sub) -> list[str]:
    return emails_from_text(getattr(sub, "emails", "") or "")


def hr_emails(sub) -> list[str]:
    return emails_from_text(getattr(sub, "hr_emails", "") or "")


def invoice_party(invoice) -> dict[str, str]:
    sub = getattr(invoice, "subsidiary", None)
    name = (getattr(invoice, "billed_name", None) or "").strip()
    address = (getattr(invoice, "billed_address", None) or "").strip()
    code = (getattr(invoice, "billed_code", None) or "").strip()
    if not name and sub:
        name = (sub.name_en or "").strip()
    if not address and sub:
        address = (sub.address_en or "").strip()
    if not code and sub:
        code = (sub.code or "").strip()
    return {"name": name, "address": address, "code": code}


def snapshot_invoice_party(invoice) -> None:
    if (getattr(invoice, "billed_name", None) or "").strip():
        return
    party = invoice_party(invoice)
    invoice.billed_name = party["name"]
    invoice.billed_address = party["address"]
    invoice.billed_code = party["code"]


def load_master_records(path: Path | None = None) -> list[dict]:
    src = path or MASTER_JSON
    data = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _norm(value) -> str:
    return str(value or "").strip()


def _norm_l(value) -> str:
    return _norm(value).lower()


def find_existing(db, rec) -> Subsidiary | None:
    code = _norm(rec.get("corporation_code")).upper()
    if not code:
        return None
    legal = _norm(rec.get("invoice_legal_name"))
    formal = _norm(rec.get("corporation_name"))
    address = _norm(rec.get("address"))
    cands = db.query(Subsidiary).filter(Subsidiary.code == code).all()
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]

    def score(row):
        pts = 0
        if legal and _norm_l(row.name_en) == _norm_l(legal):
            pts += 4
        if formal and _norm_l(row.name_ko) == _norm_l(formal):
            pts += 3
        if address and _norm_l(row.address_en) == _norm_l(address):
            pts += 2
        return pts

    ranked = sorted(((score(row), row.id, row) for row in cands), reverse=True)
    if ranked[0][0] > 0:
        return ranked[0][2]
    return None


def mark_duplicate_codes(db) -> int:
    counts = Counter(code for (code,) in db.query(Subsidiary.code).all() if code)
    flagged = 0
    for row in db.query(Subsidiary).all():
        review = counts.get(row.code, 0) > 1
        if bool(getattr(row, "needs_review", False)) != review:
            row.needs_review = review
            flagged += 1
        elif review:
            row.needs_review = True
    return flagged


def ensure_login_user(db, sub) -> None:
    if getattr(sub, "user", None):
        sub.user.is_active = sub.status == "active"
        return
    username = sub.code
    taken = db.query(User).filter_by(username=username).first()
    if taken:
        username = f"{sub.code}#{sub.id}"
        if db.query(User).filter_by(username=username).first():
            return
        sub.needs_review = True
    db.add(
        User(
            username=username,
            password_hash=generate_password_hash(Config.INITIAL_SUBSIDIARY_PASSWORD),
            role="subsidiary",
            subsidiary_id=sub.id,
            must_change_password=True,
            is_active=sub.status == "active",
        )
    )


def apply_master_record(db, rec, *, create_user=True) -> str:
    code = _norm(rec.get("corporation_code")).upper()
    if not code:
        raise ValueError("code")
    name_ko = _norm(rec.get("corporation_name"))
    name_en = _norm(rec.get("invoice_legal_name"))
    country = _norm(rec.get("country"))
    ko, en = resolve_region(rec.get("region"), "", country=country, country_en="")
    region = ko or _norm(rec.get("region")) or "기타"
    region_en = en or ""
    country_en = COUNTRY_KO_EN.get(country, "")
    try:
        list_no = int(rec.get("number") or 0)
    except (TypeError, ValueError):
        list_no = 0
    sub = find_existing(db, rec)
    created = sub is None
    if created:
        sub = Subsidiary(
            code=code,
            region=region,
            region_en=region_en,
            country=country,
            country_en=country_en,
            name_ko=name_ko or code,
            name_en=name_en or name_ko or code,
        )
        db.add(sub)
    sub.code = code
    sub.list_no = list_no or None
    sub.company = _norm(rec.get("company"))
    sub.region = region
    sub.region_en = region_en
    sub.country = country
    if country_en:
        sub.country_en = country_en
    elif not (sub.country_en or "").strip():
        sub.country_en = ""
    entity_type = resolve_entity_type(rec.get("corporation_type"))
    if entity_type:
        sub.entity_type = entity_type
    sub.name_ko = name_ko or sub.name_ko
    sub.name_en = name_en or sub.name_en
    sub.address_en = _norm(rec.get("address"))
    sub.emails = emails_to_text(rec.get("contact_emails") or [])
    sub.hr_emails = emails_to_text(rec.get("hr_expat_emails") or [])
    active = rec.get("active")
    if active is None:
        active = _norm(rec.get("status")) in {"활성화", "active", "활성"}
    sub.status = "active" if active else "inactive"
    sub.updated_at = utcnow()
    db.flush()
    if create_user:
        ensure_login_user(db, sub)
    return "created" if created else "updated"


def import_master_json(db, path: Path | None = None) -> dict:
    records = load_master_records(path)
    created = updated = errors = 0
    for rec in records:
        try:
            action = apply_master_record(db, rec)
            if action == "created":
                created += 1
            else:
                updated += 1
        except Exception:
            errors += 1
    mark_duplicate_codes(db)
    return {"created": created, "updated": updated, "errors": errors, "total": len(records)}


def freeze_issued_parties(db) -> int:
    count = 0
    rows = db.query(Invoice).filter(Invoice.status != "draft").all()
    for row in rows:
        if (getattr(row, "billed_name", None) or "").strip():
            continue
        snapshot_invoice_party(row)
        count += 1
    return count

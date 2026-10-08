"""Canonical overseas-entity types."""

ENTITY_TYPES = [
    ("대표법인", "Representative Entity"),
    ("생산법인", "Production Entity"),
    ("생산법인(경영권미보유)", "Production Entity (No Controlling Interest)"),
    ("가공센터/물류법인", "Processing Center / Logistics Entity"),
    ("기타법인", "Other Entity"),
]

KO_TO_EN = {ko: en for ko, en in ENTITY_TYPES}
EN_TO_KO = {en.lower(): ko for ko, en in ENTITY_TYPES}

ALIASES = {
    "대표": "대표법인",
    "생산": "생산법인",
    "생산법인(경영권 미보유)": "생산법인(경영권미보유)",
    "경영권미보유": "생산법인(경영권미보유)",
    "가공센터": "가공센터/물류법인",
    "물류법인": "가공센터/물류법인",
    "가공센터/물류": "가공센터/물류법인",
    "기타": "기타법인",
    "representative": "대표법인",
    "representative entity": "대표법인",
    "production": "생산법인",
    "production entity": "생산법인",
    "production entity (no controlling interest)": "생산법인(경영권미보유)",
    "no controlling interest": "생산법인(경영권미보유)",
    "processing center": "가공센터/물류법인",
    "processing center / logistics entity": "가공센터/물류법인",
    "logistics": "가공센터/물류법인",
    "logistics entity": "가공센터/물류법인",
    "other": "기타법인",
    "other entity": "기타법인",
}


def resolve_entity_type(raw) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text in KO_TO_EN:
        return text
    low = text.lower()
    if low in EN_TO_KO:
        return EN_TO_KO[low]
    if text in ALIASES:
        return ALIASES[text]
    if low in ALIASES:
        return ALIASES[low]
    return ""


def entity_type_label(value, lang="ko") -> str:
    ko = resolve_entity_type(value) or (value or "").strip()
    if not ko:
        return ""
    if lang == "en":
        return KO_TO_EN.get(ko, ko)
    return ko

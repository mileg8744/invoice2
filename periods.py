"""Declared half-year workspaces. Not a database table — no schema change."""

from __future__ import annotations

import json

from config import INSTANCE_DIR

PERIODS_PATH = INSTANCE_DIR / "periods.json"


def _valid(year, half):
    try:
        year = int(year)
        half = int(half)
    except (TypeError, ValueError):
        return None
    if year < 2000 or year > 2100 or half not in (1, 2):
        return None
    return year, half


def load_declared_periods():
    if not PERIODS_PATH.exists():
        return set()
    try:
        raw = json.loads(PERIODS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    out = set()
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                pair = _valid(item.get("year"), item.get("half"))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                pair = _valid(item[0], item[1])
            else:
                pair = None
            if pair:
                out.add(pair)
    return out


def save_declared_period(year, half):
    pair = _valid(year, half)
    if not pair:
        return False
    current = load_declared_periods()
    if pair in current:
        return False
    current.add(pair)
    rows = [{"year": y, "half": h} for y, h in sorted(current)]
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    PERIODS_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return True

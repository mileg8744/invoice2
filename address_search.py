"""English address lookup used by HQ and entity profile forms."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

PHOTON_URL = "https://photon.komoot.io/api/"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "PGU-Invoice-Portal/1.0 (education invoice address search)"


def _get_json(url: str, timeout: int = 8):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _clean(parts) -> str:
    seen = []
    for part in parts:
        text = " ".join(str(part or "").split())
        if text and text not in seen:
            seen.append(text)
    return ", ".join(seen)


def format_photon(props: dict) -> str:
    street = _clean(
        [
            props.get("housenumber"),
            props.get("street") or props.get("name"),
        ]
    )
    locality = _clean(
        [
            props.get("district"),
            props.get("city") or props.get("town") or props.get("village") or props.get("county"),
            props.get("state"),
            props.get("postcode"),
        ]
    )
    country = (props.get("country") or "").strip()
    lines = [line for line in (street, locality, country) if line]
    return "\n".join(lines)


def format_nominatim(item: dict) -> str:
    addr = item.get("address") or {}
    street = _clean(
        [
            addr.get("house_number"),
            addr.get("road") or addr.get("pedestrian") or addr.get("neighbourhood"),
        ]
    )
    locality = _clean(
        [
            addr.get("suburb") or addr.get("city_district"),
            addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county"),
            addr.get("state"),
            addr.get("postcode"),
        ]
    )
    country = (addr.get("country") or "").strip()
    lines = [line for line in (street, locality, country) if line]
    if lines:
        return "\n".join(lines)
    return (item.get("display_name") or "").strip()


def search_google_addresses(query: str, country: str, api_key: str) -> list[dict]:
    q = " ".join((query or "").split())
    extra = " ".join((country or "").split())
    if not api_key or len(q) < 3:
        return []
    params = {
        "address": f"{q} {extra}".strip(),
        "key": api_key,
        "language": "en",
    }
    try:
        data = _get_json(
            "https://maps.googleapis.com/maps/api/geocode/json?" + urllib.parse.urlencode(params)
        )
    except Exception:
        return []
    if (data or {}).get("status") not in {"OK", "ZERO_RESULTS"}:
        return []
    items = []
    seen = set()
    for row in data.get("results") or []:
        label = (row.get("formatted_address") or "").strip()
        key = " ".join(label.lower().split())
        if not label or key in seen:
            continue
        seen.add(key)
        comps = row.get("address_components") or []
        detail = _clean([c.get("long_name") for c in comps[:2]])
        items.append({"label": label, "detail": detail})
        if len(items) >= 8:
            break
    return items


def search_english_addresses(query: str, country: str = "", api_key: str = "") -> list[dict]:
    q = " ".join((query or "").split())
    extra = " ".join((country or "").split())
    if len(q) < 3:
        return []
    if api_key:
        google_items = search_google_addresses(q, extra, api_key)
        if google_items:
            return google_items
    items = []
    seen = set()

    def add(label: str, detail: str):
        key = " ".join(label.lower().split())
        if not label or key in seen:
            return
        seen.add(key)
        items.append({"label": label, "detail": detail})

    photon_q = f"{q} {extra}".strip()
    photon_rows = []
    try:
        photon = _get_json(
            PHOTON_URL
            + "?"
            + urllib.parse.urlencode({"q": photon_q, "lang": "en", "limit": 8})
        )
        for feat in photon.get("features") or []:
            props = feat.get("properties") or {}
            label = format_photon(props)
            detail = _clean([props.get("osm_value"), props.get("country"), props.get("postcode")])
            postcode = str(props.get("postcode") or "")
            photon_rows.append((1 if q.isdigit() and postcode == q else 0, label, detail))
        photon_rows.sort(key=lambda row: row[0], reverse=True)
        for _rank, label, detail in photon_rows:
            add(label, detail)
    except Exception:
        pass

    if len(items) >= 5:
        return items[:8]

    params = {
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 8,
        "accept-language": "en",
        "q": photon_q,
    }
    if q.isdigit():
        params["postalcode"] = q
    try:
        rows = _get_json(NOMINATIM_URL + "?" + urllib.parse.urlencode(params))
        for row in rows or []:
            label = format_nominatim(row)
            add(label, row.get("display_name") or "")
    except Exception:
        pass
    return items[:8]

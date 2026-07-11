"""Pure normalization and business-rule helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .constants import CHAIN_WORDS, LOCAL_CATEGORIES, LOCAL_CITIES, PROFILE_DOMAINS


def normalize_phone(phone: str | None) -> str | None:
    if not phone or not phone.strip():
        return None
    phone = phone.strip()
    leading_plus = phone.startswith("+")
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    return f"+{digits}" if leading_plus else digits


def is_likely_croatian_mobile(phone: str | None) -> bool:
    normalized = normalize_phone(phone)
    if not normalized:
        return False
    digits = normalized.lstrip("+")
    return digits.startswith("3859") or digits.startswith("09")


def is_real_website(url: str | None) -> bool:
    if not url or not url.strip():
        return False
    candidate = url.strip().lower()
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = (parsed.netloc or parsed.path).removeprefix("www.")
    whole_url = f"{host}{parsed.path}"
    return not any(domain in whole_url for domain in PROFILE_DOMAINS)


def extract_city(address: str | None) -> str | None:
    if not address:
        return None
    parts = [part.strip() for part in address.split(",") if part.strip()]
    for part in parts:
        match = re.search(r"\b\d{5}\b\s*(.+)", part)
        if match and re.search(r"[A-Za-zÀ-ž]", match.group(1)):
            return match.group(1).strip()
    ignored = {"croatia", "hrvatska", "slovenia", "slovenija", "italy", "italia"}
    for part in reversed(parts):
        cleaned = re.sub(r"\b\d{5}\b", "", part).strip()
        if cleaned.lower() not in ignored and re.search(r"[A-Za-zÀ-ž]", cleaned):
            return cleaned
    return None


def score_likely_small_business(row: dict[str, Any], review_threshold: int) -> bool:
    name = str(row.get("name") or "").lower()
    if any(chain in name for chain in CHAIN_WORDS):
        return False
    if int(row.get("review_count") or 0) >= review_threshold:
        return False
    address = str(row.get("address") or "").lower()
    category = str(row.get("category") or "").lower()
    return any(token in address for token in LOCAL_CITIES) and any(
        token in category for token in LOCAL_CATEGORIES
    )


def slugify_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "manual"

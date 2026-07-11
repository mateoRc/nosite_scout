"""Optional website contact enrichment."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

import requests

from .domain import is_real_website
from .providers import request_headers


EMPTY_CONTACTS = {"email": None, "contact_page_url": None, "facebook_url": None,
                  "instagram_url": None, "whatsapp_url": None}


def first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else None


def absolutize_link(base_url: str, link: str | None) -> str | None:
    if not link:
        return None
    link = html.unescape(link.strip())
    if link.startswith(("http://", "https://")):
        return link
    if link.startswith("//"):
        return f"https:{link}"
    if link.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{link}"
    return link


def fetch_page(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=10, headers=request_headers(), allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException:
        return None
    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type and "text" not in content_type:
        return None
    return response.text[:500_000]


def extract_contact_fields(text: str, base_url: str) -> dict[str, str | None]:
    found = dict(EMPTY_CONTACTS)
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)
    if email_match:
        found["email"] = html.unescape(email_match.group(0))
    patterns = {
        "facebook_url": r'href=["\']([^"\']*facebook\.com[^"\']*)["\']',
        "instagram_url": r'href=["\']([^"\']*instagram\.com[^"\']*)["\']',
        "whatsapp_url": r'href=["\']([^"\']*(?:wa\.me|whatsapp\.com)[^"\']*)["\']',
        "contact_page_url": r'href=["\']([^"\']*(?:kontakt|contact|contatti)[^"\']*)["\']',
    }
    for field, pattern in patterns.items():
        found[field] = absolutize_link(base_url, first_match(pattern, text))
    return found


def candidate_contact_urls(base_url: str, detected_url: str | None) -> list[str]:
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    root = f"{parsed.scheme}://{parsed.netloc}"
    candidates = ([detected_url] if detected_url else []) + [
        f"{root}{path}" for path in ("/contact", "/kontakt", "/contatti", "/contacts", "/kontaktirajte-nas")
    ]
    return list(dict.fromkeys(url for url in candidates if url))


def scrape_website(url: str | None, scrape_contact_pages: bool = True) -> dict[str, str | None]:
    if not is_real_website(url):
        return dict(EMPTY_CONTACTS)
    homepage = fetch_page(url or "")
    if not homepage:
        return dict(EMPTY_CONTACTS)
    found = extract_contact_fields(homepage, url or "")
    if scrape_contact_pages:
        for contact_url in candidate_contact_urls(url or "", found.get("contact_page_url"))[:5]:
            page = fetch_page(contact_url)
            if not page:
                continue
            found["contact_page_url"] = found.get("contact_page_url") or contact_url
            for key, value in extract_contact_fields(page, contact_url).items():
                if value and not found.get(key):
                    found[key] = value
            if found.get("email") and found.get("facebook_url") and found.get("instagram_url"):
                break
    return found

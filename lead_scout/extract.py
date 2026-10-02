from __future__ import annotations

import json
import re
from collections.abc import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import Lead

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.()-]*)?(?:\(?\d{3}\)?[\s.-]*)\d{3}[\s.-]*\d{4}(?!\d)"
)
OWNER_RE = re.compile(
    r"\b(?:owner|founder|co-founder|president)\s*(?:is|:|–|-)?\s*"
    r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})\b"
)
SOCIAL_HOSTS = {
    "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com",
    "linkedin.com", "www.linkedin.com", "x.com", "www.x.com",
}


def _iter_json(value) -> Iterable[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_json(child)


def _clean(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _address(value) -> str:
    if isinstance(value, str):
        return _clean(value)
    if not isinstance(value, dict):
        return ""
    parts = [
        value.get("streetAddress"), value.get("addressLocality"),
        value.get("addressRegion"), value.get("postalCode"), value.get("addressCountry"),
    ]
    return ", ".join(_clean(part) for part in parts if _clean(part))


def _person_name(value) -> str:
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, dict):
        return _clean(value.get("name"))
    if isinstance(value, list):
        for item in value:
            name = _person_name(item)
            if name:
                return name
    return ""


def _business_jsonld(soup: BeautifulSoup) -> list[dict]:
    result = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(tag.string or tag.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        for item in _iter_json(payload):
            kinds = item.get("@type", [])
            if isinstance(kinds, str):
                kinds = [kinds]
            if any(kind in {"Organization", "LocalBusiness", "Store", "MobilePhoneStore"}
                   for kind in kinds):
                result.append(item)
    return result


def extract_lead(html: str, url: str) -> Lead:
    soup = BeautifulSoup(html, "html.parser")
    lead = Lead(website=url, source_type="public_website", source_urls=[url])
    jsonld = _business_jsonld(soup)
    for item in jsonld:
        lead.business_name = lead.business_name or _clean(item.get("name"))
        lead.phone = lead.phone or _clean(item.get("telephone"))
        lead.email = lead.email or _clean(item.get("email")).removeprefix("mailto:")
        lead.address = lead.address or _address(item.get("address"))
        lead.owner_name = lead.owner_name or _person_name(item.get("founder"))
        if lead.business_name:
            lead.evidence.append(f"JSON-LD organization on {url}")

    if not lead.business_name:
        heading = soup.find("h1")
        title = soup.title.string if soup.title and soup.title.string else ""
        lead.business_name = _clean(heading.get_text(" ") if heading else title.split("|")[0])

    if not lead.business_name:
        og_site = soup.find("meta", attrs={"property": "og:site_name"})
        lead.business_name = _clean(og_site.get("content") if og_site else "")

    text = soup.get_text(" ", strip=True)
    if not lead.owner_name:
        match = OWNER_RE.search(text)
        if match:
            lead.owner_name = _clean(match.group(1))
            lead.evidence.append(f"Explicit owner/founder label on {url}")

    if not lead.phone:
        tel = soup.select_one('a[href^="tel:"]')
        if tel:
            lead.phone = _clean(tel.get("href", "")[4:])
        else:
            match = PHONE_RE.search(text)
            lead.phone = _clean(match.group(0)) if match else ""

    if not lead.email:
        mail = soup.select_one('a[href^="mailto:"]')
        candidate = mail.get("href", "")[7:].split("?", 1)[0] if mail else ""
        if not candidate:
            match = EMAIL_RE.search(text)
            candidate = match.group(0) if match else ""
        lead.email = candidate.lower()

    return lead


def candidate_pages(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc.lower()
    preferred = ("contact", "about", "team", "leadership", "company")
    found = []
    for link in soup.find_all("a", href=True):
        absolute = urljoin(base_url, link["href"]).split("#", 1)[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != base_host:
            continue
        label = f"{parsed.path} {link.get_text(' ', strip=True)}".lower()
        if any(word in label for word in preferred) and absolute not in found:
            found.append(absolute)
    return found


def normalized_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    return host.removeprefix("www.")


def is_social_url(url: str) -> bool:
    return urlparse(url).netloc.lower() in SOCIAL_HOSTS

"""Find LinkedIn company URLs via public search engines - no login.

This is the practical alternative to the LinkedIn Organization Lookup
API (which needs an approved LinkedIn app token): public search-engine
results for `site:linkedin.com/company <keywords>`. Search results are
ordinary public pages; we read them politely with MechanicalSoup and
stop on any block. Two engines, DuckDuckGo HTML first, Bing fallback.
"""

from __future__ import annotations

import os
import re
import time
from urllib.parse import quote_plus

import mechanicalsoup

USER_AGENT_DEFAULT = "SignalScout/0.3 (+https://github.com/abaduchanna/SignalScout)"

COMPANY_URL_RE = re.compile(
    r"(?:https?://)?(?:[a-z]{2,5}\.)?linkedin\.com/company/([A-Za-z0-9_%\-]+)",
    re.IGNORECASE,
)

BLOCK_MARKERS = (
    "just a moment", "attention required", "verify you are human",
    "unusual traffic", "captcha",
)


def _dedupe_companies(text: str, limit: int) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in COMPANY_URL_RE.finditer(text or ""):
        slug = match.group(1)
        # skip UI pseudo-slugs that appear in page chrome
        if slug.lower() in {"home", "search", "feed", "login", "pages"}:
            continue
        if slug in seen:
            continue
        seen.add(slug)
        urls.append(f"https://www.linkedin.com/company/{slug}/")
        if len(urls) >= limit:
            break
    return urls


def _read(url: str, browser: mechanicalsoup.StatefulBrowser):
    response = browser.open(url, timeout=25)
    if response.status_code in {401, 403, 429}:
        return None, f"http_{response.status_code}_not_bypassed"
    text = response.soup.get_text(" ", strip=True).lower()[:100_000]
    if any(marker in text for marker in BLOCK_MARKERS):
        return None, "blocked_challenge_not_bypassed"
    return str(response.soup), ""


def find_company_urls_via_search(keywords: str, limit: int = 15,
                                 delay: float = 3.0,
                                 user_agent: str = "") -> tuple[list[str], str]:
    """Return (company_urls, status). No LinkedIn session involved."""
    ua = user_agent or os.getenv("SCOUT_USER_AGENT", USER_AGENT_DEFAULT)
    browser = mechanicalsoup.StatefulBrowser(user_agent=ua, raise_on_404=False)
    query = f"site:linkedin.com/company {keywords}".strip()
    urls: list[str] = []
    status = "no_results"

    for engine, search_url in (
        ("duckduckgo",
         "https://html.duckduckgo.com/html/?q=" + quote_plus(query)),
        ("bing", "https://www.bing.com/search?q=" + quote_plus(query)),
    ):
        time.sleep(max(1.5, delay))
        try:
            html, error = _read(search_url, browser)
        except Exception:
            continue
        if not html:
            status = error or f"{engine}_error"
            continue
        found = _dedupe_companies(html, limit)
        if found:
            urls = found
            status = f"ok_via_{engine}"
            break

    return urls, status

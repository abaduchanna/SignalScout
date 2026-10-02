"""LinkedIn public-company reader via the user's own logged-in browser.

IMPORTANT - how this module is allowed to work:
- The operator logs into LinkedIn THEMSELVES in the SignalScout browser
  window. No credentials, cookies, or session tokens are handled, stored,
  or injected by this code.
- Only publicly viewable company-page data is read (the same page any
  signed-in visitor sees). Nothing behind connection levels is touched.
- Hard rate limits (6-12s between page loads, slow trusted scrolls).
- On authwall / checkpoint / challenge the scraper STOPS immediately -
  no bypass is attempted; the record goes to manual review.

Violating LinkedIn's User Agreement can get an account restricted. Use
your own account, modest volumes, and business-contact purposes only.
"""

from __future__ import annotations

import random
import re
import time
from urllib.parse import quote_plus, urlparse

from ..cdp_browser import TrustedBrowser
from ..extract import OWNER_RE, extract_lead
from ..models import Lead

SEARCH_URL = ("https://www.linkedin.com/search/results/companies/"
              "?keywords={keywords}")


def _company_urls_from_html(html: str) -> list[str]:
    slugs: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r'href="(/company/([A-Za-z0-9_%\-]+)/?)"', html):
        slug = match.group(2)
        if slug in seen:
            continue
        seen.add(slug)
        slugs.append("https://www.linkedin.com/company/" + slug + "/")
    return slugs


def find_company_urls(browser: TrustedBrowser, session: str,
                      keywords: str, max_results: int = 10) -> list[str]:
    """Search LinkedIn companies with trusted typed input, then read the
    public result links."""
    url = SEARCH_URL.format(keywords=quote_plus(keywords))
    report = browser.navigate(session, url)
    if report.status != "ok":
        return []
    browser.slow_read(session, screens=1)
    html = browser.html(session)
    return _company_urls_from_html(html)[: max_results]


def scrape_company(browser: TrustedBrowser, session: str,
                   company_url: str) -> Lead:
    """Read one public LinkedIn company page into a Lead record."""
    lead = Lead(source_type="linkedin_public", source_urls=[company_url],
                linkedin_company_url=company_url)
    report = browser.navigate(session, company_url)
    if report.status == "blocked_challenge":
        lead.status = "blocked_challenge_manual_login"
        return lead
    if report.status != "ok":
        lead.status = report.status
        return lead
    browser.slow_read(session, screens=2)

    # Structured data first (company pages embed an Organization block).
    html = browser.html(session)
    structured = extract_lead(html, company_url)
    lead.business_name = structured.business_name
    lead.website = structured.website if urlparse(
        structured.website).netloc not in ("", "www.linkedin.com") else ""
    lead.phone = structured.phone
    lead.address = structured.address
    lead.evidence.extend(structured.evidence)

    # About-page DOM fallbacks for fields JSON-LD omits.
    js_probe = """
    (() => {
      const pick = (sel) => { const el = document.querySelector(sel);
        return el ? el.textContent.trim() : ""; };
      const out = {
        about: pick('[data-test-id*="about"] , .about-section, #about-us'),
        website: pick('dd a[href^="http"]:not([href*="linkedin.com"])'),
        industry: pick('[data-test-id*="industry"], .industry'),
        hq: pick('[data-test-id*="headquarters"], .hq, .org-location'),
        name: pick('h1'),
      };
      return JSON.stringify(out);
    })()
    """
    try:
        import json as _json
        raw = browser.eval_js(session, js_probe).get("value", "{}")
        probe = _json.loads(raw or "{}")
    except Exception:
        probe = {}
    lead.business_name = lead.business_name or probe.get("name", "")
    lead.website = lead.website or probe.get("website", "")
    lead.address = lead.address or probe.get("hq", "")
    about_text = " ".join(str(probe.get("about", "")).split())
    owner_match = OWNER_RE.search(about_text)
    if owner_match:
        lead.owner_name = owner_match.group(1).strip()
        lead.evidence.append(
            f"Owner/founder named in public About text on {company_url}")

    if not lead.business_name:
        lead.status = "no_public_data"
    return lead


def scrape_companies(browser: TrustedBrowser, session: str,
                     company_urls: list[str], progress=None) -> list[Lead]:
    """Read many company pages with hard rate limits between each."""
    leads: list[Lead] = []
    total = max(1, len(company_urls))
    for index, url in enumerate(company_urls, start=1):
        lead = scrape_company(browser, session, url)
        leads.append(lead)
        if progress:
            progress(index, total, lead)
        time.sleep(random.uniform(6.0, 12.0))   # hard, human-like pacing
    return leads

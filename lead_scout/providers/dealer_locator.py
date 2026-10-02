"""Public dealer-locator form search via MechanicalSoup.

Store/dealer locators that are plain HTML forms (no JavaScript) can be
searched the ordinary way: fill the form, submit, read the public result
pages with BeautifulSoup. This module automates exactly that - it does
NOT execute JavaScript, does NOT bypass Cloudflare/CAPTCHA, and marks
blocked locators for manual review.

For JavaScript-only locators use the CDP path (`mode="cdp"`) which works
in the operator's own browser with trusted clicks - the same boundaries
as everywhere else in SignalScout: no challenge bypass, stop on blocks.
"""

from __future__ import annotations

import os
import time
from urllib.parse import urljoin, urlparse

import mechanicalsoup
from bs4 import BeautifulSoup

from ..extract import extract_lead, is_social_url
from ..models import Lead

BLOCK_MARKERS = (
    "just a moment", "attention required", "cloudflare ray id",
    "verify you are human", "captcha",
)

SEARCH_INPUT_HINTS = ("q", "query", "search", "zip", "postal", "location",
                      "city", "address", "keyword", "find")


class LocatorResult:
    def __init__(self, url: str, status: str = "ok", note: str = ""):
        self.url = url
        self.status = status
        self.note = note
        self.leads: list[Lead] = []


def _form_search_input(form) -> str | None:
    """Pick the most likely search/location input on a locator form."""
    best: tuple[int, str] | None = None
    for field in form.form.select("input"):
        name = (field.get("name") or field.get("id") or "").lower()
        ftype = (field.get("type") or "text").lower()
        if ftype in {"hidden", "submit", "checkbox", "radio", "file"}:
            continue
        score = 0
        if field.get("type") in {"search"}:
            score += 3
        for hint in SEARCH_INPUT_HINTS:
            if hint in name:
                score += 2
                break
        if field.get("required"):
            score += 1
        if best is None or score > best[0]:
            best = (score, field.get("name") or field.get("id") or "")
    return best[1] if best and best[1] else None


def _result_links(soup: BeautifulSoup, base_url: str, limit: int) -> list[str]:
    """Same-domain detail links from a locator results page."""
    host = urlparse(base_url).netloc.lower()
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, anchor["href"]).split("#", 1)[0]
        if urlparse(absolute).netloc.lower() != host or is_social_url(absolute):
            continue
        if absolute.rstrip("/") == base_url.rstrip("/"):
            continue
        if absolute not in found:
            found.append(absolute)
        if len(found) >= limit:
            break
    return found


def search_locator_mechanical(locator_url: str, query: str,
                              max_results: int = 10,
                              delay: float = 2.5,
                              user_agent: str = "") -> LocatorResult:
    """Fill a public locator's search form and read result pages."""
    result = LocatorResult(locator_url)
    browser = mechanicalsoup.StatefulBrowser(
        user_agent=user_agent or os.getenv(
            "SCOUT_USER_AGENT", "SignalScout/0.2 (+lead-scout)"),
        raise_on_404=False)
    try:
        page = browser.open(locator_url, timeout=25)
    except Exception as exc:
        result.status = "request_error"
        result.note = type(exc).__name__
        return result
    if page.status_code in {401, 403, 429}:
        result.status = f"http_{page.status_code}_not_bypassed"
        return result
    marker_hit = any(
        marker in page.soup.get_text(" ", strip=True).lower()[:200_000]
        for marker in BLOCK_MARKERS)
    if marker_hit:
        result.status = "blocked_challenge"
        result.note = "anti-bot challenge - STOPPED, no bypass attempted"
        return result

    form = None
    for candidate in browser.forms():
        if _form_search_input(candidate):
            form = candidate
            break
    if form is None:
        result.status = "no_form_found"
        result.note = "locator has no plain-HTML search form; use the CDP mode"
        return result
    field_name = _form_search_input(form)
    try:
        browser.select_form(form=form)
        browser[field_name] = query
        submitted = browser.submit_selected(timeout=25)
    except Exception as exc:
        result.status = "form_error"
        result.note = f"{type(exc).__name__}: {exc}"
        return result
    if submitted.status_code in {401, 403, 429}:
        result.status = f"http_{submitted.status_code}_not_bypassed"
        return result

    links = _result_links(submitted.soup, locator_url, max_results)
    if not links:
        # The results page itself may already carry the business records.
        lead = extract_lead(str(submitted.soup), locator_url)
        if lead.business_name:
            result.leads.append(lead)
        else:
            result.status = "no_results_parsed"
        return result

    for index, link in enumerate(links, start=1):
        if index > 1:
            time.sleep(max(1.5, delay))
        try:
            detail = browser.open(link, timeout=25)
        except Exception as exc:
            result.note = f"detail fetch skipped: {type(exc).__name__}"
            continue
        if detail.status_code >= 400:
            continue
        lead = extract_lead(detail.text, link)
        lead.source_type = "dealer_locator"
        if lead.business_name:
            result.leads.append(lead)
    return result


def search_locator_cdp(browser, session: str, locator_url: str, query: str,
                       max_results: int = 10) -> LocatorResult:
    """JavaScript locators: search in the operator's own browser using a
    trusted click into the search box, trusted typing, and Enter."""
    from ..cdp_browser import CDPError
    result = LocatorResult(locator_url)
    report = browser.navigate(session, locator_url)
    if report.status != "ok":
        result.status = report.status
        result.note = report.note
        return result
    box_js = browser.element_box_center_js(
        "input[type=search], input[name*=arch i], input[name*=zip i], "
        "input[name*=location i], input[name*=city i], input[type=text]")
    try:
        browser.type_text(session, query, focus_first=box_js)
        browser.press_enter(session)
    except CDPError as exc:
        result.status = "form_error"
        result.note = str(exc)
        return result
    browser.human_pause(2.0, 3.5)
    html = browser.html(session)
    links = _result_links(BeautifulSoup(html, "html.parser"), locator_url,
                          max_results)
    leads: list[Lead] = []
    for link in links[:max_results]:
        detail = browser.navigate(session, link)
        if detail.status != "ok":
            continue
        lead = extract_lead(browser.html(session), link)
        lead.source_type = "dealer_locator"
        if lead.business_name:
            leads.append(lead)
    if not leads:
        lead = extract_lead(html, locator_url)
        if lead.business_name:
            leads.append(lead)
    result.leads = leads
    return result

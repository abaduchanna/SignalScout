from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import mechanicalsoup
import requests

from .extract import candidate_pages, extract_lead, is_social_url
from .models import Lead

BLOCK_MARKERS = (
    "just a moment", "attention required", "cloudflare ray id", "verify you are human",
    "captcha",
)


@dataclass
class FetchResult:
    url: str
    html: str = ""
    status: str = "ok"


class PublicSiteCrawler:
    def __init__(self, delay_seconds: float = 2.0, max_pages: int = 5, user_agent: str = ""):
        self.delay = max(1.0, delay_seconds)
        self.max_pages = max(1, min(max_pages, 10))
        self.user_agent = user_agent or os.getenv(
            "SCOUT_USER_AGENT",
            "WirelessRetailerLeadScout/0.1 (+https://github.com/abaduchanna/Wireless-Retailer-Lead-Scout)",
        )
        self.browser = mechanicalsoup.StatefulBrowser(user_agent=self.user_agent, raise_on_404=False)
        self._robots: dict[str, RobotFileParser] = {}
        self._last_request = 0.0

    def _wait(self):
        remaining = self.delay - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    def _allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            parser = RobotFileParser()
            parser.set_url(f"{origin}/robots.txt")
            try:
                self._wait()
                parser.read()
                self._last_request = time.monotonic()
            except (OSError, URLError):
                # A missing/unreachable robots file is not treated as permission to bypass a block.
                parser = RobotFileParser()
                parser.parse(["User-agent: *", "Disallow: /"])
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(self.user_agent, url)

    def fetch(self, url: str) -> FetchResult:
        if is_social_url(url):
            return FetchResult(url, status="skipped_social_platform")
        if not self._allowed(url):
            return FetchResult(url, status="blocked_by_robots")
        self._wait()
        try:
            response = self.browser.open(url, timeout=25)
        except requests.RequestException as exc:
            return FetchResult(url, status=f"request_error:{type(exc).__name__}")
        finally:
            self._last_request = time.monotonic()
        if response.status_code in {401, 403, 429}:
            return FetchResult(url, status=f"http_{response.status_code}_not_bypassed")
        if response.status_code >= 400:
            return FetchResult(url, status=f"http_{response.status_code}")
        html = response.text
        lower = html[:200_000].lower()
        if any(marker in lower for marker in BLOCK_MARKERS):
            return FetchResult(url, status="anti_bot_challenge_not_bypassed")
        return FetchResult(response.url, html=html)

    def enrich(self, website: str, seed: Lead | None = None) -> Lead:
        lead = seed or Lead(website=website)
        first = self.fetch(website)
        if not first.html:
            lead.status = first.status
            lead.source_urls.append(website)
            return lead
        lead.merge(extract_lead(first.html, first.url))
        pages = candidate_pages(first.html, first.url)[: self.max_pages - 1]
        for page in pages:
            result = self.fetch(page)
            if result.html:
                lead.merge(extract_lead(result.html, result.url))
            elif lead.status == "ok":
                lead.status = result.status
        return lead

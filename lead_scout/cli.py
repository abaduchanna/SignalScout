from __future__ import annotations

import argparse
import json
import os

from .crawler import PublicSiteCrawler
from .markets import sweep_queries
from .providers.dealer_locator import search_locator_mechanical
from .providers.google_places import search_places
from .providers.linkedin_org import lookup_organization
from .storage import dedupe, read_seeds, write_csv, write_xlsx


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lead-scout",
        description="Find and enrich public wireless-retailer business contacts without bypassing access controls.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="Discover businesses via the official Google Places API")
    discover.add_argument("--query", required=True, help='Example: "Total Wireless retailer in Houston TX"')
    discover.add_argument("--out", default="output/leads.csv")
    discover.add_argument("--review-out", default="output/manual-review.csv")
    discover.add_argument("--api-key", default=os.getenv("GOOGLE_PLACES_API_KEY", ""))
    discover.add_argument("--pages", type=int, default=1, choices=(1, 2, 3))
    discover.add_argument("--sweep-usa", action="store_true",
                          help="ALL-USA sweep: one query per state + DC "
                               "(product = query text before ' in ')")
    discover.add_argument("--enrich-websites", action="store_true")
    discover.add_argument("--delay", type=float, default=2.0)

    crawl = sub.add_parser("crawl", help="Enrich user-supplied public business websites")
    crawl.add_argument("--input", required=True, help="CSV with business_name and website columns")
    crawl.add_argument("--out", default="output/enriched-leads.csv")
    crawl.add_argument("--review-out", default="output/manual-review.csv")
    crawl.add_argument("--delay", type=float, default=2.0)
    crawl.add_argument("--max-pages", type=int, default=5)

    linkedin = sub.add_parser("linkedin-org", help="Official LinkedIn Organization Lookup API")
    group = linkedin.add_mutually_exclusive_group(required=True)
    group.add_argument("--vanity")
    group.add_argument("--domain")
    linkedin.add_argument("--token", default=os.getenv("LINKEDIN_ACCESS_TOKEN", ""))
    linkedin.add_argument("--version", default=os.getenv("LINKEDIN_VERSION", "202609"))

    scrape = sub.add_parser("scrape", help="Scrape public business websites (MechanicalSoup/BeautifulSoup)")
    scrape.add_argument("--urls", nargs="*", default=[], help="Business website URLs")
    scrape.add_argument("--input", default="", help="CSV with a website column (seeds)")
    scrape.add_argument("--impersonate", action="store_true",
                        help="Chrome TLS fingerprint via curl_cffi for passively protected sites")
    scrape.add_argument("--out", default="output/scraped-leads.csv")
    scrape.add_argument("--review-out", default="output/manual-review.csv")
    scrape.add_argument("--delay", type=float, default=2.0)
    scrape.add_argument("--max-pages", type=int, default=5)

    locator = sub.add_parser("locator", help="Search a public dealer-locator form (plain HTML)")
    locator.add_argument("--url", required=True)
    locator.add_argument("--query", required=True, help='Example: "Total Wireless" or a ZIP code')
    locator.add_argument("--out", default="output/locator-leads.csv")
    locator.add_argument("--review-out", default="output/manual-review.csv")
    locator.add_argument("--max-results", type=int, default=10)

    sub.add_parser("gui", help="Launch the Studio-style desktop GUI")
    return parser


def _enrich(leads, delay: float, max_pages: int = 5):
    crawler = PublicSiteCrawler(delay_seconds=delay, max_pages=max_pages)
    enriched = []
    for index, lead in enumerate(leads, start=1):
        if lead.website:
            print(f"[{index}/{len(leads)}] {lead.website}")
            enriched.append(crawler.enrich(lead.website, lead))
        else:
            lead.status = "missing_website"
            enriched.append(lead)
    return dedupe(enriched)


def _write_results(out: str, review_out: str, leads) -> None:
    if str(out).lower().endswith(".xlsx"):
        write_xlsx(out, leads)
    else:
        write_csv(out, leads)
    review = [lead for lead in leads if lead.status != "ok"]
    if str(review_out).lower().endswith(".xlsx"):
        write_xlsx(review_out, review)
    else:
        write_csv(review_out, review)
    print(f"Saved {len(leads)} records to {out}")
    print(f"Saved {len(review)} manual-review records to {review_out}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "discover":
        if args.sweep_usa:
            product = args.query.split(" in ")[0].strip() or "Total Wireless retailer"
            queries = sweep_queries(product)
            leads = []
            for index, one_query in enumerate(queries, start=1):
                found = search_places(one_query, args.api_key, args.pages)
                print(f"[{index}/{len(queries)}] {one_query} -> {len(found)}")
                leads.extend(found)
        else:
            leads = search_places(args.query, args.api_key, args.pages)
        if args.enrich_websites:
            leads = _enrich(leads, args.delay)
        _write_results(args.out, args.review_out, dedupe(leads))
        return 0
    if args.command == "crawl":
        leads = _enrich(read_seeds(args.input), args.delay, args.max_pages)
        _write_results(args.out, args.review_out, leads)
        return 0
    if args.command == "linkedin-org":
        result = lookup_organization(
            token=args.token, version=args.version,
            vanity_name=args.vanity or "", email_domain=args.domain or "",
        )
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "scrape":
        urls = list(args.urls)
        if args.input:
            urls.extend(lead.website for lead in read_seeds(args.input)
                        if lead.website)
        crawler = PublicSiteCrawler(delay_seconds=args.delay,
                                    max_pages=args.max_pages,
                                    impersonate=args.impersonate)
        leads = [crawler.enrich(url) for url in urls]
        _write_results(args.out, args.review_out, dedupe(leads))
        return 0
    if args.command == "locator":
        result = search_locator_mechanical(args.url, args.query,
                                           max_results=args.max_results,
                                           delay=args.delay)
        print(f"Locator status: {result.status} {result.note}")
        _write_results(args.out, args.review_out, dedupe(result.leads))
        return 0
    if args.command == "gui":
        from .gui import main as gui_main
        return gui_main()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

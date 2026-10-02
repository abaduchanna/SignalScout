from __future__ import annotations

import argparse
import json
import os

from .crawler import PublicSiteCrawler
from .providers.google_places import search_places
from .providers.linkedin_org import lookup_organization
from .storage import dedupe, read_seeds, write_csv


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
    write_csv(out, leads)
    review = [lead for lead in leads if lead.status != "ok"]
    write_csv(review_out, review)
    print(f"Saved {len(leads)} records to {out}")
    print(f"Saved {len(review)} manual-review records to {review_out}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "discover":
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

from pathlib import Path

from lead_scout.crawler import BLOCK_MARKERS
from lead_scout.extract import candidate_pages, extract_lead, is_social_url


def test_extract_jsonld_business_and_explicit_owner():
    html = Path("tests/fixtures/business.html").read_text(encoding="utf-8")
    lead = extract_lead(html, "https://metrowireless.example/")
    assert lead.business_name == "Metro Wireless LLC"
    assert lead.owner_name == "Jamie Rivera"
    assert lead.phone == "(214) 555-0199"
    assert lead.email == "sales@metrowireless.example"
    assert lead.address == "100 Main St, Dallas, TX, 75201"


def test_candidate_pages_stay_same_origin():
    html = '<a href="/about">About</a><a href="https://evil.example/contact">Contact</a>'
    assert candidate_pages(html, "https://dealer.example/") == ["https://dealer.example/about"]


def test_social_platforms_are_not_crawled():
    assert is_social_url("https://www.linkedin.com/company/example")
    assert is_social_url("https://facebook.com/example")


def test_anti_bot_markers_are_explicit():
    assert "just a moment" in BLOCK_MARKERS
    assert "captcha" in BLOCK_MARKERS

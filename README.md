# Wireless Retailer Lead Scout

Compliance-first lead discovery and website enrichment for wireless-retailer businesses, including targeted searches such as **Total Wireless retailer in Houston, TX**.

It exports business name, explicitly published owner/founder name, public business phone/email, address, website, source URLs, evidence, and review status.

## Boundaries

- No LinkedIn page/profile/search-result or logged-in-session scraping.
- No Cloudflare, CAPTCHA, robots.txt, authentication, rate-limit, or access-control bypass.
- No CDP “trusted click” spoofing or automated challenge completion.
- No inferred private emails, personal phone numbers, or owner identities.
- No automated outreach.

LinkedIn prohibits third-party crawlers and bots that scrape or automate its website. The `linkedin-org` command therefore uses only LinkedIn's official Organization Lookup API and requires an approved token.

## Why MechanicalSoup

[MechanicalSoup](https://github.com/MechanicalSoup/MechanicalSoup) is an MIT-licensed, Requests/BeautifulSoup-based library for ordinary HTML websites. It stores cookies and follows links/forms, but does not execute JavaScript and is not a Cloudflare bypass tool. This project stops when a site returns 401/403/429 or an anti-bot challenge and writes that record to `manual-review.csv`.

## Install

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Windows executable

Download `Wireless-Retailer-Lead-Scout.exe` from the latest GitHub Release. It is a
command-line application, so run it from PowerShell or Command Prompt:

```powershell
.\Wireless-Retailer-Lead-Scout.exe --help
```

To reproduce the executable locally:

```powershell
python -m PyInstaller --clean --noconfirm --onefile `
  --name Wireless-Retailer-Lead-Scout build_entry.py
```

## Targeted discovery with Google Places API

Enable Places API (New), set an API key, and run a narrow city/state query:

```powershell
$env:GOOGLE_PLACES_API_KEY="your-key"
lead-scout discover `
  --query "Total Wireless retailer in Houston TX" `
  --enrich-websites `
  --out output\houston-total-wireless.csv
```

Google Places is optional and billed by Google. Requested fields are deliberately limited. Run separate, narrow queries for each target market.

## Enrich a user-approved seed list

```powershell
lead-scout crawl --input examples\seeds.csv --out output\enriched.csv
```

The crawler checks `robots.txt`, stays on the same business domain, visits at most five likely Contact/About/Team pages, and waits at least two seconds between requests. Owner/founder names require explicit page evidence.

## Manual review queue

Blocked, challenged, missing-website, and other incomplete records are written to `output/manual-review.csv`. Review those URLs yourself in a normal browser. The tool does not import browser cookies, automate challenges, or claim a click is human/trusted.

## LinkedIn Organization Lookup API

For exact company-page lookup only; availability depends on LinkedIn app permissions:

```powershell
$env:LINKEDIN_ACCESS_TOKEN="approved-token"
lead-scout linkedin-org --vanity example-company
lead-scout linkedin-org --domain example.com
```

It never searches or extracts personal LinkedIn profiles.

## Responsible use

- Verify each record before outreach.
- Use public business contacts only for legitimate B2B purposes.
- Follow CAN-SPAM, TCPA, state privacy laws, site terms, and opt-out requests.
- Do not sell or publish personal-contact datasets without a valid legal basis.
- Keep source URLs so records can be corrected or removed.

## References

- LinkedIn prohibited software: https://www.linkedin.com/help/linkedin/answer/a1341387/prohibited-software-and-extensions
- LinkedIn Organization Lookup API: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/organization-lookup-api
- Google Places Text Search (New): https://developers.google.com/maps/documentation/places/web-service/text-search

## License

MIT License. Copyright (c) 2026 **3S Verse**.

Primary contributor: **Abad Umair Channa**.

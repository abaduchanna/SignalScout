# SignalScout — Wireless Retail Lead Scout

**SignalScout** is a compliance-first lead discovery and website
enrichment toolkit for wireless-retailer businesses — built for
targeted prospecting such as **"Total Wireless retailer in Houston,
TX"** (VidaPay dealer development).

It collects publicly published business data: **business name, owner /
founder name (explicitly published), business phone, business email,
business address, website** — with source URLs and evidence notes for
every field, and a manual-review queue for anything blocked or
incomplete.

Developed by www.3SVerse.com · MIT licensed.

## The Studio-style GUI

`lead-scout gui` (or `run_gui.py`) opens a desktop app with the exact
3SVerse Studio design system: the dark-hero palette, the animated
spiral ring (120 s/turn) and floating orb (140 s/turn + 12 px / 13 s
float) from the 3sverse.com hero, tri-gradient accents, stacked logo
header, and the standard brand footer.

| Tab | What it does |
|---|---|
| **Discover** | Official Google Places (New) Text Search — single market OR **ALL-USA sweep** (one narrow query per state + DC), optional website enrichment |
| **Web Scraper** | MechanicalSoup + BeautifulSoup crawling of public business sites; optional browser-fingerprint mode |
| **LinkedIn** | Public company-page reader driven by **CDP trusted input** in your own logged-in browser; find companies via LinkedIn search **or public search engines without login** |
| **Results** | Collected leads, evidence inspector, **Excel (.xlsx)** + CSV export, manual-review export |
| **Settings** | User-Agent, delays, browser profile, Places API key |

## Scraping stack (what each layer is for)

1. **BeautifulSoup** — HTML parsing and field extraction (JSON-LD
   `LocalBusiness` / `Organization`, `tel:` / `mailto:` links,
   owner/founder labels).
2. **MechanicalSoup** — ordinary HTML websites and plain-HTML
   **dealer-locator forms**: fill the search box, submit, read result
   pages. Cookies and forms handled; no JavaScript execution.
3. **curl_cffi fingerprint mode** (optional) — many small-business
   sites sit behind Cloudflare's always-on *passive* fingerprint
   checks that 403 plain Python clients before any page is served.
   Fingerprint mode sends a genuine Chrome TLS/HTTP2 fingerprint so
   the passive checks see a normal browser client. This is
   fingerprint parity, **not** a challenge bypass — active challenges
   (JS / CAPTCHA / Turnstile) still stop the crawler and the record
   goes to manual review.
4. **CDP trusted input** (LinkedIn tab, CDP mode of the locator) —
   drives a real Chrome/Edge window over the Chrome DevTools
   Protocol. Clicks and typing are dispatched through
   `Input.dispatchMouseEvent` / `Input.dispatchKeyEvent`, so pages
   receive `isTrusted=true` input exactly like a human's. Eased mouse
   paths with jitter, press-duration variance, slow reading scrolls,
   and hard 6–12 s page-load pacing. **You log in yourself; the tool
   never touches credentials or cookies.**

### How challenges are handled (the honest way)

The automation runs inside a REAL browser with its real engine, so
Cloudflare's JavaScript-only managed challenges usually clear by
themselves while the page simply loads - the controller waits for
that. When a challenge or CAPTCHA genuinely requires interaction, the
browser window **stays open and YOU solve it**; the controller watches
and **resumes automatically** when the page is clean (up to 3 minutes).
The tool never clicks, scripts, or bypasses a challenge, never touches
CAPTCHAs, and pages that stay blocked go to manual review. This is the
only mode that keeps the operator human-in-the-loop instead of
pretending to be one.

## Boundaries (unchanged, non-negotiable)

- No Cloudflare, CAPTCHA, robots.txt, authentication, rate-limit, or
  access-control bypass. Blocked = recorded to `manual-review.csv`.
- No inferred private emails, personal phone numbers, or owner
  identities — only explicitly published business information.
- No automated outreach. No bulk-harvest tooling.
- **LinkedIn**: third-party scraping is restricted by LinkedIn's User
  Agreement and can get an account restricted. Use your own account,
  modest volumes, business-contact purposes only, at your own risk.
  The `linkedin-org` command uses only LinkedIn's official
  Organization Lookup API with an approved token.

## Install

**Windows (recommended):** download `SignalScout-Setup.exe` from the
[latest release](https://github.com/abaduchanna/SignalScout/releases/latest)
and run it - no Python needed.

**From source:**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## If antivirus flags SignalScout

Endpoint security products (SentinelOne, Defender, ...) used to
false-flag the old one-file builds: a `--onefile` exe extracts its
compiled program DLL (`run_gui.dll`) into `%TEMP%\onefile_*\` on
every launch, and a freshly dropped unsigned DLL in Temp looks
malicious to heuristic engines. **Since v0.3.5 there is no one-file
build at all** - the release is a single NSIS setup that installs the
standalone build once into `%LOCALAPPDATA%\Programs\SignalScout`.
No self-extract step, no Temp payload, nothing to quarantine.

If your endpoint security still asks about the installer: it is
unsigned (no paid code-signing certificate), carries full 3SVerse
version metadata, and its complete source is in this repository.
Allow it once (or ask your IT admin to) and the alert will not
return. To run from source instead (nothing to flag), use the bundled
**`run_gui.bat`** - it creates a local venv, installs dependencies,
and starts the GUI.

## Windows installer

Every `v*` tag ships **one file** on the GitHub Release page:

| File | What it is |
|---|---|
| `SignalScout-Setup.exe` | NSIS setup for the Studio-style desktop **GUI** (Nuitka standalone; brand icon, spiral and orb art bundled; per-user install, Start Menu + Desktop shortcuts, uninstaller) |

Run the setup once; launch SignalScout from the Start Menu or the
desktop shortcut. Uninstall from Windows "Apps & features" or via
`Uninstall SignalScout.exe` in the install folder.

To reproduce the installer locally:

```powershell
python -m nuitka --standalone --output-dir=onedir_build `
  --output-filename=SignalScout.exe --enable-plugin=tk-inter `
  --windows-console-mode=disable run_gui.py
# then
makensis packaging\signal_scout.nsi
```

The build is produced by `.github/workflows/build-windows.yml`
(Nuitka standalone + NSIS, brand icon and background art bundled).

## Targeted discovery with Google Places API

Enable Places API (New), set an API key, and run a narrow city/state
query:

```powershell
$env:GOOGLE_PLACES_API_KEY="your-key"
lead-scout discover `
  --query "Total Wireless retailer in Houston TX" `
  --enrich-websites `
  --out output\houston-total-wireless.csv
```

Google Places is optional and billed by Google. Requested fields are
deliberately limited. Run separate, narrow queries for each target
market.

## Scrape and enrich public business sites

```powershell
lead-scout crawl --input examples\seeds.csv --out output\enriched.csv

# direct URLs, with fingerprint mode for passively protected sites:
lead-scout scrape --urls https://example-dealer.com https://other-dealer.com --impersonate
```

The crawler checks `robots.txt`, stays on the same business domain,
visits at most five likely Contact/About/Team pages, and waits at
least two seconds between requests. Owner/founder names require
explicit page evidence.

## Public dealer-locator form search

```powershell
lead-scout locator --url https://example-brand.com/locator --query "Total Wireless" --query "77002"
```

Plain-HTML locators are searched via MechanicalSoup. JavaScript-only
locators: use the GUI's **Web Scraper → Dealer locator search** with
the **CDP trusted input** mode after starting the browser on the
LinkedIn tab.

## LinkedIn company pages (CDP trusted input)

The **alternative to the Organization Lookup API** (which needs an
approved LinkedIn app token) is built in, with two discovery routes:

1. **Find via Search Engine (no login)** — public DuckDuckGo/Bing
   results for `site:linkedin.com/company <keywords>`; returns company
   URLs without any LinkedIn session. This replaces the Org API for
   company-URL discovery.
2. **Find via LinkedIn Search** — keyword search inside your own
   logged-in browser (nationwide by default; LinkedIn search has no
   geo limit).

Then **Read Companies**: each public company page (+ its /about/ page)
is read for business name, website, headquarters address, published
phone, industry, and any founder/owner line in the public About text.
Records land in **Results** with source URLs and evidence.

1. GUI → **LinkedIn** → **Start Browser** (a real Chrome/Edge window
   opens with its own profile).
2. Log into LinkedIn **yourself** in that window (only needed for
   route 2 and for reading pages).
3. Keywords → find → **Read Companies**.

CLI equivalent: none — deliberately. The GUI keeps the human in the
loop for anything session-based.

## All-USA targeting

Google Places Text Search is geo-narrow, so nationwide coverage is a
**sweep**: one narrow query per state + DC (51 requests, billed by
Google, ~1.5 s apart). In the GUI: Discover → Scope → **ALL-USA**. On
the CLI:

```powershell
lead-scout discover --sweep-usa --query "Total Wireless retailer" --enrich-websites --out .\output\usa.xlsx
```

LinkedIn keyword search is nationwide by default — no sweep needed.

## Excel export

**Results → Export Leads Excel (.xlsx)** writes a branded workbook with
two sheets: **Leads** (every record) and **Manual Review** (blocked /
challenged / incomplete). The CLI writes `.xlsx` whenever the output
filename ends in `.xlsx`.

## Manual review queue

Blocked, challenged, missing-website, and other incomplete records are
written to `output/manual-review.csv`. Review those URLs yourself in a
normal browser. The tool does not import browser cookies from other
sessions, automate challenges, or claim a click is anything other than
what it is: automation operating your own logged-in session at human
pace.

## LinkedIn Organization Lookup API

For exact company-page lookup only; availability depends on LinkedIn
app permissions:

```powershell
$env:LINKEDIN_ACCESS_TOKEN="approved-token"
lead-scout linkedin-org --domain vidapay.com
```

## Development

```powershell
python -m pytest -q          # unit tests
python -m ruff check .       # lint
xvfb-run -a python scripts/test_gui_smoke.py   # GUI smoke (Linux)
```

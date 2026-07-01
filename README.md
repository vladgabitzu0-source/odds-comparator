# ComparaCote.ro

Odds comparison tool for Romanian football betting markets. It scrapes live 1X2
odds from multiple licensed bookmakers, reconciles the same fixture across sites,
and surfaces where one bookmaker is offering measurably better value than the
market consensus.

![ComparaCote.ro screenshot](docs/screenshot.png)

> Screenshot: drop a PNG of the running app at `docs/screenshot.png` (create the
> `docs/` folder). The image tag above will pick it up automatically.

## Overview

Bookmakers price the same match differently, and an occasional mispriced outcome
is genuine value for the bettor. ComparaCote.ro aggregates odds from Romanian
operators, converts every price to an implied probability (`p = 1 / odd`), and
compares each site against the median across sources. When a site's implied
probability sits far enough below the median — i.e. its odds are more generous
than the consensus — that outcome is flagged as value. The result is a single
ranked view of where the best prices are, plus a per-bookmaker "best odds of the
day" board for users who only hold an account with one operator.

## Tech Stack

**Backend:** `Python` · `FastAPI` · `Playwright` · `asyncio` · `APScheduler`

**Frontend:** `React` · `Vite` · `Tailwind CSS`

**Tooling / infra:** `Docker` (Chromium runtime) · residential proxy routing

## Key Technical Challenges

This project's difficulty is in the data acquisition and reconciliation, not the
UI. The notable problems solved:

**1. Bypassing Betano's Cloudflare protection through an authenticated proxy.**
Betano's Cloudflare layer blocks datacenter IPs, so scraping from a server
requires routing through a residential proxy. The catch: headless Chromium on
Linux cannot authenticate to a proxy with a username/password
(`ERR_PROXY_AUTH_UNSUPPORTED`). The solution is a small local asyncio TCP relay
(`_start_forwarding_proxy` / `_make_relay_handler` in `scrapers/betano.py`):
Chromium connects to this local proxy with no auth, and for each connection the
relay opens a socket to the real upstream proxy and injects the
`Proxy-Authorization: Basic <base64>` header only on the upstream side — it is
never propagated back to Chromium. HTTPS is handled via `CONNECT` tunnelling,
reading the upstream response line-by-line to avoid over-reading into the TLS
tunnel and deadlocking. This is paired with a full browser fingerprint (current
Chrome UA, `sec-ch-ua` client hints, `ro-RO` locale, `Europe/Bucharest`
timezone, and a deliberately narrow 1280px viewport that forces the layout the
selectors target) so the request looks like a real Romanian desktop browser.

**2. Cross-source match reconciliation with fuzzy, distinctive-word matching.**
Two sites rarely name a team or competition identically (diacritics, suffixes,
abbreviations, different home/away ordering). Pairing is done by normalizing each
name (diacritic stripping, dropping short and generic tokens), reducing it to its
*distinctive* words — explicitly excluding tier markers like `(R)`, `(F)`,
`U19`–`U23` so they can't create false matches — and accepting a pair only when
at least 50% of those distinctive words align, using bidirectional substring
matching so a short name can't fully match a longer unrelated one. The matcher
also resolves orientation: because sites disagree on which team is "home", it
detects straight vs swapped fixtures and rotates one site's home/away odds before
comparing, so every outcome is compared like-for-like.

**3. Harvest-as-you-scroll for a virtualized DOM.** Superbet's match list is
virtualized — it keeps only ~34 row elements mounted at any moment even though a
full day has ~66 matches, destroying rows as they scroll off-screen. Scrolling to
the bottom and then reading the DOM can never see them all. Instead, the scraper
reads every currently-mounted row at each scroll step in a single
`page.evaluate()` call (atomic, and far faster than many individual locator
calls) and accumulates results into a dictionary keyed by match name —
deduplicating repeat sightings and back-filling each match's competition from the
preceding league header as rows cycle through the viewport.

**4. Tier system to separate signal from noise.** A naive list buries headline
fixtures under reserve, youth, and women's matches, which also produce the
wildest (and least useful) odds divergences. Each fixture is classified as
`main` or `obscure` by scanning its name for markers (`(R)`, `(F)`, `U19`–`U23`,
case-insensitive). The frontend exposes these as separate tabs so the main-league
view stays clean.

## Architecture

```
  Superbet scraper ┐
  (Playwright)     │
                   ├─► analysis/calculator.py ─► FastAPI (api/main.py)  ─► React frontend
  Betano scraper   │   - fuzzy fixture pairing    - in-memory cache       (Vite + Tailwind)
  (Playwright +    │   - implied probability      - APScheduler refresh    GET /api/odds
   asyncio relay)  ┘   - median divergence        - per-source isolation
                                                   - freshness flags
```

Data flow: the two scrapers each return the current 1X2 odds. `calculate_value`
pairs common fixtures, converts odds to implied probabilities, takes the median
across sources, measures each site's divergence from it, and flags outcomes where
a site beats the median by more than ~4%. FastAPI serves the analysed result from
an in-memory cache that is refreshed in the background by APScheduler; each source
is scraped in isolation, so a single failing site degrades to stale-flagged data
rather than taking the API down. The React frontend renders the comparison table
and the per-bookmaker best-odds board.

## Running Locally

**Prerequisites:** Python 3.11+ and Node.js 18+.

Commands below use the Windows `py` launcher. On macOS/Linux use `python3` and
activate the virtual environment with `source .venv/bin/activate`.

### 1. Clone

```bash
git clone https://github.com/vladgabitzu0-source/odds-comparator.git
cd odds-comparator
```

### 2. Backend (FastAPI + Playwright)

```bash
cd backend

# Create and activate a virtual environment
py -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS/Linux

# Install dependencies and the Chromium browser Playwright drives
py -m pip install -r requirements.txt
py -m playwright install chromium

# Run the API (serves at http://localhost:8000)
py -m uvicorn api.main:app --reload
```

On startup the server kicks off the first scrape in the background. A full scrape
of both sites takes roughly 2–3 minutes; until it finishes, `GET /api/odds`
triggers an on-demand scrape, after which results are served instantly from cache
and refreshed automatically. Proxy environment variables are optional and only
needed when a site blocks direct connections — see `.env.example`.

### 3. Frontend (React + Vite)

In a second terminal:

```bash
cd frontend
npm install

# Optional: point the frontend at your local backend instead of the hosted API
cp .env.example .env              # then it targets http://localhost:8000

npm run dev
```

The dev server runs at http://localhost:5173.

## Configuration

Secrets and per-environment settings are read from environment variables, never
hardcoded. Copy `.env.example` to `.env` (gitignored) and fill in values as
needed:

- `PROXY_SERVER`, `PROXY_USERNAME`, `PROXY_PASSWORD` (backend) — optional
  residential proxy for scraping behind Cloudflare. Unset means a direct
  connection.
- `VITE_API_URL` (frontend) — base URL of the backend API.

## Project Structure

```
odds-comparator/
├── backend/
│   ├── scrapers/        # One module per bookmaker (Playwright)
│   ├── analysis/        # Fixture pairing + implied-probability divergence
│   ├── api/             # FastAPI app, caching, scheduled refresh
│   ├── check_overlap.py # Team-name normalization / tokenization helpers
│   └── requirements.txt
└── frontend/
    └── src/             # React + Vite + Tailwind UI
```

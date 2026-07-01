"""
Superbet scraper — grabs football 1X2 odds from superbet.ro.

1X2 market explained (for the analysis step later):
    home  -> "1" : home team wins
    draw  -> "X" : the match is a draw
    away  -> "2" : away team wins

We use Playwright in ASYNC mode. Async lets the browser wait for the page's
JavaScript to load the odds without blocking, which is exactly what betting
sites need (their odds are rendered by JS, not in the raw HTML).
"""

import asyncio
import json
import sys
from datetime import datetime

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# The page we scrape. "day=astazi" = "today" in Romanian.
URL = "https://superbet.ro/pariuri-sportive/fotbal?day=astazi"

# Site origin. The per-match hrefs (/cote/fotbal/<slug>-<id>) are usually already
# absolute, but this prefixes any that come through relative so the frontend
# always gets a full URL.
BASE_URL = "https://superbet.ro"

# Superbet marks important elements with "e2e-" test classes. These are far
# more stable than the random obfuscated CSS classes around them, so we target
# them on purpose (see CLAUDE.md: prefer stable selectors).
ODD_VALUE_SELECTOR = ".e2e-odd-value"      # a single odd number, e.g. "3.70"

# Container that wraps ONE match: its two teams + its three odds. Reading odds
# per-row (instead of from a flat page-wide list) keeps each match self-contained,
# so a stray promo/special row can't knock teams and odds out of sync.
# Confirmed from the live page DOM: ".event__sections" turned out to wrap ONLY
# the team names (0 odds inside it) — the odds sit in a sibling element. The
# ".e2e-event-row" ancestor is the level that contains all of team1 + team2 +
# the 3 odds, and it's a stable e2e- test class (preferred, per CLAUDE.md).
EVENT_SELECTOR = ".e2e-event-row"

# The home/away team names inside an event container. Superbet uses distinct
# test classes for each side, so we read them separately (no guessing order).
HOME_TEAM_SELECTOR = ".e2e-event-team1-name"
AWAY_TEAM_SELECTOR = ".e2e-event-team2-name"

# Per-league section header that precedes each group of matches. The stable e2e
# class is "e2e-competition-header" (distinct from the all-caps page banners like
# "COMPETIȚII DE TOP", which are level-one section titles we do NOT want). The
# league name itself ("Islanda - Lengjudeildin") sits in a child text span.
COMPETITION_HEADER_SELECTOR = ".e2e-competition-header"
COMPETITION_NAME_SELECTOR = ".sds-section-title__title-text"


async def scrape_superbet():
    """Open Superbet, read today's football 1X2 odds, return a list of dicts."""
    results = []

    # async_playwright() manages the browser's lifetime. "async with" makes
    # sure the browser is always closed, even if something throws.
    async with async_playwright() as p:
        # headless=True -> no visible window. Flip to False to watch it work
        # while you're debugging selectors.
        # The args are required to run Chromium inside a Docker container on Linux
        # (e.g. Railway): containers have no sandbox/GPU and a tiny /dev/shm, so
        # without these flags the browser hangs and the scrape times out.
        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-first-run",
            "--no-zygote",
        ]
        # --single-process is needed in the Railway container but CRASHES headless
        # Chromium on navigation on Windows, so we only add it on Linux. This keeps
        # both the Railway deploy and local Windows dev working.
        if sys.platform == "linux":
            launch_args.append("--single-process")
        browser = await p.chromium.launch(headless=True, args=launch_args)
        # A taller viewport means each scroll step covers more page and gives the
        # lazy-loader a bigger window to fill, which loads rows more reliably.
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Go to the page and wait until the DOM is parsed. We don't use
        # "networkidle" here: betting sites stream live odds updates constantly,
        # so the network never goes idle and networkidle would always time out.
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # Step 2: wait for the odds to actually appear in the DOM before we start
        # scrolling. If the page is slow and this times out, we don't give up —
        # we fall back to a fixed 5s pause and head into the scroll loop anyway,
        # which keeps reading rows as they lazy-load. timeouts are in ms.
        try:
            await page.wait_for_selector(ODD_VALUE_SELECTOR, timeout=60_000)
        except PlaywrightTimeoutError:
            print("DEBUG: odds selector didn't appear in 60s; "
                  "waiting 5s and scrolling anyway")
            await page.wait_for_timeout(5000)

        # Step 2b: HARVEST-AS-YOU-SCROLL.
        #
        # Superbet's match list is VIRTUALIZED: as you scroll, the page destroys
        # rows that scroll off-screen to save memory. We confirmed this against
        # the live page — there are never more than ~34 .e2e-event-row elements
        # in the DOM at once, even though a full day has ~66 matches. So the old
        # approach (scroll to the bottom, THEN read every row) can NEVER see them
        # all: the early matches are already gone by the time we reach the end.
        #
        # The fix: read the rows that are CURRENTLY in the DOM at every scroll
        # step and accumulate them into a dict keyed by match name, so each match
        # is captured while it's briefly on-screen and de-duplicated if we see it
        # more than once. We keep scrolling until we hit the bottom and the page
        # stops growing.
        #
        # One timestamp for this whole scrape run, in ISO format.
        timestamp = datetime.now().isoformat(timespec="seconds")

        # match name -> result dict. A dict de-dupes automatically: re-seeing a
        # match (because it lingered on-screen across steps) just overwrites its
        # own identical entry.
        matches_by_name = {}

        # This JS runs in the page and returns, for every row CURRENTLY in the
        # DOM, its two team names and three odds as plain strings. Doing the read
        # in one page.evaluate() (instead of many Playwright locator calls) is
        # both faster and atomic — the DOM can't shift mid-read.
        harvest_js = """
        () => {
            // COMPETITION MAPPING. Each match row follows its league header
            // (.e2e-competition-header) in document order rather than nesting
            // inside it, so we walk headers and rows together and tag each row
            // with the most recent preceding header's name ("Country - League").
            // Featured/top-events rows that have no league header above them stay
            // null (they get filled in when the same match reappears in its league
            // section, since we dedupe by match name).
            const ordered = document.querySelectorAll(
                '.e2e-competition-header, .e2e-event-row');
            let currentComp = null;
            const rowComp = new Map();
            ordered.forEach(n => {
                if (n.matches('.e2e-competition-header')) {
                    const t = n.querySelector('.sds-section-title__title-text');
                    currentComp = (t ? t.textContent : n.textContent)
                                      .replace(/\\s+/g, ' ').trim();
                } else {
                    rowComp.set(n, currentComp);
                }
            });

            return Array.from(document.querySelectorAll('.e2e-event-row')).map(row => {
                const home = row.querySelector('.e2e-event-team1-name');
                const away = row.querySelector('.e2e-event-team2-name');
                const odds = Array.from(row.querySelectorAll('.e2e-odd-value'))
                                  .map(o => o.textContent.trim());
                // Keep only clean 1X2 rows: both teams present and exactly 3 odds.
                if (!home || !away || odds.length !== 3) return null;
                // Per-match deep link. Confirmed against the live DOM: the
                // .e2e-event-row element is ITSELF the <a>, with an absolute href
                // to /cote/fotbal/<slug>-<id>. We still fall back to a descendant
                // or ancestor anchor in case the markup differs elsewhere.
                const link = (row.matches('a[href]') && row)
                          || row.querySelector('a[href]')
                          || row.closest('a[href]');
                const href = link ? (link.getAttribute('href') || '') : '';
                return {home: home.textContent.trim(),
                        away: away.textContent.trim(),
                        odds,
                        href,
                        competition: rowComp.get(row) || null};
            }).filter(Boolean);
        }
        """

        async def harvest_visible():
            """Read every on-screen row now and merge it into matches_by_name."""
            for row in await page.evaluate(harvest_js):
                name = f"{row['home']} vs {row['away']}"
                # Keep a competition we already found if this sighting lacks one
                # (the virtualized list may have dropped its header from the DOM,
                # or this is the featured-carousel copy of the match).
                competition = row.get("competition")
                existing = matches_by_name.get(name)
                if existing and not competition:
                    competition = existing["competition"]

                # Same idea for the deep link: a virtualized re-sighting (or the
                # featured-carousel copy) may not carry an href, so keep the one
                # we already captured for this match.
                url = _absolute_url(row.get("href"))
                if existing and not url:
                    url = existing["url"]

                matches_by_name[name] = {
                    "match": name,
                    "home": _to_float(row["odds"][0]),
                    "draw": _to_float(row["odds"][1]),
                    "away": _to_float(row["odds"][2]),
                    "competition": competition,
                    # Absolute deep link to this match's page (or None if the row
                    # never exposed one).
                    "url": url,
                    "source": "superbet",
                    "timestamp": timestamp,
                }

        SCROLL_STEP_PX = 800   # one good-sized step; small steps loaded fewer rows
        STEP_PAUSE_MS = 500    # let the next batch render before we read
        MAX_STEPS = 200        # safety cap so we can never loop forever

        last_scroll_height = 0
        for _ in range(MAX_STEPS):
            # Read whatever is on-screen right now, before scrolling further.
            await harvest_visible()

            await page.evaluate(f"window.scrollBy(0, {SCROLL_STEP_PX})")
            await page.wait_for_timeout(STEP_PAUSE_MS)

            # Are we at the bottom AND has the page stopped growing taller? The
            # page keeps getting taller as new sections lazy-load, so we only
            # stop once we're at the bottom and the height is stable.
            scroll_height = await page.evaluate("document.documentElement.scrollHeight")
            at_bottom = await page.evaluate(
                "window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 5"
            )
            if at_bottom and scroll_height == last_scroll_height:
                break
            last_scroll_height = scroll_height

        # Final harvest after the last scroll, so matches revealed by the very
        # last step aren't missed.
        await harvest_visible()

        results = list(matches_by_name.values())

        # Debug summary: unique matches we managed to harvest across all steps.
        print(f"DEBUG: harvested {len(results)} unique matches")

        await browser.close()

    return results


def _to_float(text):
    """Turn an odd string into a float. Handles comma decimals ('3,70')."""
    return float(text.strip().replace(",", "."))


def _absolute_url(href):
    """Turn a per-match href into an absolute URL, or None if there's no href.

    The page exposes relative paths like "/pariuri-sportive/..."; we prepend the
    site origin. Anything that already starts with "http" is returned unchanged.
    """
    if not href:
        return None
    if href.startswith("http"):
        return href
    return BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"


# Step 6: test block — only runs when you do `py superbet.py` directly,
# NOT when this file is imported by the rest of the app.
if __name__ == "__main__":
    # asyncio.run() starts the event loop and runs our async function.
    matches = asyncio.run(scrape_superbet())

    # Step 5: print as nicely formatted JSON. ensure_ascii=False keeps
    # Romanian characters (ă, â, ț...) readable instead of escaped.
    print(json.dumps(matches, indent=2, ensure_ascii=False))
    print(f"\nScraped {len(matches)} matches.")

"""
sample_data.py — a SYNTHETIC "second source" for the public demo build.

Why this file exists
--------------------
The whole point of the app is comparing odds ACROSS sources: for each outcome it
takes the median implied probability across the sites and flags the site whose
odds sit noticeably above it. With a single real scraper (Superbet) there is
nothing to compare against, so the analysis would always come back empty.

In the private build the second source was a live scraper. In this public
portfolio copy that scraper has been removed on purpose, so we synthesise a
stand-in instead. It is NOT a real bookmaker and is labelled "Sample data"
everywhere in the UI.

How the demo data is produced
-----------------------------
It is a MIRROR of whatever Superbet returned THIS run, not an independent
hardcoded list. scrape_sample() takes Superbet's matches and copies every
fixture, nudging each of the three odds (home/draw/away) independently by a
small random percentage (see _MIN_NUDGE / _MAX_NUDGE). That guarantees:

  * 100% fixture overlap every run — the same matches always exist on both
    sources, so the fuzzy pairing + median-divergence logic always has real work
    and produces non-empty output for anyone who clones and runs the app; and
  * different numbers — the nudge means the mirror is never identical to
    Superbet, so there is a genuine divergence to measure and flag.

Obscure tier: the "Restul ligilor" tab only has content when Superbet's own list
contains reserve/women/youth fixtures ((R)/(F)/U19–U23). On a quiet day it might
not, so ensure_obscure_examples() tops the base list up with 1–2 clearly
fictional obscure fixtures BEFORE mirroring, so both tabs reliably populate.

Match shape
-----------
Each dict matches what the live scraper returns:
    match        -> "Home vs Away" (must contain " vs " — the analysis splits on it)
    home/draw/away -> the 1X2 odds as floats
    competition  -> league label shown under the match name
    url          -> per-match deep link, or None to fall back to a landing page
    source       -> which side of the comparison this row belongs to
    timestamp    -> ISO time this data was produced
"""

import random
from datetime import datetime

# This source's key, used everywhere else (calculator BOOKMAKER_NAMES, the
# results dict, the frontend). Kept in one place so it's easy to see.
SOURCE = "sample"

# Tier markers that make a fixture "obscure" (reserves / women's / youth). Kept
# in sync with OBSCURE_MARKERS in analysis/calculator.py; duplicated here rather
# than imported to avoid a circular import (calculator imports this module).
OBSCURE_MARKERS = ("(r)", "(f)", "u19", "u20", "u21", "u22", "u23")

# Each mirrored odd is nudged by a random magnitude in this band, with a random
# sign — e.g. anywhere in ±3%…±8%. Big enough that the divergence maths has
# something to chew on, small enough that the prices stay plausible.
_MIN_NUDGE = 0.03
_MAX_NUDGE = 0.08

# A nudge must never push an odd to an impossible value (an odd of 1.0 pays
# nothing back), so we clamp to just above 1.0.
_MIN_ODD = 1.01

# We want at least this many obscure-tier fixtures in play so "Restul ligilor"
# isn't empty. If Superbet's live list has fewer, we top up from _OBSCURE_FALLBACK.
_MIN_OBSCURE = 2

# Fabricated obscure-tier fixtures used ONLY as a fallback when Superbet's live
# list is short on reserve/women/youth games. Deliberately fictional names (with
# "demo"/"exemplu") so they can't be mistaken for a real market. These are added
# to the Superbet-side base and then mirrored, so they appear on both sides of the
# comparison and land in the obscure tab.
_OBSCURE_FALLBACK = [
    {"match": "AC Demo (R) vs FC Exemplu (R)",
     "home": 2.35, "draw": 3.30, "away": 2.85,
     "competition": "Sample data · ligă de rezerve"},
    {"match": "Demo United (F) vs Exemplu City (F)",
     "home": 2.10, "draw": 3.45, "away": 3.15,
     "competition": "Sample data · ligă feminină"},
]


def _is_obscure(match_name):
    """True if a fixture name carries an obscure-tier marker ((R)/(F)/U19–U23)."""
    name = match_name.lower()
    return any(marker in name for marker in OBSCURE_MARKERS)


def _nudge(odd):
    """Return an odd shifted by a random ±_MIN_NUDGE…±_MAX_NUDGE percentage.

    Sign is random each call, so some outcomes come out more generous on the demo
    source and some less — exactly what makes the median-divergence flag fire on a
    realistic subset of rows rather than all or none. Rounded to 2 decimals like a
    real market, and clamped so it can never drop to an unplayable value.
    """
    magnitude = random.uniform(_MIN_NUDGE, _MAX_NUDGE)
    sign = random.choice((-1, 1))
    return max(_MIN_ODD, round(odd * (1 + sign * magnitude), 2))


def ensure_obscure_examples(superbet_matches):
    """Return the Superbet matches, topped up with fabricated obscure fixtures.

    If the live list already has at least _MIN_OBSCURE obscure-tier fixtures it is
    returned unchanged (as a fresh list). Otherwise we append enough fixtures from
    _OBSCURE_FALLBACK to reach the target, so the "Restul ligilor" tab always has
    content. The fillers must live on the Superbet SIDE (the comparison's tier is
    read from the Superbet match name), so this runs before mirroring — the
    mirror in scrape_sample then produces their demo-source counterparts.

    Never mutates the input list.
    """
    have = sum(1 for m in superbet_matches if _is_obscure(m["match"]))
    needed = max(0, _MIN_OBSCURE - have)
    topped_up = list(superbet_matches)
    if needed == 0:
        return topped_up

    now = datetime.now().isoformat(timespec="seconds")
    for base in _OBSCURE_FALLBACK[:needed]:
        topped_up.append({
            "match": base["match"],
            "home": base["home"],
            "draw": base["draw"],
            "away": base["away"],
            "competition": base["competition"],
            "url": None,
            # These sit on the Superbet side of the demo comparison.
            "source": "superbet",
            "timestamp": now,
        })
    return topped_up


async def scrape_sample(superbet_matches):
    """Build the synthetic demo source by mirroring THIS run's Superbet odds.

    Every fixture Superbet returned is copied with each of its three odds nudged a
    few percent (see _nudge), so the demo source always covers exactly the same
    fixtures (100% overlap) but never with identical numbers — giving the
    median-divergence value logic real work on every run.

    Async so it drops straight into the isolated scrape orchestration alongside
    the real scraper. Expects the Superbet list to already have been passed
    through ensure_obscure_examples() (the caller does this), so any fallback
    obscure fixtures get mirrored here too.
    """
    timestamp = datetime.now().isoformat(timespec="seconds")
    return [
        {
            "match": m["match"],
            "home": _nudge(m["home"]),
            "draw": _nudge(m["draw"]),
            "away": _nudge(m["away"]),
            "competition": m.get("competition"),
            # No real per-match page for demo data — None makes the analysis fall
            # back to this source's landing link (see AFFILIATE_LINKS in
            # calculator.py).
            "url": None,
            "source": SOURCE,
            "timestamp": timestamp,
        }
        for m in superbet_matches
    ]


# Lets you eyeball the demo mirror with `py scrapers/sample_data.py` from
# backend/. Uses a tiny fake Superbet list so it runs without launching a browser.
if __name__ == "__main__":
    import asyncio
    import json

    fake_superbet = [
        {"match": "FCSB vs Universitatea Craiova", "home": 2.05, "draw": 3.30,
         "away": 3.70, "competition": "România - Superliga", "url": None},
        {"match": "Real Madrid vs Sevilla", "home": 1.55, "draw": 4.20,
         "away": 6.00, "competition": "Spania - La Liga", "url": None},
    ]
    base = ensure_obscure_examples(fake_superbet)
    matches = asyncio.run(scrape_sample(base))
    print(json.dumps(matches, indent=2, ensure_ascii=False))
    print(f"\n{len(matches)} sample matches mirrored from {len(fake_superbet)} "
          f"Superbet fixtures (+{len(base) - len(fake_superbet)} obscure fillers).")

"""
calculator.py — the core "value finder" for the odds comparator.

What it does, end to end:
  1. Gathers 1X2 odds from every source: the live Superbet scraper plus the
     static "Sample data" sample source (scrapers/sample_data.py). The public
     build ships one real scraper, so the sample source stands in as the second
     set of odds to compare against — see that file for the why.
  2. Pairs up the SAME fixture across the sources (fuzzy team-name matching,
     reused from check_overlap.py).
  3. Converts every odd to an implied probability: p = 1 / odd.
  4. For each outcome (home / draw / away) it takes the MEDIAN probability across
     the sites, measures how far each site sits from that median, and flags a
     site as a "value" bet when its odds are noticeably more generous.

Why implied probability?
  An odd of 2.00 means the bookie thinks the outcome happens ~50% of the time
  (1 / 2.00 = 0.50). A HIGHER odd = LOWER implied probability = bigger payout for
  you. So when one site's implied probability sits well BELOW the median, that
  site is offering better-than-average odds — a potential value bet.

About "median" with two sources:
  The median of two numbers is just their average, so the two sources'
  divergences come out as mirror images (one positive, one negative). The
  architecture is kept median-based on purpose, so adding a 3rd/4th source later
  "just works".

Run it from the backend/ folder:
    cd backend && py analysis/calculator.py
"""

import asyncio
import os
import statistics
import sys

# Make the backend/ folder importable no matter how this file is launched, so the
# "scrapers" package and check_overlap.py (which both live in backend/) can be
# imported. __file__ is backend/analysis/calculator.py, so two dirnames up is
# backend/.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from scrapers.superbet import scrape_superbet
# Synthetic, clearly-labelled demo source. It replaces the removed live second
# scraper: instead of scraping, it MIRRORS Superbet's odds each run (with a small
# random nudge) so the cross-source comparison always has something to compare
# against. ensure_obscure_examples tops the base list up with obscure fixtures.
from scrapers.sample_data import scrape_sample, ensure_obscure_examples

# Reuse the team-name parsing/tokenizing helpers from check_overlap.py. We do
# NOT reuse its _teams_match: we define a stricter one below (see _teams_match).
from check_overlap import _team_names, _significant_words


# A site is flagged as "value" when its implied probability is more than this far
# BELOW the median (i.e. its divergence is bigger than this). 0.04 = 4%.
VALUE_THRESHOLD = 0.04

# Sanity cap on odds. If ANY of a pair's 6 odds is above this, we skip the whole
# pair: such fixtures are extreme mismatches where the sites disagree wildly and
# the "value" numbers stop being meaningful.
MAX_SANE_ODD = 10.0

# The three 1X2 outcomes, in the order we report them everywhere.
OUTCOMES = ("home", "draw", "away")

# Markers that tag a fixture as lower-profile (reserves, women's, youth age
# groups). A match whose name contains any of these is classed "obscure"; matches
# without them are "main". Compared case-insensitively.
OBSCURE_MARKERS = ("(r)", "(f)", "u19", "u20", "u21", "u22", "u23")


def _tier(match_name):
    """Classify a fixture as "main" or "obscure" from its name.

    "obscure" if either team is a reserves/women's/youth side (name contains one
    of OBSCURE_MARKERS), otherwise "main". Used to separate headline fixtures from
    the lower-league noise.
    """
    name = match_name.lower()
    return "obscure" if any(m in name for m in OBSCURE_MARKERS) else "main"


# Two team names count as the SAME team only if they share enough of their
# distinctive words. The old rule (any single shared word) produced false pairs
# like "Charlotte Eagles (F)" matching an unrelated Irish women's side just
# because both names contain the "(F)" women's marker. So we now (a) ignore those
# tier markers when comparing names and (b) require at least this fraction of the
# distinctive words to line up.
TEAM_MATCH_THRESHOLD = 0.5


def _distinctive_words(team):
    """Significant words of a team name with tier markers ((F), (R), U19…) removed.

    _significant_words already drops short and generic tokens; on top of that we
    drop OBSCURE_MARKERS, which describe the KIND of team (women's, reserves,
    youth) rather than WHICH team — so they must never count as a shared name.
    """
    return [w for w in _significant_words(team) if w not in OBSCURE_MARKERS]


def _count_shared(words_a, words_b):
    """How many words in words_a have an equal-or-substring match in words_b.

    Substring matching (e.g. "djurgarden" in "djurgardens") absorbs the small
    spelling differences between the two sites.
    """
    return sum(1 for a in words_a
               if any(a == b or a in b or b in a for b in words_b))


def _teams_match(a, b):
    """Do two (already normalized) team names refer to the same team?

    We score the overlap as: shared distinctive words / the larger name's
    distinctive-word count. A pair is accepted only if BOTH names have
    distinctive words, they share at least one, and the score is at least
    TEAM_MATCH_THRESHOLD (50%). Using a FRACTION instead of "any one word in
    common" is what rejects coincidental single-word hits like the "(F)" case.
    """
    wa = _distinctive_words(a)
    wb = _distinctive_words(b)
    if not wa or not wb:
        return False

    # Count in both directions and take the smaller, so a short name can't score
    # 100% just by being a substring of a longer, unrelated name.
    shared = min(_count_shared(wa, wb), _count_shared(wb, wa))
    if shared == 0:
        return False

    return shared / max(len(wa), len(wb)) >= TEAM_MATCH_THRESHOLD


def _orientation(sb_name, sp_name):
    """How do these two fixture names line up? Returns "straight", "swapped",
    or None if they aren't the same fixture at all.

    The sources don't always agree on which team is "home", so a match can line
    up either straight (home<->home, away<->away) or swapped (home<->away). We
    need to know which, because if it's swapped we must swap the sample source's
    home/away odds before comparing — otherwise we'd compare a home-win odd
    against an away-win odd and get nonsense.
    """
    sb_home, sb_away = _team_names(sb_name)
    sp_home, sp_away = _team_names(sp_name)
    if _teams_match(sb_home, sp_home) and _teams_match(sb_away, sp_away):
        return "straight"
    if _teams_match(sb_home, sp_away) and _teams_match(sb_away, sp_home):
        return "swapped"
    return None


def _oriented_sample_odds(sample_match, orientation):
    """Return the sample source's {home, draw, away} odds rotated to Superbet's view.

    If the fixture was listed with the teams swapped on the other source, its
    "home" odd is really for the team Superbet calls "away", so we swap them back.
    The draw odd is the same either way.
    """
    if orientation == "swapped":
        return {
            "home": sample_match["away"],
            "draw": sample_match["draw"],
            "away": sample_match["home"],
        }
    return {
        "home": sample_match["home"],
        "draw": sample_match["draw"],
        "away": sample_match["away"],
    }


def _analyse_outcome(superbet_odd, sample_odd):
    """Compare one outcome's odds across the two sources and return its analysis.

    Result shape:
        {"median_prob", "superbet_div", "sample_div", "best_site", "is_value"}
    """
    # Step 3: odds -> implied probabilities.
    sb_prob = 1 / superbet_odd
    sp_prob = 1 / sample_odd

    # Step 4: median implied probability across the sources.
    median_prob = statistics.median([sb_prob, sp_prob])

    # Step 5: how far each source sits from the median. A POSITIVE divergence
    # means its probability is below the median, i.e. its odds are more generous.
    sb_div = median_prob - sb_prob
    sp_div = median_prob - sp_prob

    # The "best" source for this outcome is the one offering the HIGHEST odd —
    # i.e. the LOWEST implied probability — because that's the most generous
    # payout for you. We pick it straight from the odds so the intent is
    # unmistakable. (With two sources this is the same one as the largest positive
    # divergence, but stating it in terms of odds avoids any sign confusion.)
    # Ties go to Superbet.
    best_site = "superbet" if superbet_odd >= sample_odd else "sample"
    best_div = sb_div if best_site == "superbet" else sp_div

    # Step 6: it's a value bet if the best source beats the median by > 4%.
    is_value = best_div > VALUE_THRESHOLD

    return {
        "median_prob": round(median_prob, 3),
        "superbet_div": round(sb_div, 3),
        "sample_div": round(sp_div, 3),
        "best_site": best_site,
        "is_value": is_value,
    }


def calculate_value(superbet_matches, sample_matches):
    """Pair up fixtures across the two sources and analyse each one.

    Pure function (no scraping) so it's easy to test with hand-made data. Returns
    the list of result dicts described in the module docstring.
    """
    results = []

    for sb in superbet_matches:
        # Find the first sample-source fixture that is the same match as this
        # Superbet one, remembering whether the teams were listed swapped.
        for sp in sample_matches:
            orientation = _orientation(sb["match"], sp["match"])
            if orientation is None:
                continue

            # Sample-source odds rotated into Superbet's home/draw/away
            # orientation, so every outcome compares like-for-like.
            sample_odds = _oriented_sample_odds(sp, orientation)
            superbet_odds = {
                "home": sb["home"],
                "draw": sb["draw"],
                "away": sb["away"],
            }

            # Sanity filter: skip lopsided fixtures where any of the 6 odds is
            # above MAX_SANE_ODD. Very high odds (heavy underdogs, obscure
            # reserve/youth games) are where the two sources disagree most, which
            # produces huge but meaningless "value" divergences. Dropping them
            # keeps the results focused on realistic, bettable matches.
            all_odds = list(superbet_odds.values()) + list(sample_odds.values())
            if any(odd > MAX_SANE_ODD for odd in all_odds):
                break  # not a usable pair; move on to the next Superbet match

            analysis = {
                outcome: _analyse_outcome(superbet_odds[outcome], sample_odds[outcome])
                for outcome in OUTCOMES
            }

            # Competition/league name. We prefer Superbet's (the match name also
            # comes from Superbet), falling back to the sample source's if
            # Superbet didn't capture one. .get() keeps this safe for hand-made
            # test data.
            competition = sb.get("competition") or sp.get("competition")

            results.append({
                "match": sb["match"],
                "tier": _tier(sb["match"]),
                "competition": competition,
                "superbet": superbet_odds,
                "sample": sample_odds,
                # Per-match deep links from each source (may be None if a source
                # didn't expose one). Used to build the affiliate links below.
                "superbet_url": sb.get("url"),
                "sample_url": sp.get("url"),
                "analysis": analysis,
            })
            break  # one sample match is enough; move on to the next Superbet one

    return results


async def run_analysis():
    """Gather every source, then compute the value analysis for common matches."""
    # Superbet is scraped live; the demo source is a synthetic mirror of it.
    print("Scraping Superbet...")
    superbet_matches = await scrape_superbet()
    superbet_matches = ensure_obscure_examples(superbet_matches)
    print("Synthesising demo mirror source...")
    sample_matches = await scrape_sample(superbet_matches)

    print(f"\nSuperbet:      {len(superbet_matches)} matches")
    print(f"Sample (demo): {len(sample_matches)} matches")

    results = calculate_value(superbet_matches, sample_matches)
    print(f"Common matches analysed: {len(results)}")
    return results


# --- Per-source isolation -----------------------------------------------------
# Orchestration that lets a single failing source (Cloudflare block, proxy down,
# DOM change, timeout, or an empty result) fail on its own without taking the
# other source — or the whole API — down with it. The scraping logic itself is
# untouched; we only wrap the calls.

# The LIVE scrapers we run over the network, keyed by source name. The demo
# "sample" source is deliberately NOT here: it isn't scraped independently, it's
# synthesised from Superbet's odds each run (see scrape_all_isolated below).
SOURCES = {
    "superbet": scrape_superbet,
}

# Every source name that appears in the API response, in display order — the live
# Superbet scrape plus the synthetic "sample" demo source. Used by the API to
# build its per-source cache/freshness block, so it must list every source
# scrape_all_isolated returns a status for.
SOURCE_NAMES = ("superbet", "sample")

# How few matches counts as a FAILED scrape. A real DOM break returns ~0, while a
# healthy football pre-match scrape returns dozens-to-hundreds. Anything below
# this is treated as a failure for that source, so we never overwrite good cached
# data with a broken/near-empty result. Tune if a legitimately quiet day trips it.
MIN_PLAUSIBLE_MATCHES = 5


async def _scrape_one(name, scraper):
    """Run ONE scraper in isolation. Never raises.

    Returns a status dict: {name, ok, matches, count, error}.
      - ok is False if the scraper threw OR returned suspiciously few matches
        (< MIN_PLAUSIBLE_MATCHES, the empty-result guard). In that case the
        caller should KEEP that source's previous good data instead of using
        `matches` here.
      - error is a one-line summary (never a DOM/HTML dump, per project rules).
    """
    try:
        matches = await scraper()
    except Exception as exc:  # noqa: BLE001 — deliberately swallow ANY failure
        # repr() gives a single summary line (exception type + message); we never
        # log the page source or the full traceback's payload.
        return {"name": name, "ok": False, "matches": [], "count": 0,
                "error": repr(exc)}

    count = len(matches)
    if count < MIN_PLAUSIBLE_MATCHES:
        # Succeeded without error but came back near-empty — almost always a DOM
        # change. Flag it as a failure so the cache layer keeps the last good data.
        return {"name": name, "ok": False, "matches": matches, "count": count,
                "error": f"only {count} matches (< {MIN_PLAUSIBLE_MATCHES} threshold)"}

    return {"name": name, "ok": True, "matches": matches, "count": count,
            "error": None}


async def scrape_all_isolated():
    """Gather every source, each isolated so one failure can't sink the others.

    Returns {source_name: status_dict}. The live scraper(s) run first (one browser
    at a time, as before); a crash/timeout/empty result is caught and reported.

    The "sample" demo source is then synthesised from THIS run's Superbet odds
    rather than scraped: scrape_sample mirrors every fixture with a small random
    nudge, guaranteeing 100% overlap so the value comparison always has work to
    do. It is built only when Superbet actually returned data — if Superbet
    failed, we hand scrape_sample an empty list, so the sample also reports empty
    and the cache keeps each source's last-good data (same as any failed source).
    """
    statuses = {}
    for name, scraper in SOURCES.items():
        statuses[name] = await _scrape_one(name, scraper)

    if statuses["superbet"]["ok"]:
        # Top the base list up with a couple of fabricated obscure-tier fixtures
        # if the live list is light on reserve/women/youth games, so BOTH the
        # "main" and "obscure" tabs reliably have content. These must sit on the
        # Superbet side too (the comparison reads a fixture's tier from the
        # Superbet match name), so we add them here, before mirroring, and store
        # the topped-up list back as Superbet's matches so the analysis sees them.
        base = ensure_obscure_examples(statuses["superbet"]["matches"])
        statuses["superbet"]["matches"] = base
        statuses["superbet"]["count"] = len(base)
        superbet_matches = base
    else:
        superbet_matches = []

    statuses["sample"] = await _scrape_one(
        "sample", lambda: scrape_sample(superbet_matches)
    )
    return statuses


def top_value_bets(results, limit=10):
    """Flatten every flagged value bet across all matches and return the best ones.

    Each item is one outcome of one match that cleared the value threshold,
    sorted by how big the value (divergence) is, largest first.
    """
    value_bets = []
    for result in results:
        for outcome in OUTCOMES:
            a = result["analysis"][outcome]
            if not a["is_value"]:
                continue
            best = a["best_site"]
            value_bets.append({
                "match": result["match"],
                "outcome": outcome,
                "site": best,
                "odd": result[best][outcome],
                "divergence": a[f"{best}_div"],
            })

    # Biggest divergence (most value) first.
    value_bets.sort(key=lambda v: v["divergence"], reverse=True)
    return value_bets[:limit]


# Generic landing page per source. Used ONLY as a fallback when a match has no
# per-match deep link (the live scraper normally captures one; the sample source
# never has one). The sample source has no real bookmaker behind it, so it points
# at a harmless placeholder rather than any affiliate destination.
AFFILIATE_LINKS = {
    "superbet": "https://superbet.ro/pariuri-sportive/fotbal",
    "sample": "https://example.com/date-demo",
}

# Your affiliate tracking parameter per source, appended to every outgoing link
# as a query-string (e.g. "btag=12345"). Each site uses its own parameter
# name/value. Currently EMPTY = inactive: links go straight to the deep link with
# no tracking param. Fill these in from your affiliate dashboards to activate
# tracking — the wiring is already in place (see _with_affiliate below). The
# sample source is demo data with no affiliate deal, so it stays empty.
AFFILIATE_PARAMS = {
    "superbet": "",
    "sample": "",
}

# Internal source key -> display name used as the keys of the API response. The
# sample source is labelled "Sample data" so nobody mistakes it for a real
# bookmaker.
BOOKMAKER_NAMES = {"superbet": "Superbet", "sample": "Sample data"}

# Sources that are synthetic rather than real bookmakers. The API and UI use this
# to label them clearly as sample data.
SAMPLE_SOURCES = frozenset({"sample"})


def _with_affiliate(url, key):
    """Append this bookmaker's affiliate tracking parameter to a URL.

    Picks "?" or "&" depending on whether the URL already has a query-string, so
    we never produce a malformed link. Returns the URL unchanged when no tracking
    parameter is configured for this bookmaker.
    """
    param = AFFILIATE_PARAMS.get(key, "")
    if not param:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{param}"


def _bookmaker_picks(results, key):
    """Best-odds picks for ONE bookmaker, built only from that bookmaker's data.

    Returns a list of pick dicts sorted by divergence (largest first). A result
    that lacks this bookmaker's odds or analysis is skipped instead of raising,
    so incomplete data for one source can never affect another source's list.
    """
    picks = []
    for result in results:
        odds = result.get(key)
        analysis = result.get("analysis")
        if not odds or not analysis:
            continue
        try:
            # This bookmaker's best outcome in the match = the one where it beats
            # the median by the most. f"{key}_div" is "superbet_div"/"sample_div".
            best_outcome = max(OUTCOMES, key=lambda o: analysis[o][f"{key}_div"])
            divergence = analysis[best_outcome][f"{key}_div"]
            odd = odds[best_outcome]
        except (KeyError, TypeError):
            continue  # malformed entry: skip it, keep the rest
        # Prefer the per-match deep link; fall back to the site's football
        # landing page only when no deep link was captured. Either way we append
        # the affiliate tracking parameter.
        deep_link = result.get(f"{key}_url") or AFFILIATE_LINKS[key]
        picks.append({
            "match": result["match"],
            "outcome": best_outcome,
            "odd": odd,
            "divergence": divergence,
            "link": _with_affiliate(deep_link, key),
        })
    picks.sort(key=lambda p: p["divergence"], reverse=True)
    return picks


def real_sources(source_names):
    """The names in `source_names` that are real bookmakers (not sample data)."""
    return [n for n in source_names if n not in SAMPLE_SOURCES]


def single_source_listing(key, matches):
    """List one real source's own matches with their odds (no comparison).

    Used when fewer than two real sources are available: divergence needs a second
    source, so instead of an empty view we show what this source offers. Fabricated
    filler fixtures (flagged "synthetic") are left out so only real fixtures show.
    """
    fallback = AFFILIATE_LINKS[key]
    listing = []
    for m in matches:
        if m.get("synthetic"):
            continue
        listing.append({
            "match": m["match"],
            "tier": _tier(m["match"]),
            "competition": m.get("competition"),
            "home": m["home"],
            "draw": m["draw"],
            "away": m["away"],
            "link": _with_affiliate(m.get("url") or fallback, key),
        })
    return listing


def best_odds_per_bookmaker(results, limit=5):
    """For each bookmaker, the `limit` matches where it is most generous.

    "Most generous" means the bookmaker's odds sit furthest ABOVE the others —
    i.e. its implied probability is furthest BELOW the median across sources, the
    biggest positive divergence. For every match we take that bookmaker's single
    best outcome (its largest divergence), rank all matches by it, and keep the
    top `limit`.

    Each bookmaker is computed independently (see _bookmaker_picks): an error or
    missing data for one never empties the other's list. Divergence needs a real
    second source to compare against; the API therefore skips this ranking in
    single-source mode and uses single_source_listing instead.

    Returns a dict keyed by display name, e.g.:
        {"Superbet":    [ {match, outcome, odd, divergence, link}, ... ],
         "Sample data": [ ... ]}
    """
    by_bookmaker = {}
    for key, display in BOOKMAKER_NAMES.items():
        try:
            by_bookmaker[display] = _bookmaker_picks(results, key)[:limit]
        except Exception:  # noqa: BLE001 — isolate each bookmaker from the others
            by_bookmaker[display] = []
    return by_bookmaker


if __name__ == "__main__":
    # The Windows console defaults to cp1252, which can't encode the em-dash or
    # Romanian team names. Force UTF-8 so printing doesn't crash / show garbage.
    sys.stdout.reconfigure(encoding="utf-8")

    results = asyncio.run(run_analysis())

    top = top_value_bets(results, limit=10)

    print(f"\n=== Top {len(top)} value odds (divergence > {VALUE_THRESHOLD:.0%}) ===")
    if not top:
        print("No value odds found right now.")
    for i, v in enumerate(top, start=1):
        # e.g. "1. [sample] Home  @ 2.10  (+5.2%)  —  Team1 vs Team2"
        print(
            f"{i:>2}. [{v['site']}] {v['outcome'].capitalize():<5} "
            f"@ {v['odd']:<5} ({v['divergence']:+.1%})  —  {v['match']}"
        )

"""
main.py — the FastAPI app that serves odds analysis to the React frontend.

Endpoints:
    GET /health     -> simple liveness check, {"status": "ok"}
    GET /api/odds   -> returns the analysed common matches, split into "main" and
                       "obscure" tiers. Served from an in-memory cache so it's
                       instant after the first scrape.

Run it from the backend/ folder:
    cd backend && py -m uvicorn api.main:app --reload
"""

import asyncio
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Make the backend/ folder importable no matter how uvicorn is launched, so the
# "analysis" package can be imported. __file__ is backend/api/main.py, so two
# dirnames up is backend/.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

# scrape_all_isolated() runs both scrapers, each wrapped so one failing source
# can't take the other down; calculate_value()/best_odds_per_bookmaker() then
# analyse whatever data we have. SOURCES is the {name: scraper} registry.
from analysis.calculator import (
    SOURCES,
    best_odds_per_bookmaker,
    calculate_value,
    scrape_all_isolated,
)

# Source names we track, e.g. ("superbet", "betano"). Derived from the registry
# so adding a scraper there is automatically picked up here.
SOURCE_NAMES = tuple(SOURCES)

# --- Logging -----------------------------------------------------------------
# A dedicated logger with its own timestamped handler so per-source scrape lines
# are visible in Railway logs regardless of uvicorn's formatter. propagate=False
# keeps it from double-printing through the root/uvicorn loggers.
logger = logging.getLogger("comparacote.scraper")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] scraper: %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


# --- In-memory cache ---------------------------------------------------------
# A full scrape takes ~2.5 minutes, so we never want to run it on a user request
# if we can avoid it. We keep the last result in memory and reuse it until it
# goes stale. No Redis, no database — just a module-level dict that lives as long
# as the server process does.

# How long a scrape stays "fresh". After this, the next request re-scrapes.
# 30 minutes is plenty for pre-match 1X2 odds.
CACHE_TTL_SECONDS = 30 * 60

# How often the background scheduler re-scrapes. Kept a little SHORTER than the
# TTL so a new scrape always lands before the current one goes stale — that way
# user requests basically never have to wait on a live scrape.
REFRESH_INTERVAL_SECONDS = 25 * 60

# The cache itself: the last response payload and when it was produced
# (time.monotonic() seconds — monotonic so it's immune to system clock changes).
_cache = {"data": None, "timestamp": None}

# Per-source raw-scrape cache. We keep the LAST GOOD matches for every source so
# a failed/empty scrape for one source doesn't wipe out good data — we re-run the
# analysis against the last good matches instead. Two timestamps per source:
#   *_mono -> time.monotonic(), used for the stale check (immune to clock changes)
#   *_iso  -> wall-clock ISO 8601, sent to the frontend for display
_sources = {
    name: {
        "matches": [],            # last good matches for this source
        "count": 0,               # how many matches are currently in use
        "last_success_mono": None,  # monotonic time of last good scrape
        "last_success_iso": None,   # wall-clock ISO of last good scrape
        "ok": False,              # did the MOST RECENT attempt succeed?
        "error": None,            # one-line summary of the most recent failure
    }
    for name in SOURCE_NAMES
}

# A source counts as "stale" once its last successful scrape is older than this.
# Kept above REFRESH_INTERVAL_SECONDS so a single missed refresh doesn't flip it.
STALE_AFTER_SECONDS = 45 * 60

# Only one scrape should run at a time. Without this lock, the startup warm-up
# and an early user request (or two simultaneous users) could each kick off the
# heavy scrape at the same time.
_scrape_lock = asyncio.Lock()

# Holds the startup warm-up task so it isn't garbage-collected mid-run.
_warmup_task = None


def _is_fresh():
    """True if we have cached data younger than CACHE_TTL_SECONDS."""
    if _cache["data"] is None or _cache["timestamp"] is None:
        return False
    return (time.monotonic() - _cache["timestamp"]) < CACHE_TTL_SECONDS


def scrape_isolated_sync():
    """Run the isolated multi-source scrape to completion in the CURRENT thread.

    Returns {source_name: status_dict} from scrape_all_isolated().

    asyncio.run() spins up a brand-new event loop here. When this runs inside a
    worker thread (see refresh_cache below), that fresh loop is created off
    uvicorn's own loop — and on Windows a non-main thread gets a
    ProactorEventLoop, which can spawn the subprocesses Playwright needs. This
    sidesteps the conflict with uvicorn --reload that the old
    set_event_loop_policy approach couldn't fix.
    """
    return asyncio.run(scrape_all_isolated())


def _sources_freshness():
    """Build the per-source freshness block for the API response.

    Recomputed on every request (not baked into the cached payload) so the
    stale flag reflects how old the data is RIGHT NOW, not at scrape time.
    """
    out = {}
    now_mono = time.monotonic()
    for name, src in _sources.items():
        last_mono = src["last_success_mono"]
        if last_mono is None:
            age_seconds = None
            stale = True  # never scraped successfully -> treat as stale
        else:
            age_seconds = int(now_mono - last_mono)
            stale = age_seconds > STALE_AFTER_SECONDS
        out[name] = {
            "ok_last_run": src["ok"],          # did the latest attempt succeed?
            "matches": src["count"],           # matches currently served
            "last_success": src["last_success_iso"],
            "age_seconds": age_seconds,        # None if never succeeded
            "stale": stale,
            "error": src["error"],             # latest failure summary, or None
        }
    return out


def _build_response():
    """Cached analysis payload + a LIVE per-source freshness block.

    Shallow-copies the cached data so we never mutate it while overlaying the
    freshly computed `sources` block.
    """
    data = dict(_cache["data"])
    data["sources"] = _sources_freshness()
    return data


async def refresh_cache(force=False):
    """Scrape (in a worker thread), build the payload, and store it in _cache.

    Returns the freshly built payload. The lock ensures only one scrape runs at
    a time; anyone else just waits and then reuses the result.

    force=True skips the "is it already fresh?" short-circuit. The scheduled
    background job uses it so it always produces a brand-new scrape on its timer,
    keeping the cache warm even though the current data hasn't gone stale yet.
    """
    async with _scrape_lock:
        # Another coroutine may have refreshed the cache while we waited for the
        # lock. If so, reuse its result instead of scraping all over again.
        # (Skipped when forced, so the scheduled refresh always re-scrapes.)
        if not force and _is_fresh():
            return _cache["data"]

        # Hand the blocking, browser-driving work to a separate thread so
        # Playwright gets its own fresh event loop, isolated from uvicorn's.
        # Each source is scraped in isolation; statuses is {name: status_dict}
        # and never raises, even if a scraper crashed.
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            statuses = await loop.run_in_executor(pool, scrape_isolated_sync)

        # Merge each source's result into the per-source cache. A successful
        # scrape replaces that source's data and bumps its last_success stamps;
        # a failed/empty one is logged and the PREVIOUS good data is kept, so we
        # never overwrite good odds with an error or an empty page.
        now_mono = time.monotonic()
        now_iso = datetime.now(timezone.utc).isoformat()
        for name in SOURCE_NAMES:
            status = statuses[name]
            src = _sources[name]
            src["ok"] = status["ok"]
            src["error"] = status["error"]
            if status["ok"]:
                src["matches"] = status["matches"]
                src["count"] = status["count"]
                src["last_success_mono"] = now_mono
                src["last_success_iso"] = now_iso
                logger.info("%s OK - %d matches", name, status["count"])
            else:
                # Visibility: one summary line, no DOM dump (per project rules).
                logger.warning(
                    "%s FAILED (%s) - keeping last good data "
                    "(%d matches, last success %s)",
                    name,
                    status["error"],
                    src["count"],
                    src["last_success_iso"] or "never",
                )

        # Run the analysis against whatever each source currently holds: fresh
        # data for sources that just succeeded, last-good data for those that
        # didn't. calculate_value pairs the two sources by fixture.
        superbet_matches = _sources["superbet"]["matches"]
        betano_matches = _sources["betano"]["matches"]
        results = calculate_value(superbet_matches, betano_matches)

        # Split the flat results list into the two tiers the frontend cares about.
        main = [r for r in results if r["tier"] == "main"]
        obscure = [r for r in results if r["tier"] == "obscure"]
        logger.info(
            "analysis: %d common matches (%d main / %d obscure)",
            len(results),
            len(main),
            len(obscure),
        )

        _cache["data"] = {
            "count": len(results),
            "main": main,
            "obscure": obscure,
            # Per-bookmaker "best 5 odds of the day", computed across ALL common
            # matches (both tiers) — see Tab 2 in the project spec.
            "best_odds_per_bookmaker": best_odds_per_bookmaker(results),
            # Wall-clock UTC time this refresh finished, ISO 8601 (e.g.
            # "2026-06-30T12:34:56.789012+00:00"). The frontend diffs this
            # against the current time for its "Actualizat acum X minute"
            # indicator, so it must be set HERE (when the data is produced), not
            # at request time. _cache["timestamp"] below stays monotonic for the
            # freshness/TTL logic, which must be immune to clock changes.
            "generated_at": now_iso,
            # Per-source freshness (fresh/stale, last success, latest error) is
            # added at response time by _build_response so it's always current.
        }
        _cache["timestamp"] = now_mono
        return _cache["data"]


@asynccontextmanager
async def lifespan(app):
    """Warm the cache at startup and keep it fresh on a schedule.

    Startup does two things:
      1. Kicks off the first scrape as a background task (not awaited — awaiting
         would block the server from accepting connections for ~2.5 minutes). If
         a request arrives before this finishes, get_odds scrapes on demand and
         the lock keeps the two from doubling up.
      2. Starts an APScheduler job that re-scrapes every REFRESH_INTERVAL_SECONDS
         so the cache is refreshed in the background before it ever goes stale.
    """
    global _warmup_task
    _warmup_task = asyncio.create_task(refresh_cache())

    # AsyncIOScheduler runs jobs on uvicorn's own event loop, so the async
    # refresh_cache coroutine works directly as a job. force=True so each tick
    # always produces a fresh scrape instead of short-circuiting on a still-fresh
    # cache.
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        refresh_cache,
        trigger="interval",
        seconds=REFRESH_INTERVAL_SECONDS,
        kwargs={"force": True},
        # If a previous run is still going when the next tick is due, skip it
        # rather than piling up a second scrape.
        max_instances=1,
    )
    scheduler.start()

    yield

    # Stop the scheduler cleanly on shutdown.
    scheduler.shutdown(wait=False)


app = FastAPI(title="Odds Comparator API", lifespan=lifespan)

# CORS: allow every origin so the React dev server (running on a different port,
# e.g. http://localhost:5173) can call this API during local development.
# Tighten allow_origins to the real frontend URL before deploying to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Liveness probe — lets us (and Railway) confirm the API is up."""
    return {"status": "ok"}


@app.get("/api/odds")
async def get_odds():
    """Return the analysed odds, served from cache when it's still fresh.

    Fast path: a fresh cache returns instantly. Otherwise (cache empty or older
    than CACHE_TTL_SECONDS) we scrape, refresh the cache, and return the result.
    Either way the response carries a live per-source freshness block (`sources`)
    so the caller can tell which sources are fresh vs stale. A single failing
    source never 500s this endpoint — it just shows up as stale/failed.
    """
    if not _is_fresh():
        await refresh_cache()
    return _build_response()

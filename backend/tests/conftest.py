"""Shared test helpers. No test here touches the network: every scraper is stubbed."""

import pytest

from api import main


def make_matches(n=6):
    """n hand-made fixtures in the shape the scrapers return."""
    teams = ["Alpha Town", "Beta City", "Gamma Rovers", "Delta United",
             "Epsilon Athletic", "Zeta Wanderers", "Eta Albion", "Theta Rangers",
             "Iota Dynamo", "Kappa Sporting", "Lambda Olympic", "Sigma Racing"]
    return [
        {"match": f"{teams[2 * i]} vs {teams[2 * i + 1]}", "home": 2.2,
         "draw": 3.3, "away": 3.1, "competition": "Test League", "url": None}
        for i in range(n)
    ]


def status(name, ok=True, matches=None, error=None):
    """A scrape status dict as returned by scrape_all_isolated()."""
    matches = matches if ok and matches is not None else []
    return {"name": name, "ok": ok, "matches": matches, "count": len(matches),
            "error": None if ok else (error or "boom")}


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Reset the API's in-memory cache and per-source state around every test."""
    monkeypatch.delenv("SIMULATE_FAILED_SOURCES", raising=False)
    main._cache["data"] = None
    main._cache["timestamp"] = None
    for src in main._sources.values():
        src.update(matches=[], count=0, last_success_mono=None,
                   last_success_iso=None, ok=False, error=None)
    yield


@pytest.fixture
def stub_scrape(monkeypatch):
    """Returns a function that sets what the (stubbed) scrape reports next."""
    def _set(statuses):
        monkeypatch.setattr(main, "scrape_isolated_sync", lambda: statuses)
    return _set

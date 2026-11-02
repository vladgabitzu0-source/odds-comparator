import asyncio

from fastapi.testclient import TestClient

from api import main
from tests.conftest import make_matches, status

client = TestClient(main.app)  # no `with`: lifespan (warm-up, scheduler) not started


def refresh():
    asyncio.run(main.refresh_cache(force=True))


def test_single_source_mode_returns_notice_and_matches(stub_scrape):
    matches = make_matches(6)
    stub_scrape({"superbet": status("superbet", matches=matches),
                 "sample": status("sample", matches=matches)})
    refresh()
    body = client.get("/api/odds").json()
    assert body["status"] == "ok"
    assert body["comparison_mode"] == "single_source"
    assert "at least two sources" in body["single_source"]["notice"]
    assert [m["match"] for m in body["single_source"]["matches"]] == [
        m["match"] for m in matches]
    assert body["best_odds_per_bookmaker"] == {}


def test_generated_at_advances_only_after_a_successful_refresh(stub_scrape):
    stub_scrape({"superbet": status("superbet", ok=False),
                 "sample": status("sample", ok=False)})
    refresh()
    assert main._cache["data"]["generated_at"] is None
    assert client.get("/api/odds").json()["status"] == "unavailable"

    matches = make_matches()
    stub_scrape({"superbet": status("superbet", matches=matches),
                 "sample": status("sample", matches=matches)})
    refresh()
    first = main._cache["data"]["generated_at"]
    assert first is not None

    stub_scrape({"superbet": status("superbet", ok=False),
                 "sample": status("sample", ok=False)})
    refresh()
    assert main._cache["data"]["generated_at"] == first  # unchanged


def test_last_success_at_is_tracked_per_source(stub_scrape):
    matches = make_matches()
    stub_scrape({"superbet": status("superbet", matches=matches),
                 "sample": status("sample", ok=False)})
    refresh()
    src = client.get("/api/odds").json()["sources"]
    assert src["superbet"]["last_success_at"] is not None
    assert src["sample"]["last_success_at"] is None

    stub_scrape({"superbet": status("superbet", ok=False),
                 "sample": status("sample", matches=matches)})
    refresh()
    src2 = client.get("/api/odds").json()["sources"]
    assert src2["superbet"]["last_success_at"] == src["superbet"]["last_success_at"]
    assert src2["sample"]["last_success_at"] is not None


def test_odds_endpoint_200_with_failed_sources_marked_stale(stub_scrape):
    stub_scrape({"superbet": status("superbet", ok=False),
                 "sample": status("sample", ok=False)})
    refresh()
    resp = client.get("/api/odds")
    assert resp.status_code == 200
    for src in resp.json()["sources"].values():
        assert src["stale"] is True
        assert src["ok_last_run"] is False


def test_warming_up_before_first_refresh(monkeypatch):
    async def noop(force=False):  # don't start a real scrape
        return None
    monkeypatch.setattr(main, "refresh_cache", noop)
    body = client.get("/api/odds").json()
    assert body["status"] == "warming_up"
    assert body["generated_at"] is None and body["main"] == []


def test_simulated_failure_env_var(monkeypatch, stub_scrape):
    matches = make_matches()
    stub_scrape({"superbet": status("superbet", matches=matches),
                 "sample": status("sample", matches=matches)})
    monkeypatch.setenv("SIMULATE_FAILED_SOURCES", "sample")
    refresh()
    src = client.get("/api/odds").json()["sources"]
    assert src["sample"]["ok_last_run"] is False
    assert src["sample"]["error"] == "simulated failure"
    assert src["superbet"]["ok_last_run"] is True

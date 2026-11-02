from analysis.calculator import best_odds_per_bookmaker, calculate_value
from tests.conftest import make_matches


def _results():
    sb = make_matches(3)
    sp = [dict(m, home=2.0, draw=3.5, away=3.4) for m in make_matches(3)]
    return calculate_value(sb, sp)


def test_best_odds_empty_input_gives_empty_lists():
    out = best_odds_per_bookmaker([])
    assert out == {"Superbet": [], "Sample data": []}


def test_best_odds_one_source_missing_does_not_empty_the_other():
    results = _results()
    assert results  # sanity: the hand-made fixtures paired up
    for r in results:
        r["sample"] = None  # this source has no usable odds
    out = best_odds_per_bookmaker(results)
    assert len(out["Superbet"]) > 0
    assert out["Sample data"] == []


def test_best_odds_malformed_entry_is_skipped_not_fatal():
    results = _results()
    results[0]["analysis"] = {"home": {}}  # malformed: missing keys
    out = best_odds_per_bookmaker(results)
    # The other entries still produce picks for both bookmakers.
    assert len(out["Superbet"]) == len(results) - 1
    assert len(out["Sample data"]) == len(results) - 1

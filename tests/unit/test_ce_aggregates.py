import ce_aggregates as ca

CLASSIC = "1 Apple|Normal|Standard|Classic|25 Apples"
CHESS = "1 Apple|Normal|Standard|Chess|25 Apples"
LATEST = "2026-09-27"


def hold(category, pid, name, start, end=LATEST, days=10, standing=True, tied=1):
    return {
        "category": category,
        "playerId": pid,
        "playerName": name,
        "start": start,
        "end": end,
        "days": days,
        "stillStanding": standing,
        "tiedHolders": tied,
    }


def test_normalize_ce_defaults_to_off():
    assert ca.normalize_ce(None) == "Off"
    assert ca.normalize_ce("mix") == "Mix"
    assert ca.normalize_ce("ONLY") == "Only"
    assert ca.normalize_ce("nonsense") == "Off"


def test_filter_holds_separates_ce_levels():
    holds = [hold(CLASSIC, "a", "A", "2026-01-01"), hold(CHESS, "a", "A", "2026-01-01")]
    assert [h["category"] for h in ca.filter_holds(holds, "Off")] == [CLASSIC]
    assert [h["category"] for h in ca.filter_holds(holds, "Only")] == [CHESS]
    assert len(ca.filter_holds(holds, "Mix")) == 2


def test_build_career_splits_tied_and_untied_days():
    holds = [
        hold(CLASSIC, "a", "A", "2026-01-01", days=10, tied=1),
        hold(CHESS, "a", "A", "2026-02-01", days=4, tied=2, standing=False, end="2026-02-05"),
    ]
    (row,) = ca.build_career(holds)
    assert row["wrDays"] == 14
    assert row["wrDaysUntied"] == 10
    assert row["wrDaysTied"] == 4
    assert row["holds"] == 2
    assert row["standingHolds"] == 1


def test_player_match_uses_id_only_when_known():
    holds = [
        hold(CLASSIC, "id1", "Bob", "2026-01-01", days=5),
        hold(CHESS, "id2", "Bob", "2026-01-01", days=50),
        hold(CHESS, None, "Bob", "2026-01-01", days=70),
    ]
    career = ca.player_career(holds, "id1", "Bob")
    assert career["wrDays"] == 5


def test_player_match_falls_back_to_name_without_id():
    holds = [hold(CLASSIC, "id1", "Bob", "2026-01-01"), hold(CHESS, "id2", "Alice", "2026-01-01")]
    assert ca._matches_player(holds[0], None, "bob")
    assert not ca._matches_player(holds[1], None, "bob")


def test_build_improving_limit_can_be_lifted():
    holds = [hold(CLASSIC, f"p{i}", f"P{i}", "2026-09-25") for i in range(30)]
    assert len(ca.build_improving(holds, LATEST)["7d"]) == 25
    assert len(ca.build_improving(holds, LATEST, limit=None)["7d"]) == 30

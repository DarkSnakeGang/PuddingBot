import pytest

import github_cache_fetcher as gcf
from cogs.fastsnakestats import FastSnakeStats


@pytest.mark.parametrize(
    "record, game",
    [
        ({"weblink": "https://www.speedrun.com/snake_game/runs/a"}, "main"),
        ({"weblink": "https://www.speedrun.com/snake_game_ce/runs/b"}, "ce"),
        # CE-hosted Tally run without a source tag (real archive case)
        ({"weblink": "https://www.speedrun.com/snake_game_ce/runs/c", "category": "Tally|Normal|Small|Classic|High Score"}, "ce"),
        ({"source": "ce"}, "ce"),
        ({}, "main"),
        # Future explicit game field wins over everything else
        ({"game": "9dow0go1", "weblink": "https://www.speedrun.com/snake_game/runs/d"}, "ce"),
        ({"gameId": "snake_game"}, "main"),
    ],
)
def test_run_src_game(record, game):
    assert gcf.run_src_game(record) == game


def test_classify_skips_unverified_and_accepts_list_or_dict_shards():
    as_dict = {"runs": {
        "a": {"id": "a", "weblink": "https://www.speedrun.com/snake_game/runs/a"},
        "b": {"id": "b", "weblink": "https://www.speedrun.com/snake_game_ce/runs/b", "status": "verified"},
        "c": {"id": "c", "status": {"status": "new"}},
        "d": {"id": "d", "status": "rejected"},
    }}
    assert gcf.classify_shard_runs(as_dict)["runs"] == {"a": ("main", None), "b": ("ce", None)}
    as_list = {"runs": [{"id": "e", "source": "ce"}, {"no": "id"}]}
    assert gcf.classify_shard_runs(as_list)["runs"] == {"e": ("ce", None)}


@pytest.mark.parametrize(
    "record, examiner",
    [
        ({"examiner": "x1", "examinerName": "Mod"}, ("x1", "Mod")),
        ({"examiner": {"id": "x1", "name": "Mod"}}, ("x1", "Mod")),
        ({"examiner": {"id": "x1", "names": {"international": "Mod"}}}, ("x1", "Mod")),
        # raw speedrun.com status object
        ({"status": {"status": "verified", "examiner": "x1"}}, ("x1", None)),
        ({"examinerName": "Mod"}, ("Mod", "Mod")),
        ({}, (None, None)),
    ],
)
def test_run_examiner_formats(record, examiner):
    assert gcf.run_examiner(record) == examiner


def tally_shard(runs, examiner_names=None, player_names=None):
    return {"runs": runs, "examinerNames": examiner_names or {}, "playerNames": player_names or {}}


def test_tally_dedupes_runs_listed_in_two_shards():
    counts = gcf.tally_verified([
        tally_shard({"a": ("main", None), "b": ("ce", None)}),
        tally_shard({"b": ("ce", None), "c": ("main", None)}),
    ])
    assert (counts["main"], counts["ce"], counts["total"]) == (2, 1, 3)
    assert counts["examiners"] == {"main": [], "ce": [], "both": []}
    assert counts["unexamined"] == {"main": 2, "ce": 1, "both": 3}


def test_tally_examiners_per_game_and_name_fallbacks():
    counts = gcf.tally_verified(
        [
            tally_shard(
                {"a": ("main", "x1"), "b": ("main", "x1"), "c": ("ce", "x1"), "d": ("ce", "x2"), "e": ("main", None)},
                examiner_names={"x1": "ModOne"},
            ),
            tally_shard({"f": ("main", "x3"), "g": ("main", "x4")}, player_names={"x3": "RunnerMod"}),
        ],
        index_examiners={"x2": {"name": "IndexMod"}},
    )
    assert counts["examiners"]["main"] == [["ModOne", 2], ["RunnerMod", 1], ["x4", 1]]
    assert counts["examiners"]["ce"] == [["IndexMod", 1], ["ModOne", 1]]
    assert counts["examiners"]["both"][0] == ["ModOne", 3]
    assert counts["unexamined"] == {"main": 1, "ce": 0, "both": 1}


@pytest.mark.parametrize(
    "path, ok",
    [
        ("time-travel-cache/runs/Classic/25_Apples.json", True),
        ("time-travel-cache/runs/New_Category/Any.json", True),
        ("time-travel-cache/../.env.json", False),
        ("/etc/passwd.json", False),
        (None, False),
    ],
)
def test_safe_shard_path(path, ok):
    assert gcf._safe_shard_path(path) is ok


def test_new_archive_shards_are_counted_and_unchanged_shards_not_refetched():
    import asyncio

    board = "time-travel-cache/runs/Classic/25_Apples.json"
    other = "time-travel-cache/runs-other/snake_game_ce/69_Apples.json"
    shards = {
        board: {"runs": {"a": {"id": "a", "weblink": "https://www.speedrun.com/snake_game/runs/a"}}},
        other: {"runs": {
            "b": {"id": "b", "game": "9dow0go1"},
            "c": {"id": "c", "weblink": "https://www.speedrun.com/snake_game_ce/runs/c",
                  "examiner": "x1", "examinerName": "ModOne"},
        }},
    }
    index = {"lastUpdated": "1", "shards": [{"path": board, "count": 1}]}
    fetched = []

    fetcher = gcf.GitHubCacheFetcher()

    async def load_index():
        return index, False

    async def load_shard(path, use_local):
        fetched.append(path)
        return shards[path]

    fetcher._load_runs_archive_index = load_index
    fetcher._load_runs_archive_shard = load_shard

    async def run():
        first = await fetcher._load_verified_counts()
        assert (first["main"], first["ce"], first["total"]) == (1, 0, 1)
        # FastSnakeStats later adds a non-board CE shard
        index["lastUpdated"] = "2"
        index["shards"].append({"path": other, "count": 2, "board": False})
        second = await fetcher._load_verified_counts()
        assert (second["main"], second["ce"], second["total"]) == (1, 2, 3)
        assert second["examiners"]["ce"] == [["ModOne", 1]]
        assert fetched == [board, other]

    asyncio.run(run())


def test_verified_embed_defaults_to_both_and_explains_missing_examiners():
    cog = object.__new__(FastSnakeStats)
    counts = {"main": 47415, "ce": 239, "total": 47654, "lastUpdated": "2026-10-09T03:11:41Z", "missingShards": 0}
    both = cog.create_verified_embed(counts)
    assert "**47,654**" in both.description
    assert [(f.name, f.value) for f in both.fields[:2]] == [("Google Snake", "47,415"), ("Category Extensions", "239")]
    assert both.fields[2].name == "Verified by" and "doesn't record" in both.fields[2].value
    main = cog.create_verified_embed(counts, "main")
    assert "**47,415**" in main.description and [f.name for f in main.fields] == ["Verified by"]
    assert "2026-10-09" in main.footer.text and "Page" not in main.footer.text


def test_verified_embed_paginates_examiners():
    cog = object.__new__(FastSnakeStats)
    examiners = [[f"Mod_{i}", 100 - i] for i in range(20)]
    counts = {
        "main": 2000, "ce": 0, "total": 2000, "lastUpdated": "2026-10-09",
        "examiners": {"main": examiners, "ce": [], "both": examiners},
        "unexamined": {"main": 7, "ce": 0, "both": 7},
    }
    assert cog.verified_total_pages(counts) == 2
    first = cog.create_verified_embed(counts)
    lines = first.fields[2].value.split("\n")
    assert lines[0] == "`1.` Mod\\_0 — **100**" and len(lines) == 16 and "7 runs have no examiner" in lines[-1]
    second = cog.create_verified_embed(counts, "both", 1)
    assert second.fields[2].value.startswith("`16.` Mod\\_15 — **85**")
    assert second.footer.text.startswith("Page 2/2")

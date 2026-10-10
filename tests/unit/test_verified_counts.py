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
    assert gcf.classify_shard_runs(as_dict) == {"a": "main", "b": "ce"}
    as_list = {"runs": [{"id": "e", "source": "ce"}, {"no": "id"}]}
    assert gcf.classify_shard_runs(as_list) == {"e": "ce"}


def test_tally_dedupes_runs_listed_in_two_shards():
    counts = gcf.tally_verified([{"a": "main", "b": "ce"}, {"b": "ce", "c": "main"}])
    assert counts == {"main": 2, "ce": 1, "total": 3}


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
            "c": {"id": "c", "weblink": "https://www.speedrun.com/snake_game_ce/runs/c"},
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
        assert fetched == [board, other]

    asyncio.run(run())


def test_verified_embed_defaults_and_both():
    cog = object.__new__(FastSnakeStats)
    counts = {"main": 47415, "ce": 239, "total": 47654, "lastUpdated": "2026-10-09T03:11:41Z", "missingShards": 0}
    main = cog.create_verified_embed(counts)
    assert "**47,415**" in main.description and "Google Snake" in main.description and not main.fields
    both = cog.create_verified_embed(counts, "both")
    assert "**47,654**" in both.description
    assert [(f.name, f.value) for f in both.fields] == [("Google Snake", "47,415"), ("Category Extensions", "239")]
    assert "2026-10-09" in main.footer.text

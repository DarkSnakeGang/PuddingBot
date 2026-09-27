import asyncio

import github_cache_fetcher as gcf


def test_cached_dedupes_concurrent_loads_and_backs_off_on_failure(monkeypatch):
    fetcher = gcf.GitHubCacheFetcher()
    calls = []

    async def loader():
        calls.append(1)
        await asyncio.sleep(0.01)
        return {"n": len(calls)}

    async def failing():
        calls.append("fail")
        return None

    async def run():
        results = await asyncio.gather(*(fetcher._cached("x", loader) for _ in range(5)))
        assert all(r == {"n": 1} for r in results)
        assert calls == [1]

        # Expired + failing refresh: keep serving the old copy, don't retry immediately
        fetcher._cache["x"]["expires"] = 0
        assert await fetcher._cached("x", failing) == {"n": 1}
        assert await fetcher._cached("x", failing) == {"n": 1}
        assert calls == [1, "fail"]

    asyncio.run(run())


def test_updated_stamp_prefers_meta():
    assert gcf._updated_stamp({"meta": {"lastUpdated": "b"}, "lastUpdated": "a"}) == "b"
    assert gcf._updated_stamp({"lastUpdated": "a"}) == "a"
    assert gcf._updated_stamp(None) == ""

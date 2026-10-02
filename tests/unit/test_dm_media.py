import pytest

from cogs import dm_media as dm

BASE = "https://shop.example/"
PAGE = """
<html><head>
<meta property="og:image" content="//shop.example/cdn/shop/files/preview.jpg?v=1">
<link rel="stylesheet" href="/cdn/shop/t/1/assets/theme.css?v=2">
<link rel="preload" href="/cdn/shop/t/1/assets/font.woff2?v=3">
</head><body>
<img src="/cdn/shop/files/icon.svg?width=32">
<img src="/cdn/shop/files/menu-tile.jpg?v=5&width=240">
<img src="/cdn/shop/files/hero.jpg?v=6&width=750"
     srcset="/cdn/shop/files/hero.jpg?v=6&width=375 375w, /cdn/shop/files/hero.jpg?v=6&width=1500 1500w">
<video><source src="/cdn/shop/videos/clip.HD-720p.mp4?v=0"></video>
<img src="/uploads/photo-300x200.jpg">
</body></html>
"""


@pytest.mark.parametrize(
    "url, full",
    [
        ("https://a.b/x.jpg?v=1&width=240", "https://a.b/x.jpg?v=1"),
        ("https://a.b/x.jpg?crop=center&height=32&v=1&width=32", "https://a.b/x.jpg?v=1"),
        ("https://a.b/wp/photo-300x200.jpg", "https://a.b/wp/photo.jpg"),
        ("https://a.b/s/files/item_600x.png?v=2", "https://a.b/s/files/item.png?v=2"),
        ("https://a.b/IMG_2024.jpg", "https://a.b/IMG_2024.jpg"),
        (
            "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/18/Cgasnake.png/250px-Cgasnake.png?utm_source=x",
            "https://upload.wikimedia.org/wikipedia/commons/1/18/Cgasnake.png",
        ),
    ],
)
def test_full_size_url(url, full):
    assert dm._full_size_url(url) == full


def test_wikimedia_thumbs_share_family_with_original():
    keys = {
        dm._media_family_key(u)
        for u in (
            "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/18/Cgasnake.png/250px-Cgasnake.png?utm_content=a",
            "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/18/Cgasnake.png/500px-Cgasnake.png?utm_content=b",
            "https://upload.wikimedia.org/wikipedia/commons/1/18/Cgasnake.png?utm_content=c",
        )
    }
    assert len(keys) == 1


def test_size_hint():
    assert dm._size_hint("https://a.b/x.jpg?width=1500") == 1500
    assert dm._size_hint("https://a.b/photo-300x200.jpg") == 300
    assert dm._size_hint("https://a.b/IMG_2024.jpg") == 0


def test_plan_skips_assets_and_orders_by_importance():
    plans = dm.plan_media_fetches(BASE, PAGE)
    firsts = [attempts[0] for attempts in plans]
    assert not any(u.endswith((".css?v=2", ".woff2?v=3")) or ".svg" in u for u in firsts)
    assert firsts[0] == "https://shop.example/cdn/shop/files/preview.jpg?v=1"
    assert firsts[1].endswith("clip.HD-720p.mp4?v=0")
    assert firsts[2] == "https://shop.example/cdn/shop/files/hero.jpg?v=6"
    assert firsts[-1] == "https://shop.example/cdn/shop/files/menu-tile.jpg?v=5"
    hero = plans[2]
    assert hero[1] == "https://shop.example/cdn/shop/files/hero.jpg?v=6&width=1500"


@pytest.mark.parametrize(
    "message, url",
    [
        ("see https://en.wikipedia.org/wiki/Snake_(video_game_genre)", "https://en.wikipedia.org/wiki/Snake_(video_game_genre)"),
        ("(https://a.b/page)", "https://a.b/page"),
        ("[shop](https://a.b/x?y=1).", "https://a.b/x?y=1"),
        ("https://a.b/c!", "https://a.b/c"),
    ],
)
def test_url_extraction_from_messages(message, url):
    assert dm._strip_url(dm.URL_RE.search(message).group(0)) == url


def test_upload_batches_respect_count_and_size():
    small = [(f"u{i}", b"x" * 10, "image/png") for i in range(12)]
    assert [len(b) for b in dm._upload_batches(small)] == [10, 2]
    huge = [("big", b"x" * (dm.UPLOAD_LIMIT_BYTES + 1), "video/mp4")]
    assert dm._upload_batches(huge) == []

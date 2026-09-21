"""DM feature: when someone sends a webpage link in private chat, send back its media."""

from __future__ import annotations

import asyncio
import io
import os
import re
from html.parser import HTMLParser
from typing import List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import aiohttp
import discord
from discord.ext import commands

URL_RE = re.compile(r"https?://[^\s<>)\]]+", re.IGNORECASE)

MEDIA_EXTS = (
    ".webp",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".mp4",
    ".webm",
    ".mov",
    ".m4v",
    ".avi",
    ".avif",
    ".bmp",
    ".svg",
    ".mkv",
    ".apng",
)

MEDIA_CONTENT_PREFIXES = (
    "image/",
    "video/",
)

SKIP_HOST_FRAGMENTS = (
    "facebook.com/tr",
    "google-analytics",
    "googletagmanager",
    "doubleclick.net",
    "scorecardresearch",
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; PuddingBot/1.0; +https://github.com/DarkSnakeGang/PuddingBot)"
)
MAX_PAGE_BYTES = 5 * 1024 * 1024
MAX_MEDIA_BYTES = 25 * 1024 * 1024
MAX_MEDIA_ITEMS = 25
MAX_PAGES = 1
FETCH_TIMEOUT = aiohttp.ClientTimeout(total=45)
FILES_PER_MESSAGE = 10


def message_has_http_url(content: str) -> bool:
    return bool(URL_RE.search(content or ""))


def _strip_url(raw: str) -> str:
    return (raw or "").rstrip(".,;:!?)>]}\"'" )


def _ext_of(url: str) -> str:
    try:
        path = urlparse(url).path.lower()
    except ValueError:
        return ""
    _root, ext = os.path.splitext(path)
    return ext


def _looks_like_media_url(url: str) -> bool:
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    lower = url.lower()
    if any(skip in lower for skip in SKIP_HOST_FRAGMENTS):
        return False
    ext = _ext_of(url)
    if ext in MEDIA_EXTS:
        return True
    # Query-string CDNs sometimes end with /image without extension; keep content-type check later
    return False


def _filename_for(url: str, content_type: str, index: int) -> str:
    path = urlparse(url).path
    name = os.path.basename(path) or f"media_{index}"
    name = re.sub(r"[^\w.\-]+", "_", name)[:80]
    if "." not in name:
        ct = (content_type or "").split(";")[0].strip().lower()
        ext_map = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/avif": ".avif",
            "image/bmp": ".bmp",
            "image/svg+xml": ".svg",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
        }
        name += ext_map.get(ct, ".bin")
    return name


class _MediaHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: List[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "img":
            for key in ("src", "data-src", "data-original", "data-lazy-src", "data-url"):
                if attr.get(key):
                    self.urls.append(attr[key])
            srcset = attr.get("srcset") or attr.get("data-srcset")
            if srcset:
                for part in srcset.split(","):
                    candidate = part.strip().split(" ")[0]
                    if candidate:
                        self.urls.append(candidate)
        elif tag in ("video", "source", "audio"):
            for key in ("src", "data-src"):
                if attr.get(key):
                    self.urls.append(attr[key])
        elif tag == "meta":
            prop = (attr.get("property") or attr.get("name") or "").lower()
            if prop in (
                "og:image",
                "og:image:url",
                "og:video",
                "og:video:url",
                "twitter:image",
                "twitter:image:src",
            ) and attr.get("content"):
                self.urls.append(attr["content"])
        elif tag == "link":
            rel = (attr.get("rel") or "").lower()
            href = attr.get("href") or ""
            if href and any(r in rel for r in ("image", "thumbnail", "preload", "icon")):
                self.urls.append(href)
            elif href and _looks_like_media_url(href):
                self.urls.append(href)
        elif tag == "a":
            href = attr.get("href") or ""
            if href and _looks_like_media_url(href):
                self.urls.append(href)


def extract_media_urls_from_html(base_url: str, html: str) -> List[str]:
    parser = _MediaHTMLParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass

    found: List[str] = []
    seen: Set[str] = set()

    def add(raw: str) -> None:
        if not raw or raw.startswith("data:"):
            return
        absolute = urljoin(base_url, raw.strip())
        absolute = _strip_url(absolute)
        if absolute in seen:
            return
        if not absolute.lower().startswith(("http://", "https://")):
            return
        lower = absolute.lower()
        if any(skip in lower for skip in SKIP_HOST_FRAGMENTS):
            return
        # Keep parser hits (og:image may lack an extension); content-type filters later
        seen.add(absolute)
        found.append(absolute)

    for raw in parser.urls:
        add(raw)

    # Also scrape any absolute media URLs embedded in the HTML text
    for match in re.finditer(
        r"https?://[^\s\"'<>]+?\.(?:webp|jpe?g|png|gif|mp4|webm|mov|m4v|avi|avif|bmp|svg|apng)(?:\?[^\s\"'<>]*)?",
        html,
        re.IGNORECASE,
    ):
        add(match.group(0))

    return found


async def _fetch_bytes(
    session: aiohttp.ClientSession, url: str, limit: int
) -> Tuple[bytes, str]:
    async with session.get(url, allow_redirects=True) as resp:
        if resp.status >= 400:
            raise ValueError(f"HTTP {resp.status}")
        content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        cl = resp.headers.get("Content-Length")
        if cl and int(cl) > limit:
            raise ValueError("too large")
        chunks: List[bytes] = []
        size = 0
        async for chunk in resp.content.iter_chunked(64 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError("too large")
            chunks.append(chunk)
        return b"".join(chunks), content_type


def _is_media_content_type(content_type: str, url: str) -> bool:
    ct = (content_type or "").lower()
    if any(ct.startswith(prefix) for prefix in MEDIA_CONTENT_PREFIXES):
        return True
    return _looks_like_media_url(url)


async def collect_media_from_url(
    session: aiohttp.ClientSession, page_url: str
) -> List[Tuple[str, bytes, str]]:
    """Return list of (url, bytes, content_type) for media found at/on page_url."""
    page_url = _strip_url(page_url)
    data, content_type = await _fetch_bytes(session, page_url, MAX_MEDIA_BYTES)

    # Direct media link
    if _is_media_content_type(content_type, page_url) and not content_type.startswith(
        "text/"
    ):
        return [(page_url, data, content_type)]

    if "html" not in content_type and not content_type.startswith("text/"):
        # Unknown binary that isn't clearly media
        if _looks_like_media_url(page_url):
            return [(page_url, data, content_type)]
        return []

    html = data.decode("utf-8", errors="replace")
    candidates = extract_media_urls_from_html(page_url, html)[: MAX_MEDIA_ITEMS * 3]

    results: List[Tuple[str, bytes, str]] = []
    for media_url in candidates:
        if len(results) >= MAX_MEDIA_ITEMS:
            break
        try:
            media_bytes, media_ct = await _fetch_bytes(
                session, media_url, MAX_MEDIA_BYTES
            )
        except Exception:
            continue
        if not _is_media_content_type(media_ct, media_url):
            continue
        if media_ct.startswith("text/"):
            continue
        results.append((media_url, media_bytes, media_ct))
    return results


class DmMedia(commands.Cog):
    """In DMs, scrape media from shared links and send the files back."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._busy: set[int] = set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is not None:
            return
        if message.id in self._busy:
            return

        urls = [_strip_url(m.group(0)) for m in URL_RE.finditer(message.content or "")]
        urls = list(dict.fromkeys(urls))[:MAX_PAGES]
        if not urls:
            return

        self._busy.add(message.id)
        status: Optional[discord.Message] = None
        try:
            status = await message.channel.send("Fetching media from that link…")
            headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
            async with aiohttp.ClientSession(
                headers=headers, timeout=FETCH_TIMEOUT
            ) as session:
                all_media: List[Tuple[str, bytes, str]] = []
                seen_urls: Set[str] = set()
                for page_url in urls:
                    try:
                        found = await collect_media_from_url(session, page_url)
                    except Exception as error:
                        await message.channel.send(
                            f"Could not open `{page_url}`: {error}"
                        )
                        continue
                    for item in found:
                        if item[0] in seen_urls:
                            continue
                        seen_urls.add(item[0])
                        all_media.append(item)
                        if len(all_media) >= MAX_MEDIA_ITEMS:
                            break
                    if len(all_media) >= MAX_MEDIA_ITEMS:
                        break

            if not all_media:
                if status:
                    await status.edit(content="No images or videos found on that page.")
                return

            # Send in batches; delete status after first successful send
            sent_any = False
            for start in range(0, len(all_media), FILES_PER_MESSAGE):
                batch = all_media[start : start + FILES_PER_MESSAGE]
                files: List[discord.File] = []
                for i, (url, blob, ct) in enumerate(batch, start=start + 1):
                    filename = _filename_for(url, ct, i)
                    files.append(discord.File(io.BytesIO(blob), filename=filename))
                await message.channel.send(files=files)
                sent_any = True

            if status and sent_any:
                try:
                    await status.delete()
                except Exception:
                    pass
            elif status:
                await status.edit(content=f"Found {len(all_media)} media file(s).")
        except Exception as error:
            print(f"[dm-media] Failed: {error}")
            if status:
                try:
                    await status.edit(content=f"Failed to fetch media: {error}")
                except Exception:
                    pass
        finally:
            self._busy.discard(message.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(DmMedia(bot))

"""DM feature: when someone sends a webpage link in private chat, send back its media."""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import aiohttp
import discord
from discord.ext import commands
from PIL import Image

import net_safety

URL_RE = re.compile(r"https?://[^\s<>\]]+", re.IGNORECASE)

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
    ".mkv",
    ".apng",
)

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv"}

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
# Discord rejects larger uploads, so don't download anything bigger
UPLOAD_LIMIT_BYTES = int(os.getenv("DM_UPLOAD_LIMIT_BYTES", str(10 * 1024 * 1024)))
MAX_MEDIA_BYTES = min(25 * 1024 * 1024, UPLOAD_LIMIT_BYTES)
MAX_JOB_BYTES = 100 * 1024 * 1024
MAX_MEDIA_ITEMS = 25
MAX_PAGES = 1
FETCH_TIMEOUT = aiohttp.ClientTimeout(total=45)
JOB_TIMEOUT_SECONDS = 120
MAX_CONCURRENT_JOBS = 2
FILES_PER_MESSAGE = 10
# Page scrapes: distinct images to try, downloads in flight, and the icon cutoff
MAX_FAMILIES_TRIED = MAX_MEDIA_ITEMS * 3
FETCH_CONCURRENCY = 4
MIN_IMAGE_SIDE = 100
# Never media on a scraped page (SVGs there are logos/icons/flags)
_SKIP_EXTS = {
    ".css", ".js", ".mjs", ".json", ".map", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".ico", ".svg", ".xml", ".txt", ".html", ".htm", ".php",
}
# Priority of where a URL was found: page preview image, then videos, then the rest
RANK_META, RANK_VIDEO, RANK_OTHER = 0, 1, 2
# Unknown-size images sort between small thumbnails and big hero images
UNKNOWN_SIZE_HINT = 800

# Query keys that usually mean a resized/thumbnail CDN variant
_SIZE_QUERY_KEYS = {
    "w",
    "h",
    "width",
    "height",
    "size",
    "resize",
    "fit",
    "crop",
    "quality",
    "q",
    "w_",
    "h_",
    "maxwidth",
    "maxheight",
    "imgmax",
}
_THUMB_PATH_RE = re.compile(
    r"/(?:thumbs?|thumbnails?|small|tiny|icons?|resized?)/", re.IGNORECASE
)
_SIZE_SUFFIX_RE = re.compile(
    r"[-_](?:\d{2,4}x\d{2,4}|\d{2,4}w|thumb|small|tiny|medium|icon|preview)(?=\.|$)",
    re.IGNORECASE,
)


# Resize suffix at the end of a filename stem: -300x200, _300x (Shopify), _x300, -800w
_SIZE_IN_NAME_RE = re.compile(r"[-_](?:(\d{2,4})x(\d{2,4})?|x(\d{2,4})|(\d{2,4})w)$")
# Wikimedia thumbnails: /wikipedia/<project>/thumb/a/ab/Name.jpg/250px-Name.jpg
_WIKIMEDIA_THUMB_RE = re.compile(r"^(/wikipedia/[^/]+)/thumb/(.+?)/[^/]+$")


def _canonical_location(netloc: str, path: str) -> Tuple[str, str]:
    """Map known CDN thumbnail locations to the original file's host and path."""
    match = _WIKIMEDIA_THUMB_RE.match(path)
    if match and netloc.lower().endswith("wikimedia.org"):
        return "upload.wikimedia.org", f"{match.group(1)}/{match.group(2)}"
    return netloc, path


def _keep_query_key(key: str) -> bool:
    key = key.lower()
    return key not in _SIZE_QUERY_KEYS and not key.startswith("utm_")


def message_has_http_url(content: str) -> bool:
    return bool(URL_RE.search(content or ""))


def _strip_url(raw: str) -> str:
    """Drop trailing punctuation; keep ')' that closes a '(' inside the URL (wiki links)."""
    url = (raw or "").rstrip(".,;:!?>]}\"'")
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1].rstrip(".,;:!?>]}\"'")
    return url


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
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
        }
        name += ext_map.get(ct, ".bin")
    return name


def _media_family_key(url: str) -> str:
    """Collapse thumbnail/full CDN variants of the same asset to one key."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url.lower()
    netloc, path = _canonical_location(parsed.netloc, parsed.path or "")
    path = _THUMB_PATH_RE.sub("/", path)
    root, ext = os.path.splitext(path)
    root = _SIZE_SUFFIX_RE.sub("", root)
    path = root + ext.lower()
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if _keep_query_key(k)
    ]
    query = urlencode(query_pairs)
    return urlunparse(
        (parsed.scheme.lower(), netloc.lower(), path, "", query, "")
    )


def _image_dims(blob: bytes) -> Optional[Tuple[int, int]]:
    try:
        with Image.open(io.BytesIO(blob)) as img:
            return int(img.width), int(img.height)
    except Exception:
        # Includes DecompressionBombError for absurd dimensions
        return None


def _image_pixel_area(blob: bytes) -> Optional[int]:
    dims = _image_dims(blob)
    return dims[0] * dims[1] if dims else None


def _size_hint(url: str) -> int:
    """Largest pixel size a URL asks for (width=1500, -300x200.jpg, ...); 0 if none."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return 0
    hints = [
        int(value)
        for key, value in parse_qsl(parsed.query)
        if key.lower() in _SIZE_QUERY_KEYS and value.isdigit()
    ]
    match = _SIZE_IN_NAME_RE.search(os.path.splitext(parsed.path)[0])
    if match:
        hints.extend(int(group) for group in match.groups() if group)
    match = re.search(r"/(\d{2,4})px-[^/]+$", parsed.path)
    if match:
        hints.append(int(match.group(1)))
    return max(hints, default=0)


def _full_size_url(url: str) -> str:
    """Same asset without resize params / NxN filename suffix (CDNs then serve the original)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    netloc, path = _canonical_location(parsed.netloc, parsed.path)
    root, ext = os.path.splitext(path)
    root = _SIZE_IN_NAME_RE.sub("", root) if ext else root
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if _keep_query_key(k)
        ]
    )
    return urlunparse(parsed._replace(netloc=netloc, path=root + ext, query=query))


def prefer_full_over_thumbnails(
    items: List[Tuple[str, bytes, str]],
) -> List[Tuple[str, bytes, str]]:
    """Drop small/thumbnail variants when a larger version of the same image exists.

    Groups by URL family (size query params / thumb path / NxN suffixes stripped).
    Within a family, keeps the largest image by pixel area (then by bytes).
    Exact byte duplicates are also collapsed. Videos are kept as-is.
    """
    if len(items) <= 1:
        return items

    # Exact payload dedupe (same file, different URL)
    by_hash: Dict[str, Tuple[int, str, bytes, str]] = {}
    hash_order: List[str] = []
    for index, (url, blob, ct) in enumerate(items):
        digest = hashlib.sha1(blob).hexdigest()
        if digest not in by_hash:
            by_hash[digest] = (index, url, blob, ct)
            hash_order.append(digest)
    deduped = [by_hash[d][1:] for d in hash_order]

    best_by_family: Dict[str, Tuple[int, int, int, str, bytes, str]] = {}
    # score_area, byte_len, original_index, url, blob, ct
    for index, (url, blob, ct) in enumerate(deduped):
        is_image = (ct or "").lower().startswith("image/")
        if is_image:
            family = _media_family_key(url)
            area = _image_pixel_area(blob)
            score = area if area is not None else len(blob)
        else:
            # Don't collapse videos/other against images
            family = f"unique:{index}:{url}"
            score = len(blob)
        candidate = (score, len(blob), index, url, blob, ct)
        current = best_by_family.get(family)
        if current is None or candidate[:2] > current[:2]:
            best_by_family[family] = candidate

    winners = sorted(best_by_family.values(), key=lambda row: row[2])
    return [(url, blob, ct) for _score, _nbytes, _idx, url, blob, ct in winners]


class _MediaHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # (raw url, srcset width descriptor or 0, RANK_*)
        self.entries: List[Tuple[str, int, int]] = []

    def _add(self, raw: str, width: int = 0, rank: int = RANK_OTHER) -> None:
        if raw:
            self.entries.append((raw, width, rank))

    def _add_srcset(self, srcset: str) -> None:
        for part in srcset.split(","):
            bits = part.strip().split()
            if not bits:
                continue
            descriptor = bits[1].lower() if len(bits) > 1 else ""
            width = int(descriptor[:-1]) if descriptor.endswith("w") and descriptor[:-1].isdigit() else 0
            self._add(bits[0], width)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "img":
            for key in ("src", "data-src", "data-original", "data-lazy-src", "data-url"):
                self._add(attr.get(key, ""))
            self._add_srcset(attr.get("srcset") or attr.get("data-srcset") or "")
        elif tag in ("video", "source", "audio"):
            for key in ("src", "data-src"):
                self._add(attr.get(key, ""), rank=RANK_VIDEO if tag != "audio" else RANK_OTHER)
            self._add_srcset(attr.get("srcset") or "")
        elif tag == "meta":
            prop = (attr.get("property") or attr.get("name") or "").lower()
            if prop in (
                "og:image",
                "og:image:url",
                "og:video",
                "og:video:url",
                "twitter:image",
                "twitter:image:src",
            ):
                self._add(attr.get("content", ""), rank=RANK_META)
        elif tag == "link":
            rel = (attr.get("rel") or "").lower()
            href = attr.get("href") or ""
            if href and any(r in rel for r in ("image", "thumbnail", "preload", "icon")):
                self._add(href)
            elif href and _looks_like_media_url(href):
                self._add(href)
        elif tag == "a":
            href = attr.get("href") or ""
            if href and _looks_like_media_url(href):
                self._add(href)


def _extract_media_entries(base_url: str, html: str) -> List[Tuple[str, int, int]]:
    """Absolute candidate URLs in page order as (url, size hint, rank)."""
    parser = _MediaHTMLParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass

    found: Dict[str, Tuple[int, int]] = {}

    def add(raw: str, width: int, rank: int) -> None:
        if not raw or raw.startswith("data:"):
            return
        absolute = _strip_url(urljoin(base_url, raw.strip()))
        if not absolute.lower().startswith(("http://", "https://")):
            return
        lower = absolute.lower()
        if any(skip in lower for skip in SKIP_HOST_FRAGMENTS):
            return
        # Keep parser hits (og:image may lack an extension); content-type filters later
        hint = max(width, _size_hint(absolute))
        old = found.get(absolute)
        found[absolute] = (max(hint, old[0]), min(rank, old[1])) if old else (hint, rank)

    for raw, width, rank in parser.entries:
        add(raw, width, rank)

    # Also scrape any absolute media URLs embedded in the HTML text
    for match in re.finditer(
        r"https?://[^\s\"'<>]{1,2048}?\.(?:webp|jpe?g|png|gif|mp4|webm|mov|m4v|avi|avif|bmp|apng)(?:\?[^\s\"'<>]{0,2048})?",
        html,
        re.IGNORECASE,
    ):
        add(match.group(0), 0, RANK_VIDEO if _ext_of(match.group(0)) in VIDEO_EXTS else RANK_OTHER)

    return [(url, hint, rank) for url, (hint, rank) in found.items()]


def extract_media_urls_from_html(base_url: str, html: str) -> List[str]:
    return [url for url, _hint, _rank in _extract_media_entries(base_url, html)]


def plan_media_fetches(base_url: str, html: str) -> List[List[str]]:
    """One URL list per distinct asset, most important asset first.

    Each list tries the full-size URL (resize params stripped) and then the
    largest variants the page offered, in case the CDN rejects the bare URL.
    """
    families: Dict[str, Dict] = {}
    for order, (url, hint, rank) in enumerate(_extract_media_entries(base_url, html)):
        if _ext_of(url) in _SKIP_EXTS:
            continue
        family = families.setdefault(
            _media_family_key(url), {"rank": rank, "order": order, "variants": []}
        )
        family["rank"] = min(family["rank"], rank)
        family["variants"].append((hint, url))

    ranked = []
    for family in families.values():
        variants = sorted(family["variants"], key=lambda v: -v[0])
        attempts = list(dict.fromkeys([_full_size_url(variants[0][1])] + [u for _, u in variants]))
        best = variants[0][0] or UNKNOWN_SIZE_HINT
        ranked.append(((family["rank"], -best, family["order"]), attempts[:3]))
    ranked.sort(key=lambda row: row[0])
    return [attempts for _key, attempts in ranked]


async def _fetch_bytes(
    session: aiohttp.ClientSession, url: str, limit: int
) -> Tuple[bytes, str]:
    _final_url, content_type, data = await net_safety.fetch_bytes_async(
        session, url, max_bytes=limit
    )
    return data, content_type


def _is_media_content_type(content_type: str, url: str) -> bool:
    ct = (content_type or "").lower()
    # Discord shows SVG files as source code, not images
    if "svg" in ct or _ext_of(url) == ".svg":
        return False
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

    html = data[:MAX_PAGE_BYTES].decode("utf-8", errors="replace")
    plans = (await asyncio.to_thread(plan_media_fetches, page_url, html))[:MAX_FAMILIES_TRIED]

    async def fetch_best(attempts: List[str], limit: int) -> Optional[Tuple[str, bytes, str]]:
        for media_url in attempts:
            try:
                media_bytes, media_ct = await _fetch_bytes(session, media_url, limit)
            except Exception:
                continue
            ct = (media_ct or "").lower()
            if ct.startswith("text/") or not _is_media_content_type(ct, media_url):
                continue
            if ct.startswith("image/"):
                dims = await asyncio.to_thread(_image_dims, media_bytes)
                if dims and max(dims) < MIN_IMAGE_SIDE:
                    return None  # icon/sprite; the other variants are no bigger
            return media_url, media_bytes, media_ct
        return None

    results: List[Tuple[str, bytes, str]] = []
    job_bytes = len(data)
    for start in range(0, len(plans), FETCH_CONCURRENCY):
        remaining = MAX_JOB_BYTES - job_bytes
        if len(results) >= MAX_MEDIA_ITEMS or remaining <= 0:
            break
        chunk = plans[start : start + FETCH_CONCURRENCY]
        limit = min(MAX_MEDIA_BYTES, remaining // len(chunk))
        for item in await asyncio.gather(*(fetch_best(a, limit) for a in chunk)):
            if item:
                job_bytes += len(item[1])
                results.append(item)
    best = await asyncio.to_thread(prefer_full_over_thumbnails, results)
    return best[:MAX_MEDIA_ITEMS]


def _upload_batches(
    items: List[Tuple[str, bytes, str]],
) -> List[List[Tuple[int, str, bytes, str]]]:
    """Group files so each message stays under the file-count and upload-size limits."""
    batches: List[List[Tuple[int, str, bytes, str]]] = []
    current: List[Tuple[int, str, bytes, str]] = []
    size = 0
    for index, (url, blob, ct) in enumerate(items, start=1):
        if len(blob) > UPLOAD_LIMIT_BYTES:
            continue
        if current and (len(current) >= FILES_PER_MESSAGE or size + len(blob) > UPLOAD_LIMIT_BYTES):
            batches.append(current)
            current, size = [], 0
        current.append((index, url, blob, ct))
        size += len(blob)
    if current:
        batches.append(current)
    return batches


class DmMedia(commands.Cog):
    """In DMs, scrape media from shared links and send the files back."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._busy_users: set[int] = set()
        self._slots = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is not None:
            return

        urls = [_strip_url(m.group(0)) for m in URL_RE.finditer(message.content or "")]
        urls = list(dict.fromkeys(urls))[:MAX_PAGES]
        if not urls:
            return
        if message.author.id in self._busy_users:
            await message.channel.send("Still working on your last link, hang on.")
            return

        self._busy_users.add(message.author.id)
        status: Optional[discord.Message] = None
        try:
            status = await message.channel.send("Fetching media from that link…")
            async with self._slots:
                all_media = await asyncio.wait_for(
                    self._collect(message, urls), timeout=JOB_TIMEOUT_SECONDS
                )

            if not all_media:
                if status:
                    await status.edit(content="No images or videos found on that page.")
                return

            # Send in batches; delete status after first successful send
            sent_any = False
            for batch in _upload_batches(all_media):
                files = [
                    discord.File(io.BytesIO(blob), filename=_filename_for(url, ct, i))
                    for i, url, blob, ct in batch
                ]
                await message.channel.send(files=files)
                sent_any = True

            if status and sent_any:
                try:
                    await status.delete()
                except Exception:
                    pass
            elif status:
                await status.edit(content="The media on that page is too large to upload here.")
        except asyncio.TimeoutError:
            if status:
                try:
                    await status.edit(content="That page took too long to process.")
                except Exception:
                    pass
        except Exception as error:
            print(f"[dm-media] Failed: {type(error).__name__}: {error}")
            if status:
                try:
                    await status.edit(content="Failed to fetch media from that link.")
                except Exception:
                    pass
        finally:
            self._busy_users.discard(message.author.id)

    async def _collect(
        self, message: discord.Message, urls: List[str]
    ) -> List[Tuple[str, bytes, str]]:
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        all_media: List[Tuple[str, bytes, str]] = []
        seen_urls: Set[str] = set()
        async with net_safety.public_session(headers=headers, timeout=FETCH_TIMEOUT) as session:
            for page_url in urls:
                try:
                    found = await collect_media_from_url(session, page_url)
                except net_safety.UnsafeURL as error:
                    await message.channel.send(f"Could not open that link: {error}")
                    continue
                except net_safety.TooLarge:
                    await message.channel.send("That file is too large to send here.")
                    continue
                except Exception as error:
                    print(f"[dm-media] Could not open {page_url}: {type(error).__name__}: {error}")
                    await message.channel.send("Could not open that link.")
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
        return await asyncio.to_thread(prefer_full_over_thumbnails, all_media)


async def setup(bot: commands.Bot):
    await bot.add_cog(DmMedia(bot))

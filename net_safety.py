"""Guards for fetching user-supplied URLs: public hosts only, bounded size and time."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import aiohttp
import requests
from aiohttp.abc import AbstractResolver

MAX_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_CHUNK = 64 * 1024


class UnsafeURL(ValueError):
    """URL is not a public http(s) address. The message is safe to show users."""


class TooLarge(ValueError):
    """Response body exceeded the byte cap."""


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def check_url(url: str) -> None:
    """Raise UnsafeURL unless `url` is http(s) and every address its host resolves to is public."""
    try:
        parsed = urlparse(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise UnsafeURL("That link is not a valid URL.") from None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeURL("Only http(s) links are supported.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise UnsafeURL("Could not resolve that link's host.") from None
    if not infos or not all(_ip_is_public(info[4][0]) for info in infos):
        raise UnsafeURL("That link points to a private or local address.")


async def check_url_async(url: str) -> None:
    await asyncio.to_thread(check_url, url)


def fetch_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout: float = 20.0,
    headers: Optional[Dict[str, str]] = None,
    truncate: bool = False,
) -> Tuple[str, str, bytes]:
    """Blocking GET with per-hop URL checks. Returns (final_url, content_type, body).

    Over `max_bytes`: raise TooLarge, or return the first `max_bytes` if `truncate`.
    """
    deadline = time.monotonic() + timeout
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Timed out fetching that link.")
        with requests.get(
            url, headers=headers, timeout=remaining, stream=True, allow_redirects=False
        ) as resp:
            location = resp.headers.get("Location")
            if resp.status_code in _REDIRECT_STATUSES and location:
                url = urljoin(url, location)
                continue
            resp.raise_for_status()
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            declared = resp.headers.get("Content-Length") or ""
            if not truncate and declared.isdigit() and int(declared) > max_bytes:
                raise TooLarge("That file is too large.")
            body = bytearray()
            for chunk in resp.iter_content(_CHUNK):
                body += chunk
                if len(body) > max_bytes:
                    if truncate:
                        del body[max_bytes:]
                        break
                    raise TooLarge("That file is too large.")
                if time.monotonic() > deadline:
                    raise TimeoutError("Timed out fetching that link.")
            return url, content_type, bytes(body)
    raise UnsafeURL("That link redirects too many times.")


class _PublicResolver(AbstractResolver):
    """Refuse to connect to non-public addresses (also covers DNS rebinding between checks)."""

    def __init__(self) -> None:
        self._inner = aiohttp.ThreadedResolver()

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET) -> List[Dict[str, Any]]:
        infos = await self._inner.resolve(host, port, family)
        if not infos or not all(_ip_is_public(info["host"]) for info in infos):
            raise UnsafeURL("That link points to a private or local address.")
        return infos

    async def close(self) -> None:
        await self._inner.close()


def public_session(**kwargs: Any) -> aiohttp.ClientSession:
    """aiohttp session that can only connect to public addresses."""
    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=_PublicResolver()), **kwargs)


async def fetch_bytes_async(
    session: aiohttp.ClientSession,
    url: str,
    *,
    max_bytes: int,
    timeout: float = 30.0,
    truncate: bool = False,
) -> Tuple[str, str, bytes]:
    """Async GET with per-hop URL checks. Returns (final_url, content_type, body)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    for _ in range(MAX_REDIRECTS + 1):
        await check_url_async(url)
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("Timed out fetching that link.")
        async with session.get(
            url, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=remaining)
        ) as resp:
            location = resp.headers.get("Location")
            if resp.status in _REDIRECT_STATUSES and location:
                url = urljoin(url, location)
                continue
            if resp.status >= 400:
                raise ValueError(f"HTTP {resp.status}")
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            declared = resp.headers.get("Content-Length") or ""
            if not truncate and declared.isdigit() and int(declared) > max_bytes:
                raise TooLarge("That file is too large.")
            body = bytearray()
            async for chunk in resp.content.iter_chunked(_CHUNK):
                body += chunk
                if len(body) > max_bytes:
                    if truncate:
                        del body[max_bytes:]
                        break
                    raise TooLarge("That file is too large.")
            return url, content_type, bytes(body)
    raise UnsafeURL("That link redirects too many times.")

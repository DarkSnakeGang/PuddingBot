"""ESMBot-style Select Image context menu and /caption slash command."""

from __future__ import annotations

import asyncio
import io
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from image_caption import caption_image

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
HISTORY_LIMIT = 50
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

# Per-user selected media: user_id -> {url, spoiler}
_selected_images: Dict[int, Dict] = {}


def _looks_like_image_url(url: str) -> bool:
    if not url:
        return False
    try:
        path = urlparse(url).path.lower()
    except ValueError:
        return False
    if any(path.endswith(ext) for ext in IMAGE_EXTS):
        return True
    host = urlparse(url).hostname or ""
    if host.endswith("discordapp.com") or host.endswith("discordapp.net"):
        return True
    if "tenor.com" in host or "giphy.com" in host:
        return True
    return False


def _media_from_attachment(att: discord.Attachment) -> Optional[Dict]:
    ct = (att.content_type or "").lower()
    name = (att.filename or "").lower()
    if ct.startswith("image/") or any(name.endswith(ext) for ext in IMAGE_EXTS):
        return {
            "url": att.proxy_url or att.url,
            "spoiler": bool(att.is_spoiler()),
        }
    return None


def _media_from_embed(embed: discord.Embed) -> Optional[Dict]:
    if embed.image and embed.image.url:
        return {"url": embed.image.url, "spoiler": False}
    if embed.thumbnail and embed.thumbnail.url:
        return {"url": embed.thumbnail.url, "spoiler": False}
    if embed.video and embed.video.url and embed.url:
        provider = (embed.provider.url if embed.provider else "") or ""
        if any(p in provider for p in ("tenor.com", "tenor.co", "giphy.com")):
            return {"url": embed.url, "spoiler": False}
        if _looks_like_image_url(embed.video.url):
            return {"url": embed.video.url, "spoiler": False}
    if embed.url and _looks_like_image_url(embed.url):
        return {"url": embed.url, "spoiler": False}
    return None


def extract_media_from_message(message: discord.Message) -> List[Dict]:
    """Collect image media from a single message (attachments then embeds)."""
    found: List[Dict] = []
    for att in message.attachments:
        media = _media_from_attachment(att)
        if media:
            found.append(media)
    for embed in message.embeds:
        media = _media_from_embed(embed)
        if media:
            found.append(media)
    if message.content:
        for match in re.finditer(r"https?://\S+", message.content):
            url = match.group(0).rstrip(")>\"'")
            if _looks_like_image_url(url):
                found.append({"url": url, "spoiler": False})
    return found


async def resolve_tenor_view_url(url: str) -> Optional[str]:
    """Best-effort: turn a tenor.com/view/... page into a direct media gif."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if "tenor.com" not in host:
        return url
    if "/view/" not in parsed.path:
        return url
    if host.startswith("media"):
        return url
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return url
                html = await resp.text()
        match = re.search(r"https://media\.tenor\.com/[^\s\"']+\.gif", html)
        if match:
            return match.group(0)
    except Exception:
        pass
    return url


async def download_image(url: str) -> bytes:
    url = await resolve_tenor_view_url(url) or url
    headers = {"User-Agent": "PuddingBot/1.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                raise ValueError(f"Failed to download image (HTTP {resp.status})")
            cl = resp.headers.get("Content-Length")
            if cl and int(cl) > MAX_DOWNLOAD_BYTES:
                raise ValueError("Image is too large to download")
            data = await resp.read()
            if len(data) > MAX_DOWNLOAD_BYTES:
                raise ValueError("Image is too large to download")
            return data


class ImageTools(commands.Cog):
    """Select Image + caption (ESMBot-style)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.select_image_menu = app_commands.ContextMenu(
            name="Select Image",
            callback=self.select_image,
        )
        self.bot.tree.add_command(self.select_image_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.select_image_menu.name,
            type=discord.AppCommandType.message,
        )

    async def select_image(
        self, interaction: discord.Interaction, message: discord.Message
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        media_list = extract_media_from_message(message)
        chosen = None
        for media in media_list:
            url = media.get("url") or ""
            if not url:
                continue
            if _looks_like_image_url(url) or "tenor.com" in url or "giphy.com" in url:
                chosen = media
                break
        if not chosen and media_list:
            chosen = media_list[0]
        if not chosen:
            await interaction.followup.send(
                "Couldn't find an image in that message.",
                ephemeral=True,
            )
            return

        _selected_images[interaction.user.id] = {
            "url": chosen["url"],
            "spoiler": bool(chosen.get("spoiler")),
        }
        await interaction.followup.send(
            "Image selected. Run `/caption` to caption it.",
            ephemeral=True,
        )

    async def _history_media(
        self, interaction: discord.Interaction
    ) -> Optional[Dict]:
        channel = interaction.channel
        if channel is None or not hasattr(channel, "history"):
            return None
        if interaction.guild and isinstance(channel, discord.abc.GuildChannel):
            perms = channel.permissions_for(interaction.guild.me)
            if perms and not perms.read_message_history:
                return None
        try:
            async for msg in channel.history(limit=HISTORY_LIMIT):
                found = extract_media_from_message(msg)
                if found:
                    return found[0]
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    async def _resolve_media(
        self,
        interaction: discord.Interaction,
        image: Optional[discord.Attachment],
        link: Optional[str],
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Return (media_dict, error_message)."""
        if image is not None:
            media = _media_from_attachment(image)
            if not media:
                return None, "That attachment isn't an image/GIF."
            return media, None

        if link:
            link = link.strip()
            if not link.startswith("http"):
                return None, "Link must be an http(s) URL."
            return {"url": link, "spoiler": False}, None

        selected = _selected_images.pop(interaction.user.id, None)
        if selected:
            return selected, None

        history = await self._history_media(interaction)
        if history:
            return history, None

        tip = (
            "No image found. Attach one, pass a link, right-click a message → "
            "**Apps → Select Image**, or post an image in this channel first."
        )
        return None, tip

    @app_commands.command(name="caption", description="Adds a caption to an image")
    @app_commands.describe(
        text="The text to put on the image",
        image="An image/GIF attachment",
        link="An image/GIF URL",
        spoiler="Attempt to send output as a spoiler",
        ephemeral="Attempt to send output as an ephemeral/temporary response",
    )
    async def caption_command(
        self,
        interaction: discord.Interaction,
        text: str,
        image: Optional[discord.Attachment] = None,
        link: Optional[str] = None,
        spoiler: Optional[bool] = False,
        ephemeral: Optional[bool] = False,
    ) -> None:
        if not (text or "").strip():
            await interaction.response.send_message(
                "You need to provide some text to add a caption!",
                ephemeral=True,
            )
            return

        use_ephemeral = bool(ephemeral)
        await interaction.response.defer(ephemeral=use_ephemeral)

        media, err = await self._resolve_media(interaction, image, link)
        if err or not media:
            await interaction.followup.send(err or "No image found.", ephemeral=True)
            return

        try:
            raw = await download_image(media["url"])
            out_bytes, ext = await asyncio.to_thread(caption_image, raw, text.strip())
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        except Exception as e:
            print(f"Caption failed: {e}")
            await interaction.followup.send(
                "Failed to caption that image. Try another image or format.",
                ephemeral=True,
            )
            return

        filename = f"{'SPOILER_' if spoiler or media.get('spoiler') else ''}caption.{ext}"
        file = discord.File(io.BytesIO(out_bytes), filename=filename)
        try:
            msg = await interaction.followup.send(file=file, wait=True)
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"Couldn't upload the captioned image: {e}",
                ephemeral=True,
            )
            return

        if msg and msg.attachments:
            att = msg.attachments[0]
            _selected_images[interaction.user.id] = {
                "url": att.proxy_url or att.url,
                "spoiler": bool(spoiler or media.get("spoiler")),
            }


async def setup(bot: commands.Bot):
    await bot.add_cog(ImageTools(bot))

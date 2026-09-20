"""Auto-convert MKV attachments to MP4 in the Google Snake Discord server."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from functools import lru_cache
from typing import Optional

import discord
from discord.ext import commands

# Google Snake server
MKV_AUTO_GUILD_ID = 723093146954760222
# Discord bot upload limit without nitro / boosts (bytes)
DEFAULT_UPLOAD_LIMIT = 25 * 1024 * 1024
CONVERT_TIMEOUT_SECONDS = 600


def _is_mkv_attachment(att: discord.Attachment) -> bool:
    name = (att.filename or "").lower()
    ct = (att.content_type or "").lower()
    if name.endswith(".mkv"):
        return True
    return "matroska" in ct or ct in ("video/x-matroska", "video/mkv")


def _upload_limit_for(guild: Optional[discord.Guild]) -> int:
    if guild is None:
        return DEFAULT_UPLOAD_LIMIT
    # discord.py FileSizeLimit / premium_tier boosts upload size
    limits = {
        0: 25 * 1024 * 1024,
        1: 25 * 1024 * 1024,
        2: 50 * 1024 * 1024,
        3: 100 * 1024 * 1024,
    }
    return limits.get(int(getattr(guild, "premium_tier", 0) or 0), DEFAULT_UPLOAD_LIMIT)


@lru_cache(maxsize=1)
def _ffmpeg_bin() -> str:
    """System ffmpeg if present, else the pip-bundled imageio-ffmpeg binary."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError(
            "ffmpeg is not available. Install the imageio-ffmpeg package "
            "(comes in via /update + requirements.txt)."
        ) from error
    return imageio_ffmpeg.get_ffmpeg_exe()


async def _run_ffmpeg(args: list[str]) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=CONVERT_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return -1, "ffmpeg timed out"
    err = (stderr or b"").decode("utf-8", errors="replace")[-2000:]
    return proc.returncode or 0, err


async def convert_mkv_to_mp4(src_path: str, dst_path: str) -> None:
    """Remux when possible; otherwise re-encode to H.264/AAC."""
    ffmpeg = _ffmpeg_bin()

    copy_args = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        src_path,
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        dst_path,
    ]
    code, err = await _run_ffmpeg(copy_args)
    if code == 0 and os.path.isfile(dst_path) and os.path.getsize(dst_path) > 0:
        return

    reencode_args = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        src_path,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        dst_path,
    ]
    code, err = await _run_ffmpeg(reencode_args)
    if code != 0 or not os.path.isfile(dst_path) or os.path.getsize(dst_path) <= 0:
        raise RuntimeError(err.strip() or "ffmpeg failed to produce an mp4")


class MkvConvert(commands.Cog):
    """Convert .mkv uploads to .mp4 in the Google Snake guild."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._busy: set[int] = set()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None or message.guild.id != MKV_AUTO_GUILD_ID:
            return
        if message.id in self._busy:
            return

        mkvs = [a for a in message.attachments if _is_mkv_attachment(a)]
        if not mkvs:
            return

        self._busy.add(message.id)
        try:
            for att in mkvs:
                await self._convert_one(message, att)
        finally:
            self._busy.discard(message.id)

    async def _convert_one(
        self, message: discord.Message, att: discord.Attachment
    ) -> None:
        status: Optional[discord.Message] = None
        try:
            status = await message.channel.send("Converting...")
        except Exception as error:
            print(f"[mkv-convert] Could not send status: {error}")
            return

        limit = _upload_limit_for(message.guild)
        if att.size and att.size > limit * 4:
            # Skip absurd downloads that cannot possibly fit after convert
            await self._fail(status, "That MKV is too large to convert for Discord upload.")
            return

        tmp_dir = tempfile.mkdtemp(prefix="mkv2mp4-")
        base = os.path.splitext(att.filename or "video")[0] or "video"
        # Keep filename Discord-safe
        safe_base = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in base)[:80]
        src_path = os.path.join(tmp_dir, f"{safe_base}.mkv")
        dst_path = os.path.join(tmp_dir, f"{safe_base}.mp4")

        try:
            await att.save(src_path)
            await convert_mkv_to_mp4(src_path, dst_path)

            out_size = os.path.getsize(dst_path)
            if out_size > limit:
                await self._fail(
                    status,
                    f"Converted MP4 is {out_size / (1024 * 1024):.1f} MB, "
                    f"over this server's {limit / (1024 * 1024):.0f} MB upload limit.",
                )
                return

            spoiler = bool(att.is_spoiler())
            file = discord.File(
                dst_path,
                filename=f"{safe_base}.mp4",
                spoiler=spoiler,
            )
            await message.channel.send(file=file)
            try:
                await status.delete()
            except Exception:
                pass
        except Exception as error:
            print(f"[mkv-convert] Failed on {att.filename}: {error}")
            await self._fail(status, f"Conversion failed: {error}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def _fail(self, status: Optional[discord.Message], text: str) -> None:
        if status is None:
            return
        try:
            await status.edit(content=text)
        except Exception:
            try:
                await status.delete()
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(MkvConvert(bot))

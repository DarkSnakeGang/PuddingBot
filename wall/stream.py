"""Discord send/edit stream for Wall All pattern solves."""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import sys
from typing import Awaitable, Callable, Optional

import discord

from . import PatternResult
from .worker import decode_result

FIRST_SOLVE_TIMEOUT = 45
# Hard cap on one solve (the closest-gap search is otherwise unbounded)
TOTAL_SOLVE_SECONDS = int(os.getenv("WALL_SOLVE_SECONDS", "180"))
MAX_CONCURRENT_SOLVES = int(os.getenv("WALL_MAX_SOLVES", "2"))
EDIT_INTERVAL_SECONDS = 1.5
MIN_PATTERN_CELLS = 80
_STREAM_LIMIT = 16 * 1024 * 1024
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_solve_slots = asyncio.Semaphore(MAX_CONCURRENT_SOLVES)

SendFn = Callable[[PatternResult], Awaitable[discord.Message]]
EditFn = Callable[[discord.Message, PatternResult], Awaitable[None]]

BUSY_MESSAGE = "The wall solver is busy with other patterns right now. Try again in a minute."
FAILED_MESSAGE = "Failed to solve that pattern."
TIMEOUT_MESSAGE = (
    f"Solve timed out after {FIRST_SOLVE_TIMEOUT}s. "
    "Try a different pattern (or one with more walls)."
)


class SolverBusy(Exception):
    """All solver slots are in use."""


def pattern_input_error(cleaned: str) -> Optional[str]:
    """User-facing reason a cleaned grid can't be solved, or None if it's fine."""
    if len(cleaned) != 90:
        return (
            "Small board only: send exactly 90 cells of `0`/`1` or `1`/`2`. "
            f"Got **{len(cleaned)}** after stripping other characters."
        )
    if len(set(cleaned)) > 2:
        return "Use exactly two cell values (`0`/`1` or `1`/`2`), not all three."
    return None


def pattern_file(result: PatternResult) -> Optional[discord.File]:
    if not result.png:
        return None
    # Unique name so Discord CDN does not reuse a cached older attachment.
    digest = hashlib.sha1(result.png).hexdigest()[:10]
    return discord.File(io.BytesIO(result.png), filename=f"wallall-{digest}.png")


def _content(result: PatternResult) -> str:
    text = result.content or ""
    if len(text) > 1900:
        return text[:1900] + "\n…(truncated)"
    return text


async def send_pattern_message(target, result: PatternResult) -> discord.Message:
    file = pattern_file(result)
    if file:
        return await target.send(_content(result), file=file)
    return await target.send(_content(result))


async def edit_pattern_message(message: discord.Message, result: PatternResult) -> None:
    if result.retain_image:
        await message.edit(content=_content(result))
        return
    file = pattern_file(result)
    if file:
        await message.edit(content=_content(result), attachments=[file])
    else:
        await message.edit(content=_content(result), attachments=[])


def _merge(pending: Optional[PatternResult], item: PatternResult) -> PatternResult:
    """Coalesce updates; a text-only update must not drop a newer board image."""
    if pending is not None and item.retain_image and not pending.retain_image:
        return PatternResult(content=item.content, png=pending.png, retain_image=False)
    return item


async def _pump(proc: asyncio.subprocess.Process, queue: asyncio.Queue) -> None:
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                queue.put_nowait(decode_result(line))
            except RuntimeError as error:
                queue.put_nowait(error)
            except ValueError:
                continue
    finally:
        queue.put_nowait(None)


async def stream_pattern_solve(
    cleaned: str,
    send: SendFn,
    edit: EditFn,
) -> None:
    """Solve in a killable child process, editing one Discord message as the gap improves.

    Raises SolverBusy, asyncio.TimeoutError (nothing found in time) or RuntimeError.
    """
    if _solve_slots.locked():
        raise SolverBusy()
    async with _solve_slots:
        await _run_solve(cleaned, send, edit)


async def _run_solve(cleaned: str, send: SendFn, edit: EditFn) -> None:
    loop = asyncio.get_running_loop()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "wall.worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        cwd=_PROJECT_ROOT,
        limit=_STREAM_LIMIT,
    )
    proc.stdin.write(cleaned.encode("ascii"))
    await proc.stdin.drain()
    proc.stdin.close()

    queue: asyncio.Queue = asyncio.Queue()
    pump = asyncio.create_task(_pump(proc, queue))
    started = loop.time()
    deadline = started + TOTAL_SOLVE_SECONDS
    message: Optional[discord.Message] = None
    last_sent: Optional[PatternResult] = None
    pending: Optional[PatternResult] = None
    last_flush = 0.0
    error: Optional[Exception] = None
    stopped_early = False
    try:
        while True:
            limit = deadline if last_sent or pending else min(deadline, started + FIRST_SOLVE_TIMEOUT)
            timeout = limit - loop.time()
            if pending is not None:
                timeout = min(timeout, last_flush + EDIT_INTERVAL_SECONDS - loop.time())
            try:
                item = await asyncio.wait_for(queue.get(), max(0.0, timeout))
            except asyncio.TimeoutError:
                item = False
            done = item is None
            if isinstance(item, Exception):
                error, done = item, True
            elif isinstance(item, PatternResult):
                pending = _merge(pending, item)

            if pending is not None and (
                done or message is None or loop.time() - last_flush >= EDIT_INTERVAL_SECONDS
            ):
                try:
                    if message is None:
                        message = await send(pending)
                    else:
                        await edit(message, pending)
                except discord.NotFound:
                    break
                except discord.HTTPException as http_error:
                    print(f"[wall] Failed to update solve message: {http_error}")
                last_sent = _merge(last_sent, pending)
                pending = None
                last_flush = loop.time()

            if done:
                break
            if loop.time() >= limit:
                stopped_early = True
                break
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        pump.cancel()

    if error is not None and message is None:
        raise error
    if stopped_early:
        if message is None:
            raise asyncio.TimeoutError()
        note = f"\n⏱️ Stopped searching after {TOTAL_SOLVE_SECONDS}s; best result found is shown."
        try:
            await edit(message, PatternResult(content=_content(last_sent) + note, retain_image=True))
        except discord.HTTPException:
            pass

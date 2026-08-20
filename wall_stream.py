"""Discord send/edit stream for Wall All pattern solves."""

from __future__ import annotations

import asyncio
import io
from typing import Awaitable, Callable, Optional

import discord

import wall

FIRST_SOLVE_TIMEOUT = 45
IMPROVE_WAIT_TIMEOUT = 105  # 90s Board-tab improve + render slack

SendFn = Callable[[wall.PatternResult], Awaitable[discord.Message]]
EditFn = Callable[[discord.Message, wall.PatternResult], Awaitable[None]]


def pattern_file(result: wall.PatternResult) -> Optional[discord.File]:
    if not result.png:
        return None
    return discord.File(io.BytesIO(result.png), filename="wallall.png")


def _content(result: wall.PatternResult) -> str:
    text = result.content or ""
    if len(text) > 1900:
        return text[:1900] + "\n…(truncated)"
    return text


async def send_pattern_message(target, result: wall.PatternResult) -> discord.Message:
    file = pattern_file(result)
    if file:
        return await target.send(_content(result), file=file)
    return await target.send(_content(result))


async def edit_pattern_message(message: discord.Message, result: wall.PatternResult) -> None:
    file = pattern_file(result)
    if file:
        await message.edit(content=_content(result), attachments=[file])
    else:
        await message.edit(content=_content(result), attachments=[])


async def stream_pattern_solve(
    cleaned: str,
    send: SendFn,
    edit: EditFn,
) -> None:
    """Run the solver in a thread and update the Discord message as the gap improves."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_update(result: wall.PatternResult) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, result)

    def work() -> None:
        try:
            wall.solve_pattern(cleaned, on_update=on_update)
        except Exception as error:
            loop.call_soon_threadsafe(queue.put_nowait, error)
        else:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    worker = asyncio.create_task(asyncio.to_thread(work))
    message = None
    first = True
    timed_out = False
    try:
        while True:
            timeout = FIRST_SOLVE_TIMEOUT if first else IMPROVE_WAIT_TIMEOUT
            try:
                item = await asyncio.wait_for(queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                timed_out = True
                break
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            first = False
            if message is None:
                message = await send(item)
            else:
                await edit(message, item)
    finally:
        await worker
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is None or isinstance(item, Exception):
                continue
            if message is None:
                message = await send(item)
            else:
                await edit(message, item)
    if timed_out and message is None:
        raise asyncio.TimeoutError()

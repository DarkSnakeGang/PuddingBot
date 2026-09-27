"""Keep embeds inside Discord's size limits instead of failing with HTTP 400."""

from __future__ import annotations

import functools
from typing import Callable, List, Optional

import discord

TITLE_MAX = 256
DESCRIPTION_MAX = 4096
FIELD_NAME_MAX = 256
FIELD_VALUE_MAX = 1024
FOOTER_MAX = 2048
AUTHOR_MAX = 256
FIELDS_MAX = 25
TOTAL_MAX = 6000
EMBEDS_PER_MESSAGE = 10
BLANK = "\u200b"


def _truncate(text: Optional[str], limit: int) -> Optional[str]:
    if text is None:
        return None
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def split_value(value: str, limit: int = FIELD_VALUE_MAX) -> List[str]:
    """Split on line boundaries into chunks of at most `limit` characters."""
    chunks: List[str] = []
    current = ""
    for line in str(value).split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()] or [BLANK]


def fit_embed(embed: discord.Embed) -> discord.Embed:
    """Truncate/split an embed in place so Discord accepts it."""
    if embed.title:
        embed.title = _truncate(embed.title, TITLE_MAX)
    if embed.description:
        embed.description = _truncate(embed.description, DESCRIPTION_MAX)
    if embed.footer and embed.footer.text and len(embed.footer.text) > FOOTER_MAX:
        embed.set_footer(text=_truncate(embed.footer.text, FOOTER_MAX), icon_url=embed.footer.icon_url)
    if embed.author and embed.author.name and len(embed.author.name) > AUTHOR_MAX:
        embed.set_author(
            name=_truncate(embed.author.name, AUTHOR_MAX),
            url=embed.author.url,
            icon_url=embed.author.icon_url,
        )

    fields = []
    for field in embed.fields:
        name = field.name or BLANK
        value = str(field.value) if field.value else BLANK
        for i, chunk in enumerate(split_value(value)):
            label = name if i == 0 else f"{name} (cont.)"
            fields.append((_truncate(label, FIELD_NAME_MAX), chunk, field.inline))
    if len(fields) > FIELDS_MAX:
        omitted = len(fields) - (FIELDS_MAX - 1)
        fields = fields[: FIELDS_MAX - 1] + [("…", f"{omitted} more section(s) not shown", False)]

    embed.clear_fields()
    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)

    trimmed = False
    while len(embed) > TOTAL_MAX and embed.fields:
        embed.remove_field(len(embed.fields) - 1)
        trimmed = True
    if len(embed) > TOTAL_MAX and embed.description:
        overflow = len(embed) - TOTAL_MAX
        embed.description = _truncate(embed.description, max(1, len(embed.description) - overflow))
    note = ("…", "Output truncated to fit Discord's limits.", False)
    if trimmed and len(embed.fields) < FIELDS_MAX and len(embed) + len(note[0]) + len(note[1]) <= TOTAL_MAX:
        embed.add_field(name=note[0], value=note[1], inline=note[2])
    return embed


def fit_embeds(func: Callable) -> Callable:
    """Decorator: run `fit_embed` on an Embed (or list of Embeds) a builder returns."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if isinstance(result, discord.Embed):
            return fit_embed(result)
        if isinstance(result, list):
            return [fit_embed(e) if isinstance(e, discord.Embed) else e for e in result]
        return result

    return wrapper


def group_embeds(embeds: List[discord.Embed]) -> List[List[discord.Embed]]:
    """Pack embeds into messages that respect the per-message 6000-char / 10-embed limits."""
    groups: List[List[discord.Embed]] = []
    current: List[discord.Embed] = []
    size = 0
    for embed in embeds:
        length = len(embed)
        if current and (size + length > TOTAL_MAX or len(current) >= EMBEDS_PER_MESSAGE):
            groups.append(current)
            current, size = [], 0
        current.append(embed)
        size += length
    if current:
        groups.append(current)
    return groups

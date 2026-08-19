"""Slash command for the small-board Wall All ham-cycle solver."""

from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import wall
import wall_stream

SOLVE_TIMEOUT_SECONDS = wall_stream.FIRST_SOLVE_TIMEOUT


class WallAll(commands.Cog):
    """Small-board Wall All pattern solver."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="wallall",
        description="Solve a small-board Wall All Ham Cycle or Ham Path (90-cell 0/1 or 1/2 grid)",
    )
    @app_commands.describe(
        grid="Paste pudding copy (`pattern 12…`) or a 10×9 0/1 or 1/2 grid. Spaces ignored.",
    )
    async def wallall_command(
        self, interaction: discord.Interaction, grid: app_commands.Range[str, 1, 600]
    ) -> None:
        cleaned = wall.parse_pattern_input(grid)
        if len(cleaned) != 90:
            await interaction.response.send_message(
                f"Small board only: send exactly 90 cells of `0`/`1` or `1`/`2`. "
                f"Got **{len(cleaned)}** after stripping other characters.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        async def send(result: wall.PatternResult) -> discord.Message:
            file = wall_stream.pattern_file(result)
            content = result.content or ""
            if len(content) > 1900:
                content = content[:1900] + "\n…(truncated)"
            if file:
                return await interaction.followup.send(content, file=file)
            return await interaction.followup.send(content)

        try:
            await wall_stream.stream_pattern_solve(
                cleaned, send, wall_stream.edit_pattern_message
            )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "Solve timed out after 45s. Try a different pattern (or one with more walls)."
            )
        except Exception as error:
            print(f"Error in /wallall: {error}")
            await interaction.followup.send("Failed to solve that pattern.")


async def setup(bot: commands.Bot):
    await bot.add_cog(WallAll(bot))

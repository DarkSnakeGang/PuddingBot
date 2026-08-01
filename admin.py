import os
import subprocess
import sys
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

RESTART_EXIT_CODE = 42
GIT_BRANCH = os.getenv("GIT_BRANCH", "main")
APP_DIR = os.getenv("APP_DIR", "/app")


def _get_owner_id() -> Optional[int]:
    owner_id = os.getenv("BOT_OWNER_ID")
    if not owner_id:
        return None
    try:
        return int(owner_id)
    except ValueError:
        return None


def _run_command(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=APP_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class Admin(commands.Cog):
    """Owner-only administration commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_owner(self, user_id: int) -> bool:
        owner_id = _get_owner_id()
        return owner_id is not None and user_id == owner_id

    @app_commands.command(
        name="update",
        description="Pull the latest code from GitHub and restart the bot",
    )
    async def update_command(self, interaction: discord.Interaction):
        if not self._is_owner(interaction.user.id):
            await interaction.response.send_message(
                "You are not authorized to run this command.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Hard sync to origin — avoids "untracked files would be overwritten" from Docker COPY leftovers
            fetch_result = _run_command(
                ["git", "fetch", "origin", GIT_BRANCH],
                timeout=120,
            )
            if fetch_result.returncode != 0:
                error_output = (fetch_result.stderr or fetch_result.stdout or "Unknown error").strip()
                await interaction.followup.send(
                    f"Git fetch failed:\n```\n{error_output[:1500]}\n```"
                )
                return

            reset_result = _run_command(
                ["git", "reset", "--hard", f"origin/{GIT_BRANCH}"],
                timeout=60,
            )
            if reset_result.returncode != 0:
                error_output = (reset_result.stderr or reset_result.stdout or "Unknown error").strip()
                await interaction.followup.send(
                    f"Git reset failed:\n```\n{error_output[:1500]}\n```"
                )
                return

            # Remove leftover untracked files from image COPY, but keep secrets
            clean_result = _run_command(
                ["git", "clean", "-fd", "-e", ".env", "-e", ".env.*"],
                timeout=60,
            )
            if clean_result.returncode != 0:
                error_output = (clean_result.stderr or clean_result.stdout or "Unknown error").strip()
                await interaction.followup.send(
                    f"Git clean failed:\n```\n{error_output[:1500]}\n```"
                )
                return

            pip_result = _run_command(
                ["pip3", "install", "-r", "requirements.txt"],
                timeout=300,
            )
            if pip_result.returncode != 0:
                error_output = (pip_result.stderr or pip_result.stdout or "Unknown error").strip()
                await interaction.followup.send(
                    "Git update succeeded, but dependency install failed:\n"
                    f"```\n{error_output[:1500]}\n```"
                )
                return

            commit_result = _run_command(["git", "rev-parse", "--short", "HEAD"], timeout=10)
            commit_hash = commit_result.stdout.strip() or "unknown"
            reset_output = (reset_result.stdout or "").strip() or f"Reset to origin/{GIT_BRANCH}"

            await interaction.followup.send(
                f"Updated to `{commit_hash}`.\n```\n{reset_output}\n```\nRestarting bot..."
            )

            await self.bot.close()
            sys.exit(RESTART_EXIT_CODE)

        except subprocess.TimeoutExpired:
            await interaction.followup.send("Update timed out. Check container logs.")
        except Exception as error:
            await interaction.followup.send(f"Update failed: {error}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))

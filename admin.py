import asyncio
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


async def _run_command_async(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    # Keep the Discord event loop alive while git/pip run
    return await asyncio.to_thread(_run_command, args, timeout)


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

        # Immediate visible status (must happen within 3 seconds)
        await interaction.response.send_message(
            "Updating from GitHub…\n- Fetching `origin/" + GIT_BRANCH + "`",
            ephemeral=True,
        )

        async def set_status(text: str) -> None:
            try:
                await interaction.edit_original_response(content=text)
            except Exception as e:
                print(f"Could not edit update status: {e}")

        try:
            before = await _run_command_async(["git", "rev-parse", "--short", "HEAD"], 10)
            before_hash = (before.stdout or "").strip() or "unknown"

            fetch_result = await _run_command_async(
                ["git", "fetch", "origin", GIT_BRANCH],
                timeout=120,
            )
            if fetch_result.returncode != 0:
                error_output = (fetch_result.stderr or fetch_result.stdout or "Unknown error").strip()
                await set_status(f"Update failed during fetch:\n```\n{error_output[:1500]}\n```")
                return

            await set_status(
                f"Updating from GitHub…\n"
                f"- Fetched `origin/{GIT_BRANCH}`\n"
                f"- Resetting working tree (was `{before_hash}`)"
            )

            reset_result = await _run_command_async(
                ["git", "reset", "--hard", f"origin/{GIT_BRANCH}"],
                timeout=60,
            )
            if reset_result.returncode != 0:
                error_output = (reset_result.stderr or reset_result.stdout or "Unknown error").strip()
                await set_status(f"Update failed during reset:\n```\n{error_output[:1500]}\n```")
                return

            clean_result = await _run_command_async(
                ["git", "clean", "-fd", "-e", ".env", "-e", ".env.*"],
                timeout=60,
            )
            if clean_result.returncode != 0:
                error_output = (clean_result.stderr or clean_result.stdout or "Unknown error").strip()
                await set_status(f"Update failed during clean:\n```\n{error_output[:1500]}\n```")
                return

            await set_status(
                f"Updating from GitHub…\n"
                f"- Code synced to `origin/{GIT_BRANCH}`\n"
                f"- Installing dependencies"
            )

            pip_result = await _run_command_async(
                ["pip3", "install", "-r", "requirements.txt"],
                timeout=300,
            )
            if pip_result.returncode != 0:
                error_output = (pip_result.stderr or pip_result.stdout or "Unknown error").strip()
                await set_status(
                    "Code synced, but dependency install failed "
                    "(bot was not restarted):\n"
                    f"```\n{error_output[:1500]}\n```"
                )
                return

            after = await _run_command_async(["git", "rev-parse", "--short", "HEAD"], 10)
            after_hash = (after.stdout or "").strip() or "unknown"
            reset_line = (reset_result.stdout or "").strip()

            await set_status(
                f"Update complete.\n"
                f"- `{before_hash}` → `{after_hash}`\n"
                f"- {reset_line or 'Working tree matches origin/' + GIT_BRANCH}\n"
                f"- Dependencies installed\n\n"
                f"Restarting bot now — I will be back in a few seconds."
            )

            # Give Discord time to deliver the final status before we die
            await asyncio.sleep(2)
            await self.bot.close()
            sys.exit(RESTART_EXIT_CODE)

        except subprocess.TimeoutExpired:
            await set_status("Update timed out. Check container logs — bot was not restarted.")
        except Exception as error:
            await set_status(f"Update failed: {error}\nBot was not restarted.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))

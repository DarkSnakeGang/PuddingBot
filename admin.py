import asyncio
import os
import re
import subprocess
import sys
from typing import Optional, Set

import discord
import requests
from discord import app_commands
from discord.ext import commands

RESTART_EXIT_CODE = 42
GIT_BRANCH = os.getenv("GIT_BRANCH", "main")
APP_DIR = os.getenv("APP_DIR", "/app")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = "qwen3:0.6b"


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
    return await asyncio.to_thread(_run_command, args, timeout)


def _desired_ollama_model() -> str:
    """Resolve model after git sync: env wins, else default from gpt.py on disk."""
    env_model = os.getenv("OLLAMA_MODEL")
    if env_model:
        return env_model.strip().strip('"').strip("'")

    try:
        with open(os.path.join(APP_DIR, "gpt.py"), encoding="utf-8") as handle:
            text = handle.read()
        match = re.search(
            r'OLLAMA_MODEL\s*=\s*os\.getenv\(\s*["\']OLLAMA_MODEL["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
            text,
        )
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Could not read OLLAMA_MODEL from gpt.py: {e}")

    return DEFAULT_OLLAMA_MODEL


def _installed_ollama_models() -> Set[str]:
    names: Set[str] = set()
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=15)
        response.raise_for_status()
        for model in response.json().get("models", []):
            name = model.get("name") or ""
            if name:
                names.add(name)
                names.add(name.split(":")[0])
                # ollama list uses tags like qwen3:8b; also accept with digest suffixes
                if ":" in name:
                    names.add(name.rsplit(":", 1)[0] + ":" + name.rsplit(":", 1)[1].split("-")[0])
    except Exception as e:
        print(f"Could not list Ollama models via API: {e}")
    return names


def _model_is_installed(model: str, installed: Set[str]) -> bool:
    if model in installed:
        return True
    # Match qwen3:8b against qwen3:8b or qwen3:8b-... variants
    for name in installed:
        if name == model or name.startswith(model + "-") or name.startswith(model + ":"):
            return True
    return False


async def _ensure_ollama_model(model: str, set_status) -> tuple[bool, str]:
    """Pull the model if missing. Returns (ok, status_note)."""
    installed = await asyncio.to_thread(_installed_ollama_models)
    if _model_is_installed(model, installed):
        return True, f"Ollama model `{model}` already installed"

    await set_status(
        f"Updating…\n"
        f"- Code synced\n"
        f"- Pulling Ollama model `{model}` (this can take several minutes)…"
    )

    pull = await _run_command_async(["ollama", "pull", model], timeout=1800)
    if pull.returncode != 0:
        error_output = (pull.stderr or pull.stdout or "Unknown error").strip()
        return False, f"Ollama pull failed for `{model}`:\n```\n{error_output[:1200]}\n```"

    return True, f"Ollama model `{model}` downloaded"


class Admin(commands.Cog):
    """Owner-only administration commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_owner(self, user_id: int) -> bool:
        owner_id = _get_owner_id()
        return owner_id is not None and user_id == owner_id

    @app_commands.command(
        name="sync-icons",
        description="Refresh setting icon emoji map from this server (admin only)",
    )
    @app_commands.default_permissions(administrator=True)
    async def sync_icons_command(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(
                "Run this in the server that has the setting emojis.",
                ephemeral=True,
            )
            return

        is_admin = (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        )
        if not (is_admin or self._is_owner(interaction.user.id)):
            await interaction.response.send_message(
                "You need the **Administrator** permission to run this command.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        import data_management as dm

        mapped = dm.refresh_emoji_map_from_guild(interaction.guild)
        expected = sum(
            1
            for family in (dm.APPLE_AMOUNTS, dm.SPEEDS, dm.SIZES, dm.GAMEMODES)
            for meta in family.values()
            if meta.get("id")
        )
        missing = expected - mapped
        await interaction.followup.send(
            f"Refreshed icons from this server.\n"
            f"- Mapped: **{mapped}** / {expected}\n"
            f"- Missing: **{missing}**\n"
            f"(Also runs automatically on bot startup.)",
            ephemeral=True,
        )

    @app_commands.command(
        name="update",
        description="Pull latest code, sync Ollama model, and restart the bot",
    )
    async def update_command(self, interaction: discord.Interaction):
        if not self._is_owner(interaction.user.id):
            await interaction.response.send_message(
                "You are not authorized to run this command.",
                ephemeral=True,
            )
            return

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
                ["git", "clean", "-fd", "-e", ".env", "-e", ".env.*", "-e", "emoji_map.json"],
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

            model = _desired_ollama_model()
            ollama_ok, ollama_note = await _ensure_ollama_model(model, set_status)
            if not ollama_ok:
                await set_status(
                    f"Code and deps updated, but Ollama model sync failed "
                    f"(bot was not restarted):\n{ollama_note}"
                )
                return

            after = await _run_command_async(["git", "rev-parse", "--short", "HEAD"], 10)
            after_hash = (after.stdout or "").strip() or "unknown"
            reset_line = (reset_result.stdout or "").strip()

            await set_status(
                f"Update complete.\n"
                f"- `{before_hash}` → `{after_hash}`\n"
                f"- {reset_line or 'Working tree matches origin/' + GIT_BRANCH}\n"
                f"- Dependencies installed\n"
                f"- {ollama_note}\n\n"
                f"Restarting bot now — I will be back in a few seconds."
            )

            await asyncio.sleep(2)
            await self.bot.close()
            sys.exit(RESTART_EXIT_CODE)

        except subprocess.TimeoutExpired:
            await set_status("Update timed out. Check container logs — bot was not restarted.")
        except Exception as error:
            await set_status(f"Update failed: {error}\nBot was not restarted.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))

"""Watch DarkSnakeGang mod / FastSnakeStats repos and announce updates."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands, tasks

# Community mods / tools channel
REPO_WATCH_CHANNEL_ID = int(
    os.getenv("REPO_WATCH_CHANNEL_ID", "728788277762457702")
)

REPO_WATCH_ENABLED = os.getenv("REPO_WATCH_ENABLED", "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)

try:
    REPO_WATCH_MINUTES = max(1, int(os.getenv("REPO_WATCH_MINUTES", "30")))
except ValueError:
    REPO_WATCH_MINUTES = 30

STATE_PATH = os.path.join(
    os.path.dirname(__file__),
    "repo_watch_state.json",
)


@dataclass(frozen=True)
class TrackedRepo:
    """A GitHub repo to probe for new tip commits."""

    name: str
    owner: str
    repo: str
    branch: str = "main"

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.full_name}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.full_name}.git"


# Display name → DarkSnakeGang repository
TRACKED_REPOS: Tuple[TrackedRepo, ...] = (
    TrackedRepo("PuddingMod", "DarkSnakeGang", "GoogleSnakePudding"),
    TrackedRepo("LevelEditor", "DarkSnakeGang", "GoogleSnakeLevelEditor"),
    TrackedRepo("MoreMenu", "DarkSnakeGang", "GoogleSnakeCustomMenuStuff"),
    TrackedRepo("MouseMod", "DarkSnakeGang", "GoogleSnakeMouseMode"),
    TrackedRepo("VisibilityMod", "DarkSnakeGang", "GoogleSnakeDeleteStuffMod"),
    TrackedRepo("RemixMod", "DarkSnakeGang", "GoogleSnakeRemix"),
    TrackedRepo("FastSnakeStats", "DarkSnakeGang", "FastSnakeStats"),
)


async def _git_ls_remote(repo: TrackedRepo) -> Optional[str]:
    """Return the current tip SHA for repo.branch via git ls-remote."""
    ref = f"refs/heads/{repo.branch}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-remote",
            repo.clone_url,
            ref,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)
    except asyncio.TimeoutError:
        print(f"[repo-watch] Timed out probing {repo.full_name}")
        return None
    except FileNotFoundError:
        print("[repo-watch] git not found on PATH")
        return None
    except Exception as error:
        print(f"[repo-watch] Error probing {repo.full_name}: {error}")
        return None

    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace").strip()
        print(f"[repo-watch] ls-remote failed for {repo.full_name}: {err[:300]}")
        return None

    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    if not text:
        return None
    # "sha\trefs/heads/main"
    sha = text.split()[0].strip()
    return sha or None


def _load_state() -> Dict[str, str]:
    if not os.path.isfile(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        shas = data.get("shas") if isinstance(data, dict) else None
        if isinstance(shas, dict):
            return {str(k): str(v) for k, v in shas.items() if v}
    except Exception as error:
        print(f"[repo-watch] Could not read state file: {error}")
    return {}


def _save_state(shas: Dict[str, str]) -> None:
    payload = {
        "lastChecked": datetime.now(timezone.utc).isoformat(),
        "shas": shas,
    }
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except Exception as error:
        print(f"[repo-watch] Could not write state file: {error}")


class RepoWatcher(commands.Cog):
    """Probe tracked repos and announce tip-commit changes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._known_shas: Dict[str, str] = _load_state()
        self._probe_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        if REPO_WATCH_ENABLED:
            if not self.repo_watch_task.is_running():
                self.repo_watch_task.start()
            names = ", ".join(r.name for r in TRACKED_REPOS)
            print(
                f"[repo-watch] Enabled — checking {len(TRACKED_REPOS)} repos "
                f"every {REPO_WATCH_MINUTES} minutes ({names})"
            )
        else:
            print("[repo-watch] Disabled (REPO_WATCH_ENABLED=0)")

    async def cog_unload(self) -> None:
        if self.repo_watch_task.is_running():
            self.repo_watch_task.cancel()

    async def _get_announce_channel(self) -> Optional[discord.abc.Messageable]:
        channel = self.bot.get_channel(REPO_WATCH_CHANNEL_ID)
        if channel is not None:
            return channel
        try:
            return await self.bot.fetch_channel(REPO_WATCH_CHANNEL_ID)
        except Exception as error:
            print(
                f"[repo-watch] Could not fetch channel "
                f"{REPO_WATCH_CHANNEL_ID}: {error}"
            )
            return None

    async def _announce(self, repo: TrackedRepo, sha: str) -> None:
        channel = await self._get_announce_channel()
        if channel is None:
            print(
                f"[repo-watch] Skipping announce for {repo.name} — "
                f"channel {REPO_WATCH_CHANNEL_ID} unavailable"
            )
            return
        short = sha[:7] if sha else "unknown"
        message = f"{repo.name} was updated!"
        try:
            await channel.send(message)
            print(f"[repo-watch] Announced {repo.name} update ({short})")
        except Exception as error:
            print(f"[repo-watch] Failed to announce {repo.name}: {error}")

    async def probe_once(self, announce: bool = True) -> List[str]:
        """Probe all repos. Returns display names that changed."""
        changed: List[str] = []
        async with self._probe_lock:
            updated_state = dict(self._known_shas)
            for repo in TRACKED_REPOS:
                sha = await _git_ls_remote(repo)
                if not sha:
                    continue
                key = repo.full_name
                previous = updated_state.get(key)
                if previous is None:
                    # First sighting: seed quietly (no spam on boot / new repo)
                    updated_state[key] = sha
                    print(
                        f"[repo-watch] Seeded {repo.name} at {sha[:7]} "
                        f"(no announce)"
                    )
                    continue
                if previous == sha:
                    continue
                updated_state[key] = sha
                changed.append(repo.name)
                print(
                    f"[repo-watch] {repo.name} tip changed: "
                    f"{previous[:7]} → {sha[:7]}"
                )
                if announce:
                    await self._announce(repo, sha)

            self._known_shas = updated_state
            _save_state(updated_state)
        return changed

    @tasks.loop(minutes=REPO_WATCH_MINUTES)
    async def repo_watch_task(self) -> None:
        try:
            print("[repo-watch] Probing tracked repos…")
            changed = await self.probe_once(announce=True)
            if not changed:
                print("[repo-watch] No updates")
            else:
                print(f"[repo-watch] Announced: {', '.join(changed)}")
        except Exception as error:
            print(f"[repo-watch] Probe failed: {error}")

    @repo_watch_task.before_loop
    async def before_repo_watch_task(self) -> None:
        await self.bot.wait_until_ready()
        # Avoid racing startup; also gives auto-update a head start
        await asyncio.sleep(90)


async def setup(bot: commands.Bot):
    await bot.add_cog(RepoWatcher(bot))

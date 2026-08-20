"""Persist category WR watches and compare snapshots."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wr_watch_state.json")
MAX_WATCHES_PER_USER = 15
MAX_WATCHES_TOTAL = 80


def fingerprint_runs(runs: Optional[List[Dict]]) -> str:
    if not runs:
        return ""
    parts = []
    for run in runs:
        run_id = str(run.get("id") or "").strip()
        parts.append(run_id or "?")
    return ",".join(sorted(parts))


def _empty_state() -> Dict:
    return {"watches": []}


def load_state() -> Dict:
    if not os.path.isfile(STATE_PATH):
        return _empty_state()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("watches"), list):
            return data
    except Exception as error:
        print(f"[wr-watch] Could not read state: {error}")
    return _empty_state()


def save_state(state: Dict) -> None:
    payload = {
        "lastChecked": datetime.now(timezone.utc).isoformat(),
        "watches": state.get("watches") or [],
    }
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
    except Exception as error:
        print(f"[wr-watch] Could not write state: {error}")


def list_user_watches(user_id: int) -> List[Dict]:
    uid = int(user_id)
    return [w for w in load_state().get("watches") or [] if int(w.get("user_id") or 0) == uid]


def add_watch(
    *,
    user_id: int,
    channel_id: int,
    guild_id: Optional[int],
    category: str,
    fingerprint: str,
    player: str,
    time_str: str,
) -> tuple[Optional[Dict], Optional[str]]:
    state = load_state()
    watches = state.get("watches") or []
    uid = int(user_id)
    if any(int(w.get("user_id") or 0) == uid and w.get("category") == category for w in watches):
        return None, "You are already watching that category."
    mine = [w for w in watches if int(w.get("user_id") or 0) == uid]
    if len(mine) >= MAX_WATCHES_PER_USER:
        return None, f"You already have {MAX_WATCHES_PER_USER} watches. Remove one first."
    if len(watches) >= MAX_WATCHES_TOTAL:
        return None, "The global watch list is full. Try again later."

    entry = {
        "id": uuid.uuid4().hex[:12],
        "user_id": uid,
        "channel_id": int(channel_id),
        "guild_id": int(guild_id) if guild_id else None,
        "category": category,
        "fingerprint": fingerprint,
        "player": player,
        "time": time_str,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    watches.append(entry)
    state["watches"] = watches
    save_state(state)
    return entry, None


def remove_watch(user_id: int, category: str) -> bool:
    state = load_state()
    uid = int(user_id)
    before = state.get("watches") or []
    after = [
        w for w in before
        if not (int(w.get("user_id") or 0) == uid and w.get("category") == category)
    ]
    if len(after) == len(before):
        return False
    state["watches"] = after
    save_state(state)
    return True


def clear_user_watches(user_id: int) -> int:
    state = load_state()
    uid = int(user_id)
    before = state.get("watches") or []
    after = [w for w in before if int(w.get("user_id") or 0) != uid]
    removed = len(before) - len(after)
    if removed:
        state["watches"] = after
        save_state(state)
    return removed


def update_watch_snapshot(watch_id: str, fingerprint: str, player: str, time_str: str) -> None:
    state = load_state()
    changed = False
    for watch in state.get("watches") or []:
        if watch.get("id") == watch_id:
            watch["fingerprint"] = fingerprint
            watch["player"] = player
            watch["time"] = time_str
            changed = True
            break
    if changed:
        save_state(state)

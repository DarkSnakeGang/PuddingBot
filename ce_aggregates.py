"""CE-filtered rebuilds of FastSnakeStats explorer aggregates.

The explorer JSON only ships aggregates across every mode (CE levels included).
These helpers recompute the same shapes from `longevity.all` holds and
`progression` after applying a ce_display filter (Off | Mix | Only).
"""
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

import data_management as dm


def normalize_ce(ce_display: Optional[str]) -> str:
    value = (ce_display or "Off").strip().capitalize()
    return value if value in ("Off", "Mix", "Only") else "Off"


def filter_holds(holds: Iterable[Dict], ce_display: Optional[str]) -> List[Dict]:
    ce = normalize_ce(ce_display)
    if ce == "Mix":
        return list(holds or [])
    return [
        h for h in (holds or [])
        if dm.category_allowed_for_ce_display(h.get("category") or "", ce)
    ]


def _better(a: Optional[Dict], b: Optional[Dict]) -> Optional[Dict]:
    if not a:
        return b
    if not b:
        return a
    if (b.get("days") or 0) != (a.get("days") or 0):
        return b if (b.get("days") or 0) > (a.get("days") or 0) else a
    return b if str(b.get("start") or "") > str(a.get("start") or "") else a


def _hold_row(h: Dict) -> Dict:
    return {
        "category": h.get("category"),
        "playerId": h.get("playerId"),
        "playerName": h.get("playerName"),
        "time": h.get("time"),
        "weblink": h.get("weblink"),
        "start": h.get("start"),
        "end": h.get("end"),
        "days": h.get("days") or 0,
        "stillStanding": bool(h.get("stillStanding")),
        "tiedHolders": h.get("tiedHolders") or 1,
    }


def build_career(holds: Iterable[Dict]) -> List[Dict]:
    """Same shape as explorer `career` rows (WR-days per player)."""
    by_player: Dict[str, Dict] = {}
    for h in holds or []:
        pid = h.get("playerId")
        if not pid:
            continue
        p = by_player.get(pid)
        if p is None:
            p = {
                "playerId": pid,
                "playerName": h.get("playerName"),
                "wrDays": 0,
                "wrDaysUntied": 0,
                "wrDaysTied": 0,
                "holds": 0,
                "standingHolds": 0,
                "bestAll": None,
                "bestStanding": None,
                "bestAllUntied": None,
                "bestStandingUntied": None,
                "bestAllTied": None,
                "bestStandingTied": None,
            }
            by_player[pid] = p
        p["playerName"] = h.get("playerName") or p["playerName"]
        days = h.get("days") or 0
        row = _hold_row(h)
        tied = (h.get("tiedHolders") or 1) > 1
        p["wrDays"] += days
        p["holds"] += 1
        p["bestAll"] = _better(p["bestAll"], row)
        if tied:
            p["wrDaysTied"] += days
            p["bestAllTied"] = _better(p["bestAllTied"], row)
        else:
            p["wrDaysUntied"] += days
            p["bestAllUntied"] = _better(p["bestAllUntied"], row)
        if h.get("stillStanding"):
            p["standingHolds"] += 1
            p["bestStanding"] = _better(p["bestStanding"], row)
            if tied:
                p["bestStandingTied"] = _better(p["bestStandingTied"], row)
            else:
                p["bestStandingUntied"] = _better(p["bestStandingUntied"], row)
    return sorted(
        by_player.values(),
        key=lambda r: (-r["wrDays"], str(r.get("playerName") or "")),
    )


def build_countries(
    holds: Iterable[Dict], player_countries: Dict, country_names: Dict
) -> List[Dict]:
    """Same shape as explorer `countries` rows."""
    agg: Dict[str, Dict] = {}
    player_days: Dict[str, Dict] = {}
    for h in holds or []:
        pid = h.get("playerId")
        if not pid:
            continue
        code = None
        if not str(pid).startswith("guest:"):
            code = player_countries.get(pid)
        key = code or "unknown"
        c = agg.get(key)
        if c is None:
            c = {
                "countryCode": code,
                "countryName": "Unknown" if not code else (country_names.get(code) or code.upper()),
                "playerIds": set(),
                "wrDays": 0,
                "wrDaysUntied": 0,
                "wrDaysTied": 0,
                "holds": 0,
                "standingHolds": 0,
                "bestAll": None,
                "bestStanding": None,
            }
            agg[key] = c
        c["playerIds"].add(pid)
        days = h.get("days") or 0
        row = _hold_row(h)
        c["wrDays"] += days
        c["holds"] += 1
        c["bestAll"] = _better(c["bestAll"], row)
        if (h.get("tiedHolders") or 1) > 1:
            c["wrDaysTied"] += days
        else:
            c["wrDaysUntied"] += days
        if h.get("stillStanding"):
            c["standingHolds"] += 1
            c["bestStanding"] = _better(c["bestStanding"], row)

        pw = player_days.get(pid)
        if pw is None:
            pw = {"playerId": pid, "playerName": h.get("playerName"), "wrDays": 0, "key": key}
            player_days[pid] = pw
        pw["playerName"] = h.get("playerName") or pw["playerName"]
        pw["wrDays"] += days

    top: Dict[str, Dict] = {}
    for pw in player_days.values():
        prev = top.get(pw["key"])
        if (
            prev is None
            or pw["wrDays"] > prev["wrDays"]
            or (
                pw["wrDays"] == prev["wrDays"]
                and str(pw["playerName"]) < str(prev["playerName"])
            )
        ):
            top[pw["key"]] = {
                "playerId": pw["playerId"],
                "playerName": pw["playerName"],
                "wrDays": pw["wrDays"],
            }

    rows = []
    for key, c in agg.items():
        rows.append({
            "countryCode": c["countryCode"],
            "countryName": c["countryName"],
            "playerCount": len(c["playerIds"]),
            "wrDays": c["wrDays"],
            "wrDaysUntied": c["wrDaysUntied"],
            "wrDaysTied": c["wrDaysTied"],
            "holds": c["holds"],
            "standingHolds": c["standingHolds"],
            "topPlayer": top.get(key),
            "bestAll": c["bestAll"],
            "bestStanding": c["bestStanding"],
        })
    rows.sort(key=lambda r: (-r["wrDays"], str(r.get("countryName") or "")))
    return rows


def _active_on(h: Dict, day: str) -> bool:
    start = h.get("start") or ""
    if not start or start > day:
        return False
    if h.get("stillStanding"):
        return True
    return day < (h.get("end") or "")


def _shift(day: str, delta_days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=delta_days)).isoformat()


IMPROVING_WINDOWS = (("7d", 7), ("30d", 30), ("90d", 90), ("365d", 365))


def build_improving(
    holds: Iterable[Dict], latest: str, limit: Optional[int] = 25
) -> Dict[str, List[Dict]]:
    """Same shape as explorer `improving` (WR count gain per window)."""
    holds = list(holds or [])
    names: Dict[str, str] = {}
    for h in holds:
        pid = h.get("playerId")
        if pid:
            names[pid] = h.get("playerName") or names.get(pid) or pid

    def counts_on(day: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for h in holds:
            pid = h.get("playerId")
            if pid and _active_on(h, day):
                out[pid] = out.get(pid, 0) + 1
        return out

    end_counts = counts_on(latest)
    result: Dict[str, List[Dict]] = {}
    for key, days in IMPROVING_WINDOWS:
        start_counts = counts_on(_shift(latest, -days))
        ranked = []
        for pid, end_n in end_counts.items():
            start_n = start_counts.get(pid, 0)
            delta = end_n - start_n
            if delta <= 0:
                continue
            ranked.append({
                "playerId": pid,
                "playerName": names.get(pid, pid),
                "delta": delta,
                "startCount": start_n,
                "endCount": end_n,
            })
        ranked.sort(key=lambda r: (-r["delta"], str(r["playerName"])))
        result[key] = ranked[:limit]
    return result


def player_improving(
    holds: Iterable[Dict], latest: str, player_id: Optional[str], player_name: Optional[str]
) -> Optional[Dict[str, Dict]]:
    mine = [h for h in holds or [] if _matches_player(h, player_id, player_name)]
    if not mine:
        return None
    end_n = sum(1 for h in mine if _active_on(h, latest))
    found: Dict[str, Dict] = {}
    for key, days in IMPROVING_WINDOWS:
        start_n = sum(1 for h in mine if _active_on(h, _shift(latest, -days)))
        delta = end_n - start_n
        if delta > 0:
            found[key] = {"delta": delta, "startCount": start_n, "endCount": end_n}
    return found or None


def _matches_player(h: Dict, player_id: Optional[str], player_name: Optional[str]) -> bool:
    # With a known id, never merge in same-named players or guests
    if player_id:
        return h.get("playerId") == player_id
    name = (player_name or "").lower().strip()
    return bool(name) and (h.get("playerName") or "").lower() == name


def player_career(
    holds: Iterable[Dict], player_id: Optional[str], player_name: Optional[str]
) -> Optional[Dict]:
    mine = [h for h in holds or [] if _matches_player(h, player_id, player_name)]
    rows = build_career(mine)
    return rows[0] if rows else None


def _day_index(day: str, origin: date) -> int:
    return (date.fromisoformat(day) - origin).days


def player_peak_stats(
    holds: Iterable[Dict],
    earliest: str,
    latest: str,
    player_id: Optional[str],
    player_name: Optional[str],
) -> Optional[Dict]:
    """Peak records / peak % / dates held / unique WRs from filtered holds."""
    holds = list(holds or [])
    if not holds or not earliest or not latest:
        return None
    origin = date.fromisoformat(earliest)
    n_days = _day_index(latest, origin) + 1
    if n_days <= 0:
        return None

    def spans(h: Dict) -> Optional[Tuple[int, int]]:
        start = h.get("start")
        if not start:
            return None
        s = max(0, _day_index(start, origin))
        if h.get("stillStanding"):
            e = n_days
        else:
            end = h.get("end")
            if not end:
                return None
            e = min(n_days, _day_index(end, origin))
        return (s, e) if e > s else None

    total_diff = [0] * (n_days + 1)
    mine_diff = [0] * (n_days + 1)
    mine_links = set()
    found_name = None
    found_id = None
    for h in holds:
        span = spans(h)
        if not span:
            continue
        s, e = span
        total_diff[s] += 1
        total_diff[e] -= 1
        if _matches_player(h, player_id, player_name):
            mine_diff[s] += 1
            mine_diff[e] -= 1
            mine_links.add(h.get("weblink") or f"{h.get('category')}|{h.get('start')}")
            found_name = h.get("playerName") or found_name
            found_id = h.get("playerId") or found_id

    if not mine_links:
        return None

    total = mine = 0
    peak_count, peak_count_day = 0, 0
    peak_pct, peak_pct_day = 0.0, 0
    dates_held = 0
    for i in range(n_days):
        total += total_diff[i]
        mine += mine_diff[i]
        if mine <= 0:
            continue
        dates_held += 1
        if mine > peak_count:
            peak_count, peak_count_day = mine, i
        pct = (mine / total) * 100 if total else 0.0
        if pct > peak_pct:
            peak_pct, peak_pct_day = pct, i

    latest_pct = (mine / total) * 100 if total and mine > 0 else 0.0
    as_date = lambda i: (origin + timedelta(days=i)).isoformat()
    return {
        "id": found_id or player_id,
        "name": found_name or player_name,
        "totalRecords": len(mine_links),
        "totalDates": dates_held,
        "peakRecords": {"count": peak_count, "date": as_date(peak_count_day)},
        "peakPercentage": {"percentage": round(peak_pct, 2), "date": as_date(peak_pct_day)},
        "latest": {
            "count": max(mine, 0),
            "percentage": round(latest_pct, 2),
            "date": latest,
        },
    }


def activity_from_progression(progression: Dict, ce_display: Optional[str]) -> List[Dict]:
    """Daily {date, flips, newWrs} from progression for CE-filtered categories.

    flips = #1 time changed that day; newWrs = new #1 times set that day
    (including a board's first WR) — progression has no per-run SRC dates.
    """
    ce = normalize_ce(ce_display)
    by_day: Dict[str, Dict[str, int]] = {}
    for category, points in (progression or {}).items():
        if not points or not dm.category_allowed_for_ce_display(category, ce):
            continue
        for i, point in enumerate(points):
            day = point.get("d")
            if not day:
                continue
            slot = by_day.setdefault(day, {"flips": 0, "newWrs": 0})
            slot["newWrs"] += 1
            if i > 0:
                slot["flips"] += 1
    return [
        {"date": day, "flips": v["flips"], "newWrs": v["newWrs"]}
        for day, v in sorted(by_day.items())
    ]

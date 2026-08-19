import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, Dict, List, Tuple
import asyncio
import os
import random
from calendar import monthrange, month_name
from datetime import datetime, date, time, timedelta, timezone

from github_cache_fetcher import github_cache_fetcher
import data_management as dm
import wr_watch

# google-snake channel (snake emoji) — https://discord.com/channels/723093146954760222/723093815786864661
GOOGLE_SNAKE_CHANNEL_ID = int(os.getenv("GOOGLE_SNAKE_CHANNEL_ID", "723093815786864661"))
# Minimum hold age (days) to count as an "oldest records" beat
MIN_OLDEST_HOLD_DAYS = int(os.getenv("MIN_OLDEST_HOLD_DAYS", "365"))
# How many longest beaten holds to highlight in the monthly post
MONTHLY_BEATEN_LIMIT = int(os.getenv("MONTHLY_BEATEN_LIMIT", "10"))
# Noon local for the scheduled post (default UTC+3)
_MONTHLY_UTC_OFFSET = int(os.getenv("MONTHLY_REPORT_UTC_OFFSET", "3"))
MONTHLY_REPORT_TZ = timezone(timedelta(hours=_MONTHLY_UTC_OFFSET))

# FastSnakeStats Mastery mode-group filter labels
MASTERY_MODE_HS_ONLY = "High score modes only"
MASTERY_MODE_NO_PEACEFUL = "Excluding Peaceful"
MASTERY_MODE_GROUPS = (MASTERY_MODE_HS_ONLY, MASTERY_MODE_NO_PEACEFUL)
# Shared Mode filter on explorer list tabs (FSS STATS_LIST_MODE_GROUPS)
LIST_MODE_GROUPS = (MASTERY_MODE_HS_ONLY,)


class FastSnakeStats(commands.Cog):
    """FastSnakeStats Discord bot integration"""

    watch_group = app_commands.Group(
        name="watch",
        description="Get notified when a category world record changes",
    )
    
    def __init__(self, bot):
        self.bot = bot
        self.cache_data = {}
        self.last_cache_update = None
        self.monthly_oldest_report_task.start()
        self.wr_watch_task.start()

    def cog_unload(self):
        self.monthly_oldest_report_task.cancel()
        if self.wr_watch_task.is_running():
            self.wr_watch_task.cancel()
    
    async def get_record_data(self, apple_amount: str, speed: str, size: str, gamemode: str, date: Optional[str] = None, run_mode: str = "25 Apples") -> Optional[Dict]:
        """Get record data for specific settings"""
        try:
            # Validate settings
            if not dm.validate_settings(apple_amount, speed, size, gamemode):
                return None
            
            # Validate date if provided
            if date and not await github_cache_fetcher.is_date_available(date):
                return None
            
            # Generate settings key
            settings_key = dm.get_settings_key(apple_amount, speed, size, gamemode, run_mode)
            
            # Fetch data from GitHub cache
            if date:
                world_records = await github_cache_fetcher.fetch_world_records_for_date(date)
            else:
                world_records = await github_cache_fetcher.fetch_current_world_records()
            
            if not world_records or settings_key not in world_records:
                return None
            
            runs = world_records[settings_key]
            if not runs or len(runs) == 0:
                return None
            
            # Get the best run (first in the list)
            best_run = runs[0]
            
            return {
                'run': best_run,
                'settings': settings_key,
                'total_runs': len(runs),
                'date': date or await github_cache_fetcher.get_most_recent_date()
            }
            
        except Exception as e:
            print(f"Error getting record data: {e}")
            return None
    
    async def get_player_data(self, player_name: str, date: Optional[str] = None) -> Optional[Dict]:
        """Get player statistics and recent activity"""
        try:
            # Validate date if provided
            if date and not await github_cache_fetcher.is_date_available(date):
                return None
            
            # Fetch data from GitHub cache
            if date:
                world_records = await github_cache_fetcher.fetch_world_records_for_date(date)
            else:
                world_records = await github_cache_fetcher.fetch_current_world_records()
            
            if not world_records:
                return None
            
            player_name_lower = player_name.lower()
            player_records = []
            total_runs = 0
            total_world_records = 0
            
            # Search through all settings for this player
            for settings_key, runs in world_records.items():
                if not runs or len(runs) == 0:
                    continue
                total_world_records += len(runs)
                
                # Count all runs for this player in this settings combination (matching /stats logic)
                for run in runs:
                    if run and dm.get_player_name(run):
                        player_name_from_run = dm.get_player_name(run)
                        if player_name_from_run.lower() == player_name_lower:
                            total_runs += 1
                            player_records.append({
                                'run': run,
                                'settings': settings_key,
                                'rank': 1
                            })
            
            peak_stats = await github_cache_fetcher.get_player_peak_stats(player_name)
            display_name = (peak_stats or {}).get('name') or player_name
            player_id = (peak_stats or {}).get('id')
            snapshot_date = date or await github_cache_fetcher.get_most_recent_date()
            current_pct = (
                round((total_runs / total_world_records) * 100, 2)
                if total_world_records > 0 else 0.0
            )

            career = await github_cache_fetcher.get_player_career(
                player_id=player_id, player_name=display_name
            )
            longevity_best = await github_cache_fetcher.get_player_longevity_best(
                player_id=player_id, player_name=display_name
            )
            improving = await github_cache_fetcher.get_player_improving(
                player_id=player_id, player_name=display_name
            )
            mastery = await github_cache_fetcher.get_mastery_player(
                player_id=player_id, player_name=display_name
            )
            if mastery:
                mastery_meta = await github_cache_fetcher.fetch_mastery_challenge()
                mastery = {
                    **mastery,
                    "boardCount": ((mastery_meta or {}).get("meta") or {}).get(
                        "boardCount", 1386
                    ),
                }
            empire = await github_cache_fetcher.get_chronicle_empire(
                player_id=player_id, player_name=display_name
            )

            if not player_records:
                if not peak_stats and not career and not mastery and not empire:
                    return None
                return {
                    'player_name': display_name,
                    'player_id': player_id,
                    'world_records_held': 0,
                    'current_percentage': 0.0,
                    'total_world_records': total_world_records,
                    'recent_activity': [],
                    'date': snapshot_date,
                    'peak_stats': peak_stats,
                    'career': career,
                    'longevity_best': longevity_best,
                    'improving': improving,
                    'mastery': mastery,
                    'empire': empire,
                }

            # Sort by date (most recent first)
            player_records.sort(key=lambda x: dm.get_run_date(x['run']), reverse=True)
            
            return {
                'player_name': display_name,
                'player_id': player_id,
                'world_records_held': total_runs,
                'current_percentage': current_pct,
                'total_world_records': total_world_records,
                'recent_activity': player_records,
                'date': snapshot_date,
                'peak_stats': peak_stats,
                'career': career,
                'longevity_best': longevity_best,
                'improving': improving,
                'mastery': mastery,
                'empire': empire,
            }
            
        except Exception as e:
            print(f"Error getting player data: {e}")
            return None
    
    async def get_stats_data(self, date: Optional[str] = None) -> Optional[Dict]:
        """Get statistics about top record holders"""
        try:
            # Validate date if provided
            if date and not await github_cache_fetcher.is_date_available(date):
                return None
            
            # Fetch data from GitHub cache
            if date:
                world_records = await github_cache_fetcher.fetch_world_records_for_date(date)
            else:
                world_records = await github_cache_fetcher.fetch_current_world_records()
            
            if not world_records:
                return None
            
            # Count total runs across all settings
            total_world_records = 0
            player_records = {}
            
            # Count runs per player
            for settings_key, runs in world_records.items():
                if not runs or len(runs) == 0:
                    continue
                
                # Count all runs for this settings combination
                total_world_records += len(runs)
                
                # Count runs per player
                for run in runs:
                    if run and dm.get_player_name(run):
                        player_name = dm.get_player_name(run)
                        
                        if player_name not in player_records:
                            player_records[player_name] = 0
                        player_records[player_name] += 1
            
            if not player_records:
                return None
            
            # Sort by number of records (descending)
            sorted_by_number = sorted(player_records.items(), key=lambda x: x[1], reverse=True)
            
            # Sort by percentage (descending)
            sorted_by_percentage = sorted(player_records.items(), key=lambda x: (x[1] / total_world_records) * 100, reverse=True)
            
            return {
                'total_world_records': total_world_records,
                'top_by_number': sorted_by_number,  # All players by number
                'top_by_percentage': sorted_by_percentage,  # All players by percentage
                'date': date or await github_cache_fetcher.get_most_recent_date()
            }
            
        except Exception as e:
            print(f"Error getting stats data: {e}")
            return None
    
    async def get_weekly_report_data(self) -> Optional[Dict]:
        """Get weekly report data showing record changes in the last 7 days"""
        try:
            # Get available dates
            available_dates = await github_cache_fetcher.get_available_dates()
            if not available_dates or len(available_dates) < 2:
                return None
            
            # Get the most recent 7 days from available dates
            recent_dates = available_dates[-7:] if len(available_dates) >= 7 else available_dates
            current_date = recent_dates[-1]  # Most recent date
            week_ago_date = recent_dates[0]  # 7 days ago (or earliest available)
            
            # Fetch current and week-ago data
            current_records = await github_cache_fetcher.fetch_world_records_for_date(current_date)
            week_ago_records = await github_cache_fetcher.fetch_world_records_for_date(week_ago_date)
            
            if not current_records:
                return None
            
            # Analyze changes
            new_records = []
            record_changes = []
            improved_records = []
            
            # Get all unique settings keys
            all_settings = set(current_records.keys())
            if week_ago_records:
                all_settings.update(week_ago_records.keys())
            
            for settings_key in all_settings:
                current_runs = current_records.get(settings_key, [])
                week_ago_runs = week_ago_records.get(settings_key, []) if week_ago_records else []
                
                # Check for new records (no previous record)
                if current_runs and not week_ago_runs:
                    best_run = current_runs[0]
                    new_records.append({
                        'settings': settings_key,
                        'run': best_run,
                        'player': dm.get_player_name(best_run),
                        'time': dm.get_run_time(best_run),
                        'date': dm.get_run_date(best_run)
                    })
                
                # Check for record changes (different player or improved time)
                elif current_runs and week_ago_runs:
                    current_best = current_runs[0]
                    week_ago_best = week_ago_runs[0]
                    
                    current_player = dm.get_player_name(current_best)
                    week_ago_player = dm.get_player_name(week_ago_best)
                    
                    # Different player took the record
                    if current_player != week_ago_player:
                        record_changes.append({
                            'settings': settings_key,
                            'old_player': week_ago_player,
                            'new_player': current_player,
                            'old_time': dm.get_run_time(week_ago_best),
                            'new_time': dm.get_run_time(current_best),
                            'old_date': dm.get_run_date(week_ago_best),
                            'new_date': dm.get_run_date(current_best),
                            'improvement': self._calculate_improvement(week_ago_best, current_best)
                        })
                    
                    # Same player improved their own record
                    elif current_player == week_ago_player:
                        improvement = self._calculate_improvement(week_ago_best, current_best)
                        if improvement and improvement > 0:
                            improved_records.append({
                                'settings': settings_key,
                                'player': current_player,
                                'old_time': dm.get_run_time(week_ago_best),
                                'new_time': dm.get_run_time(current_best),
                                'old_date': dm.get_run_date(week_ago_best),
                                'new_date': dm.get_run_date(current_best),
                                'improvement': improvement
                            })
            
            return {
                'current_date': current_date,
                'week_ago_date': week_ago_date,
                'new_records': new_records,
                'record_changes': record_changes,
                'improved_records': improved_records,
                'total_changes': len(new_records) + len(record_changes) + len(improved_records)
            }
            
        except Exception as e:
            print(f"Error getting weekly report data: {e}")
            return None

    def _previous_calendar_month_bounds(self, ref: Optional[date] = None) -> Tuple[str, str, str]:
        """Return (start_iso, end_iso, label) for the previous calendar month."""
        today = ref or datetime.now(MONTHLY_REPORT_TZ).date()
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        label = f"{month_name[first_prev.month]} {first_prev.year}"
        return first_prev.isoformat(), last_prev.isoformat(), label

    def _year_month_bounds(self, year_month: str) -> Optional[Tuple[str, str, str]]:
        """Return (start_iso, end_iso, label) for a YYYY-MM string."""
        try:
            year_s, month_s = year_month.split("-", 1)
            year, month = int(year_s), int(month_s)
            if month < 1 or month > 12:
                return None
            first = date(year, month, 1)
            last = date(year, month, monthrange(year, month)[1])
            label = f"{month_name[month]} {year}"
            return first.isoformat(), last.isoformat(), label
        except (TypeError, ValueError):
            return None

    async def get_complete_year_months(self) -> List[str]:
        """YYYY-MM months with full FastSnakeStats coverage (live check)."""
        return await github_cache_fetcher.get_complete_year_months()

    async def resolve_monthly_year_month(self, year_month: Optional[str] = None) -> Optional[str]:
        """Pick a report month using live FastSnakeStats completeness.

        - If year_month is given, accept it only when that month is fully cached.
        - Otherwise prefer the previous calendar month when complete, else the
          latest complete month FastSnakeStats has (back to the start of data).
        """
        complete = await github_cache_fetcher.get_complete_year_months()
        if not complete:
            return None
        if year_month:
            return year_month if year_month in complete else None
        previous = self._previous_calendar_month_bounds()[0][:7]
        if previous in complete:
            return previous
        return complete[0]

    def _longevity_snapshot_from_progression(
        self,
        progression: Dict,
        as_of: str,
        limit: int = 10,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
        standing_only: bool = False,
    ) -> Tuple[List[Dict], int]:
        """Top longevity holds and year-old+ standing count as of a date, from progression."""
        holds: List[Dict] = []
        for category, flips in progression.items():
            if not flips:
                continue
            if not self._category_matches_filters(
                category,
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            ):
                continue
            for i, flip in enumerate(flips):
                start = flip.get("d")
                if not start or start > as_of:
                    continue
                next_flip = flips[i + 1] if i + 1 < len(flips) else None
                next_date = next_flip.get("d") if next_flip else None
                if next_date and next_date <= as_of:
                    effective_end = next_date
                    still_standing = False
                else:
                    effective_end = as_of
                    still_standing = True
                days = self._hold_day_count(start, effective_end)
                holds.append({
                    "category": category,
                    "playerName": flip.get("n") or "Unknown",
                    "playerId": flip.get("i"),
                    "time": flip.get("t") or "",
                    "weblink": flip.get("w"),
                    "start": start,
                    "end": effective_end,
                    "days": days,
                    "stillStanding": still_standing,
                })

        holds.sort(key=lambda item: (-item["days"], item["start"]))
        standing = [item for item in holds if item["stillStanding"]]
        remaining_old = sum(
            1 for item in standing[:50] if item["days"] >= MIN_OLDEST_HOLD_DAYS
        )
        ranked = standing if standing_only else holds
        return ranked[:limit], remaining_old

    async def _get_longevity_items(
        self,
        mode: str = "standing",
        tied: Optional[str] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
        limit: int = 50,
    ) -> Optional[List[Dict]]:
        filters = dict(
            game_mode=game_mode,
            apple_amount=apple_amount,
            speed=speed,
            size=size,
            run_mode=run_mode,
        )
        items = await github_cache_fetcher.get_longevity(mode)
        if items is None:
            return None
        items = self._filter_category_rows(items, **filters)
        items = self._filter_longevity_tied(items, tied)
        return items[:limit]

    def _format_hold_duration(self, start: str, end: str) -> str:
        """Human duration like '5 years, 4 months and 23 days'."""
        try:
            s = datetime.fromisoformat(start).date()
            e = datetime.fromisoformat(end).date()
        except ValueError:
            return "unknown duration"

        years = e.year - s.year
        months = e.month - s.month
        days = e.day - s.day
        if days < 0:
            months -= 1
            prev_month = e.month - 1 or 12
            prev_year = e.year if e.month > 1 else e.year - 1
            days += monthrange(prev_year, prev_month)[1]
        if months < 0:
            years -= 1
            months += 12

        parts = []
        if years:
            parts.append(f"{years} year" + ("s" if years != 1 else ""))
        if months:
            parts.append(f"{months} month" + ("s" if months != 1 else ""))
        if days or not parts:
            parts.append(f"{days} day" + ("s" if days != 1 else ""))
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        return f"{parts[0]}, {parts[1]} and {parts[2]}"

    def _hold_day_count(self, start: str, end: str) -> int:
        try:
            return (datetime.fromisoformat(end).date() - datetime.fromisoformat(start).date()).days
        except ValueError:
            return 0

    async def get_monthly_oldest_report_data(
        self, year_month: Optional[str] = None
    ) -> Optional[Dict]:
        """Build the monthly oldest-records report purely from FastSnakeStats.

        Uses only statistics-explorer.json (progression) from the FastSnakeStats
        GitHub cache — no Discord message history or manual lists.
        Computed on the fly each time /monthly or the scheduled post runs.

        year_month: optional YYYY-MM; default is the latest fully complete month
        (preferring the previous calendar month when FastSnakeStats has it).
        """
        try:
            resolved = await self.resolve_monthly_year_month(year_month)
            if not resolved:
                return None
            bounds = self._year_month_bounds(resolved)
            if not bounds:
                return None
            period_start, period_end, period_label = bounds

            explorer = await github_cache_fetcher.fetch_statistics_explorer(force_refresh=True)
            if not explorer:
                return None

            progression = explorer.get("progression") or {}
            beaten: List[Dict] = []
            for category, flips in progression.items():
                if not flips or len(flips) < 2:
                    continue
                for i in range(len(flips) - 1):
                    start = flips[i].get("d")
                    end = flips[i + 1].get("d")
                    if not start or not end:
                        continue
                    if end < period_start or end > period_end:
                        continue
                    days = self._hold_day_count(start, end)
                    if days < MIN_OLDEST_HOLD_DAYS:
                        continue
                    beaten.append({
                        "category": category,
                        "old_player": flips[i].get("n") or "Unknown",
                        "new_player": flips[i + 1].get("n") or "Unknown",
                        "start": start,
                        "end": end,
                        "days": days,
                        "duration": self._format_hold_duration(start, end),
                        "old_time": flips[i].get("t") or "",
                        "new_time": flips[i + 1].get("t") or "",
                        "old_weblink": flips[i].get("w"),
                        "new_weblink": flips[i + 1].get("w"),
                    })

            beaten.sort(key=lambda item: (-item["days"], item["end"]))
            total_beaten = len(beaten)
            beaten = beaten[:MONTHLY_BEATEN_LIMIT]

            oldest_top, remaining_old = self._longevity_snapshot_from_progression(
                progression, period_end, limit=10
            )

            return {
                "period_start": period_start,
                "period_end": period_end,
                "period_label": period_label,
                "year_month": resolved,
                "min_days": MIN_OLDEST_HOLD_DAYS,
                "beaten": beaten,
                "total_beaten": total_beaten,
                "remaining_old": remaining_old,
                "oldest_top": oldest_top,
            }
        except Exception as e:
            print(f"Error getting monthly oldest report data: {e}")
            return None

    def create_monthly_beaten_embed(self, report_data: Dict) -> discord.Embed:
        """Embed listing longstanding records beaten in the period (no pagination)."""
        beaten = report_data["beaten"]
        min_days = report_data.get("min_days", MIN_OLDEST_HOLD_DAYS)
        total_beaten = report_data.get("total_beaten", len(beaten))

        embed = discord.Embed(
            title=f"📅 Monthly Oldest Records — {report_data['period_label']}",
            description=(
                f"The longest-standing records beaten between "
                f"**{report_data['period_start']}** and **{report_data['period_end']}** "
                f"(holds of **{min_days}+** days)."
            ),
            color=0xe67e22,
            timestamp=datetime.now(),
        )
        shown_note = ""
        if total_beaten > len(beaten):
            shown_note = f"\nShowing the **{len(beaten)}** longest of **{total_beaten}**"
        embed.add_field(
            name="📊 Summary",
            value=(
                f"**{total_beaten}** record"
                f"{'' if total_beaten == 1 else 's'} over a year old beaten"
                f"{shown_note}\n"
                f"**{report_data['remaining_old']}** holds of {min_days}+ days still standing"
            ),
            inline=False,
        )

        if not beaten:
            embed.add_field(
                name="🏆 Beaten Holds",
                value=f"No holds of {min_days}+ days fell this month.",
                inline=False,
            )
        else:
            lines = []
            for i, item in enumerate(beaten, 1):
                run_mode = item["category"].split("|")[4] if "|" in item["category"] else ""
                old_time = self._format_explorer_time(item.get("old_time", ""), run_mode)
                new_time = self._format_explorer_time(item.get("new_time", ""), run_mode)
                if item.get("old_weblink") and old_time != "N/A":
                    old_time = f"[{old_time}]({item['old_weblink']})"
                if item.get("new_weblink") and new_time != "N/A":
                    new_time = f"[{new_time}]({item['new_weblink']})"
                lines.append(
                    f"**{i}.** {self._format_category_line(item['category'])}\n"
                    f"**{item['old_player']}** → **{item['new_player']}** · "
                    f"after **{item['duration']}**\n"
                    f"{old_time} → {new_time} · beaten `{item['end']}`"
                )
            # Split across fields to stay under Discord's 1024-char field limit
            chunk_size = 3
            for chunk_start in range(0, len(lines), chunk_size):
                chunk = lines[chunk_start:chunk_start + chunk_size]
                start_n = chunk_start + 1
                end_n = chunk_start + len(chunk)
                name = "🏆 Beaten Holds" if chunk_start == 0 else f"🏆 Beaten Holds ({start_n}–{end_n})"
                embed.add_field(name=name, value="\n\n".join(chunk), inline=False)

        embed.set_footer(text="Data from FastSnakeStats • Monthly oldest update")
        return embed

    def create_monthly_oldest_embed(self, report_data: Dict) -> discord.Embed:
        """Embed for the top 10 longest holds as of the report month end."""
        embed = discord.Embed(
            title=f"⏳ Top 10 Oldest Holds — as of {report_data['period_end']}",
            description=(
                "Longest holds as of that month’s end. "
                "● still a WR then · ○ no longer a WR by then."
            ),
            color=0x9b59b6,
            timestamp=datetime.now(),
        )
        lines = []
        for i, item in enumerate(report_data.get("oldest_top") or [], 1):
            category = item.get("category", "")
            standing = bool(item.get("stillStanding"))
            name = item.get("playerName", "Unknown")
            days = item.get("days", "?")
            start = item.get("start", "?")
            end_label = "present" if standing else item.get("end", "?")
            time_str = self._format_linked_hold_time(item)
            cat = self._format_category_line(category)
            status = "still WR" if standing else "fallen"
            marker = "●" if standing else "○"
            lines.append(
                f"**{i}.** {marker} **{days}d** — **{name}** — {cat}\n"
                f"{time_str} · `{start}` → `{end_label}` · {status}"
            )
        if not lines:
            embed.add_field(
                name="All-Time Longevity",
                value="No longevity data available.",
                inline=False,
            )
        else:
            mid = 5
            embed.add_field(
                name="All-Time Longevity (1–5)",
                value="\n\n".join(lines[:mid]),
                inline=False,
            )
            if len(lines) > mid:
                embed.add_field(
                    name="All-Time Longevity (6–10)",
                    value="\n\n".join(lines[mid:]),
                    inline=False,
                )
        embed.set_footer(text="Data from FastSnakeStats • Monthly oldest update")
        return embed

    def build_monthly_report_embeds(self, report_data: Dict) -> List[discord.Embed]:
        return [
            self.create_monthly_beaten_embed(report_data),
            self.create_monthly_oldest_embed(report_data),
        ]

    async def post_monthly_oldest_report(self, channel) -> bool:
        """Post the monthly oldest-records update to a channel."""
        report_data = await self.get_monthly_oldest_report_data()
        if not report_data:
            await channel.send("❌ Unable to build the monthly oldest-records report.")
            return False

        await channel.send(embeds=self.build_monthly_report_embeds(report_data))
        return True

    @tasks.loop(time=time(hour=12, minute=0, tzinfo=MONTHLY_REPORT_TZ))
    async def monthly_oldest_report_task(self):
        """Post on the 1st of each month at 12:00 (UTC+3 by default)."""
        now = datetime.now(MONTHLY_REPORT_TZ)
        if now.day != 1:
            return
        channel = self.bot.get_channel(GOOGLE_SNAKE_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(GOOGLE_SNAKE_CHANNEL_ID)
            except Exception as e:
                print(f"Monthly report: could not fetch channel {GOOGLE_SNAKE_CHANNEL_ID}: {e}")
                return
        try:
            print(f"Posting monthly oldest report to #{getattr(channel, 'name', GOOGLE_SNAKE_CHANNEL_ID)}")
            await self.post_monthly_oldest_report(channel)
        except Exception as e:
            print(f"Error posting monthly oldest report: {e}")

    @monthly_oldest_report_task.before_loop
    async def before_monthly_oldest_report_task(self):
        await self.bot.wait_until_ready()

    def _watch_holder_line(self, runs: Optional[List]) -> str:
        if not runs:
            return "unheld"
        names = [dm.get_player_name(run) for run in runs]
        time_str = dm.get_run_time(runs[0])
        parts = (runs[0].get("date") and str(runs[0].get("date"))) or ""
        label = ", ".join(n for n in names if n)
        return f"{label or 'Unknown'} · {time_str}" + (f" ({parts})" if parts else "")

    async def _check_wr_watches(self) -> None:
        state = wr_watch.load_state()
        watches = state.get("watches") or []
        if not watches:
            return
        records = await github_cache_fetcher.fetch_current_world_records()
        if not records:
            print("[wr-watch] No records available; skipping probe")
            return

        flips: Dict[str, Dict] = {}
        for watch in watches:
            category = watch.get("category") or ""
            runs = records.get(category) or []
            fingerprint = wr_watch.fingerprint_runs(runs)
            previous = watch.get("fingerprint") or ""
            if previous == fingerprint:
                continue
            old_player = watch.get("player") or "unheld"
            old_time = watch.get("time") or "—"
            new_line = self._watch_holder_line(runs)
            wr_watch.update_watch_snapshot(
                watch.get("id") or "",
                fingerprint,
                dm.get_player_name(runs[0]) if runs else "unheld",
                dm.get_run_time(runs[0]) if runs else "—",
            )
            flips.setdefault(category, {"old": f"{old_player} · {old_time}", "new": new_line, "pings": {}})
            channel_id = int(watch.get("channel_id") or 0)
            user_id = int(watch.get("user_id") or 0)
            flips[category]["pings"].setdefault(channel_id, set()).add(user_id)

        for category, payload in flips.items():
            line = (
                f"{self._format_category_line(category)} was updated!\n"
                f"was: {payload['old']}\n"
                f"now: {payload['new']}"
            )
            for channel_id, user_ids in payload["pings"].items():
                mentions = " ".join(f"<@{uid}>" for uid in sorted(user_ids))
                message = f"{mentions}\n{line}" if mentions else line
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except Exception as error:
                        print(f"[wr-watch] Could not fetch channel {channel_id}: {error}")
                        continue
                try:
                    await channel.send(message)
                except Exception as error:
                    print(f"[wr-watch] Failed to announce {category}: {error}")

    @tasks.loop(hours=24)
    async def wr_watch_task(self) -> None:
        try:
            print("[wr-watch] Probing watched categories…")
            await self._check_wr_watches()
        except Exception as error:
            print(f"[wr-watch] Probe failed: {error}")

    @wr_watch_task.before_loop
    async def before_wr_watch_task(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(120)
    
    def _calculate_improvement(self, old_run: dict, new_run: dict) -> Optional[float]:
        """Calculate time improvement in milliseconds"""
        try:
            old_time_str = dm.get_run_time(old_run)
            new_time_str = dm.get_run_time(new_run)
            
            # Convert time strings to milliseconds for comparison
            old_ms = self._time_to_milliseconds(old_time_str)
            new_ms = self._time_to_milliseconds(new_time_str)
            
            if old_ms and new_ms:
                return old_ms - new_ms  # Positive means improvement
            return None
        except Exception as e:
            print(f"Error calculating improvement: {e}")
            return None
    
    def _time_to_milliseconds(self, time_str: str) -> Optional[float]:
        """Convert time string to milliseconds"""
        try:
            if not time_str or time_str == "N/A":
                return None
            
            # Handle format like "1h 2m 3s 456ms"
            total_ms = 0
            
            # Extract hours
            if 'h' in time_str:
                parts = time_str.split('h')
                hours = int(parts[0])
                total_ms += hours * 3600 * 1000
                time_str = parts[1]
            
            # Extract minutes
            if 'm' in time_str:
                parts = time_str.split('m')
                minutes = int(parts[0])
                total_ms += minutes * 60 * 1000
                time_str = parts[1]
            
            # Extract seconds
            if 's' in time_str:
                parts = time_str.split('s')
                seconds = float(parts[0])
                total_ms += seconds * 1000
                time_str = parts[1]
            
            # Extract milliseconds
            if 'ms' in time_str:
                ms = int(time_str.replace('ms', '').strip())
                total_ms += ms
            
            return total_ms
        except Exception as e:
            print(f"Error converting time to milliseconds: {e}")
            return None
    
    async def get_date_choices(self) -> List[app_commands.Choice[str]]:
        """Get available dates as choices for command parameters"""
        try:
            dates = await github_cache_fetcher.get_available_dates()
            if not dates:
                return []
            
            # Create choices from available dates (most recent first)
            choices = []
            for date in reversed(dates):  # Most recent first
                choices.append(app_commands.Choice(name=date, value=date))
            
            return choices
        except Exception as e:
            print(f"Error getting date choices: {e}")
            return []
    
    async def record_date_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for date parameter in record command"""
        return await self.get_date_choices()
    
    async def player_date_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for date parameter in player command"""
        return await self.get_date_choices()
    
    async def stats_date_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for date parameter in stats command"""
        return await self.get_date_choices()

    def _filter_setting_choices(self, options: List[str], current: str) -> List[app_commands.Choice[str]]:
        if current:
            needle = current.lower()
            options = [option for option in options if needle in option.lower()]
        return [app_commands.Choice(name=option, value=option) for option in options[:25]]

    async def player_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        names = await github_cache_fetcher.search_player_names(current, limit=25)
        return [app_commands.Choice(name=name, value=name) for name in names]

    async def record_game_mode_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        return self._filter_setting_choices(dm.get_ordered_gamemodes(), current)

    async def record_apple_amount_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        return self._filter_setting_choices(dm.get_ordered_apple_amounts(), current)

    async def record_speed_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        return self._filter_setting_choices(dm.get_ordered_speeds(), current)

    async def record_size_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        return self._filter_setting_choices(dm.get_ordered_sizes(), current)

    async def record_run_mode_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        return self._filter_setting_choices(dm.get_ordered_run_modes(), current)

    async def list_run_mode_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """Run modes for explorer list filters, including Timed (all non-HS)."""
        options = ["Timed"] + dm.get_ordered_run_modes()
        return self._filter_setting_choices(options, current)

    async def mastery_game_mode_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """Modes for Mastery filters, including HS-only / excluding-Peaceful groups."""
        options = list(MASTERY_MODE_GROUPS) + dm.get_ordered_gamemodes()
        return self._filter_setting_choices(options, current)

    async def list_game_mode_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """Modes for explorer list filters, including High score modes only."""
        options = list(LIST_MODE_GROUPS) + dm.get_ordered_gamemodes()
        return self._filter_setting_choices(options, current)
    
    def get_random_combination(
        self,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> Optional[Dict]:
        """Pick a random valid category, optionally filtered by settings/tier."""
        pool = dm.filter_valid_categories(
            game_mode=game_mode,
            apple_amount=apple_amount,
            speed=speed,
            size=size,
            run_mode=run_mode,
            tier=tier,
        )
        # Hard exclude impossible boards (e.g. 100 Apples on Small)
        filtered_pool = []
        for key in pool:
            parts = dm.parse_category_parts(key)
            if not dm.is_valid_category(
                parts["apple_amount"],
                parts["speed"],
                parts["size"],
                parts["game_mode"],
                parts["run_mode"],
            ):
                continue
            filtered_pool.append(key)
        pool = filtered_pool
        if not pool:
            return None

        settings_key = random.choice(pool)
        parts = dm.parse_category_parts(settings_key)
        if parts["run_mode"] == "100 Apples" and parts["size"] == "Small":
            return None
        scored = dm.score_category(settings_key)
        return {
            "settings_key": settings_key,
            "game_mode": parts["game_mode"],
            "apple_amount": parts["apple_amount"],
            "speed": parts["speed"],
            "size": parts["size"],
            "run_mode": parts["run_mode"],
            "tier": scored["tier"],
            "score": scored["score"],
        }

    async def random_size_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        options = dm.get_ordered_sizes()
        chosen_run = getattr(interaction.namespace, "run_mode", None)
        if chosen_run == "100 Apples":
            options = [s for s in options if s != "Small"]
        return self._filter_setting_choices(options, current)

    async def random_run_mode_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        options = dm.get_ordered_run_modes()
        chosen_size = getattr(interaction.namespace, "size", None)
        chosen_mode = getattr(interaction.namespace, "game_mode", None)
        if chosen_size == "Small":
            options = [r for r in options if r != "100 Apples"]
        if chosen_mode:
            chosen_apple = getattr(interaction.namespace, "apple_amount", None)
            if chosen_apple:
                if not dm.allows_high_score(chosen_apple, chosen_mode):
                    options = [r for r in options if r != "High Score"]
            elif not (
                dm.is_high_score_mode(chosen_mode)
                or dm.is_tally_ce_highscore_mode(chosen_mode)
            ):
                options = [r for r in options if r != "High Score"]
        return self._filter_setting_choices(options, current)
    
    def create_record_embed(self, record_data: Dict, settings_key: str) -> discord.Embed:
        """Create a rich embed for record display"""
        run = record_data['run']
        
        embed = discord.Embed(
            title=f"🏆 World Record — {dm.format_category_key(settings_key)}",
            color=0x00ff00,  # Green for records
            timestamp=datetime.now()
        )
        
        # Add fields
        embed.add_field(
            name="Player",
            value=dm.get_player_name(run),
            inline=True
        )
        
        embed.add_field(
            name="Time",
            value=dm.get_run_time(run),
            inline=True
        )
        
        embed.add_field(
            name="Date",
            value=dm.get_run_date(run),
            inline=True
        )
        
        embed.add_field(
            name="Rank",
            value="#1",
            inline=True
        )
        
        # Add footer
        embed.set_footer(text=f"Data from FastSnakeStats • {record_data['date']}")
        
        return embed
    
    def _format_player_career_stats(
        self, peak_stats: Optional[Dict], career: Optional[Dict] = None
    ) -> str:
        """Match FastSnakeStats search-player career summary."""
        lines = []
        total_dates = (peak_stats or {}).get('totalDates')
        total_records = (peak_stats or {}).get('totalRecords')
        if total_dates is not None:
            lines.append(f"**Dates:** {total_dates}")
        if total_records is not None:
            lines.append(f"**Total WRs:** {total_records}")

        if career:
            if career.get('wrDays') is not None:
                lines.append(f"**WR-days:** {career['wrDays']}")
            if career.get('wrDaysUntied') is not None:
                lines.append(f"**Untied WR-days:** {career['wrDaysUntied']}")
            if career.get('wrDaysTied') is not None:
                lines.append(f"**Tied WR-days:** {career['wrDaysTied']}")
            if career.get('holds') is not None:
                lines.append(f"**Holds:** {career['holds']}")
            if career.get('standingHolds') is not None:
                lines.append(f"**Still standing:** {career['standingHolds']}")

        return "\n".join(lines) if lines else "No career metadata available."

    def _format_player_peak_stats(self, peak_stats: Optional[Dict]) -> str:
        if not peak_stats:
            return "No historical peak data available."

        lines = []
        peak_records = peak_stats.get('peakRecords') or {}
        peak_pct = peak_stats.get('peakPercentage') or {}
        latest = peak_stats.get('latest') or {}

        if peak_records.get('count') is not None and peak_records.get('date'):
            lines.append(
                f"**Peak Records:** {peak_records['count']} on {peak_records['date']}"
            )
        if peak_pct.get('percentage') is not None and peak_pct.get('date'):
            lines.append(
                f"**Peak Percentage:** {peak_pct['percentage']:.2f}% on {peak_pct['date']}"
            )
        if latest.get('date') and (
            latest.get('count') is not None or latest.get('percentage') is not None
        ):
            count = latest.get('count', '?')
            pct = latest.get('percentage')
            pct_text = f", {pct:.2f}%" if pct is not None else ""
            lines.append(f"**Latest snapshot:** {count} records{pct_text} on {latest['date']}")
        return "\n".join(lines) if lines else "No historical peak data available."

    def _format_player_longevity_line(self, label: str, item: Optional[Dict]) -> str:
        if not item:
            return f"**{label}:** None"
        time_str = self._format_linked_hold_time(item)
        end_label = "present" if item.get('stillStanding') else item.get('end', '?')
        return (
            f"**{label}:** **{item.get('days', '?')} days** — "
            f"{self._format_category_line(item.get('category', ''))} — "
            f"{time_str} • `{item.get('start', '?')}` → `{end_label}`"
        )

    def _format_player_improving(self, improving: Optional[Dict]) -> str:
        if not improving:
            return "No recent WR gains in explorer windows."
        order = ["7d", "30d", "90d", "365d"]
        lines = []
        for window in order:
            row = improving.get(window)
            if not row:
                continue
            lines.append(
                f"**{window}:** +{row.get('delta', 0)} "
                f"({row.get('startCount', '?')} → {row.get('endCount', '?')})"
            )
        return "\n".join(lines) if lines else "No recent WR gains in explorer windows."

    def _format_player_mastery_stats(self, mastery: Optional[Dict]) -> str:
        if not mastery:
            return "No Mastery Challenge completions yet."
        total = mastery.get("total")
        board_count = mastery.get("boardCount") or 1386
        bs = mastery.get("bySpeed") or {}
        bz = mastery.get("bySize") or {}
        lines = [
            f"**Boards:** {total} / {board_count}",
            f"N **{bs.get('Normal', 0)}** · F **{bs.get('Fast', 0)}** · S **{bs.get('Slow', 0)}**",
            f"Std **{bz.get('Standard', 0)}** · Sm **{bz.get('Small', 0)}** · Lg **{bz.get('Large', 0)}**",
            "_Use `/player holds:Mastery` or `/mastery` for details._",
        ]
        return "\n".join(lines)

    def _format_player_empire(self, empire: Optional[Dict]) -> str:
        """Chronicle empire arc summary for a player profile."""
        if not empire:
            return "No Chronicle empire arc yet."
        lines = []
        peak = empire.get("peak") or {}
        latest = empire.get("latest") or {}
        if peak.get("count") is not None and peak.get("date"):
            lines.append(f"**Peak:** {peak['count']} WRs on `{peak['date']}`")
        if latest.get("count") is not None and latest.get("date"):
            pct = latest.get("percentage")
            pct_text = f" ({pct}%)" if pct is not None else ""
            lines.append(f"**Now:** {latest['count']} WRs{pct_text} on `{latest['date']}`")
        if empire.get("peakDrop") is not None:
            lines.append(f"**Drop from peak:** −{empire['peakDrop']}")
        tps = empire.get("turningPoints") or []
        if tps:
            tp = tps[0]
            sign = "+" if (tp.get("delta") or 0) >= 0 else ""
            lines.append(
                f"**Biggest turn:** `{tp.get('date')}` {sign}{tp.get('delta')} "
                f"({tp.get('from')} → {tp.get('to')})"
            )
        lines.append("_Use `/chronicle section:Empire` for the full arc._")
        return "\n".join(lines) if lines else "No Chronicle empire arc yet."

    def create_player_embed(self, player_data: Dict, page: int = 0) -> discord.Embed:
        """Create a rich embed for player display with pagination"""
        activity = player_data.get('recent_activity') or []
        runs_per_page = 5
        total_pages = max(1, (len(activity) + runs_per_page - 1) // runs_per_page)
        page = max(0, min(page, total_pages - 1))

        embed = discord.Embed(
            title=f"👤 Player Profile - {player_data['player_name']}",
            color=0x0099ff,
            timestamp=datetime.now()
        )

        current_pct = player_data.get('current_percentage')
        pct_text = (
            f" • **{current_pct:.2f}%**"
            if current_pct is not None else ""
        )
        embed.add_field(
            name="📊 Current Snapshot",
            value=(
                f"**World Records:** {player_data['world_records_held']}{pct_text}\n"
                f"**As of:** `{player_data['date']}`"
            ),
            inline=False
        )

        embed.add_field(
            name="📚 Career",
            value=self._format_player_career_stats(
                player_data.get('peak_stats'),
                player_data.get('career'),
            ),
            inline=False
        )

        embed.add_field(
            name="🏅 Mastery",
            value=self._format_player_mastery_stats(player_data.get('mastery')),
            inline=False
        )

        embed.add_field(
            name="📈 Peaks",
            value=self._format_player_peak_stats(player_data.get('peak_stats')),
            inline=False
        )

        empire = player_data.get('empire')
        if empire:
            embed.add_field(
                name="🏰 Empire",
                value=self._format_player_empire(empire),
                inline=False
            )

        longevity = player_data.get('longevity_best') or {}
        embed.add_field(
            name="⏳ Longevity",
            value=(
                self._format_player_longevity_line("Best all-time", longevity.get('allTime'))
                + "\n"
                + self._format_player_longevity_line("Best still standing", longevity.get('standing'))
            ),
            inline=False
        )

        improving = player_data.get('improving')
        if improving:
            embed.add_field(
                name="🚀 Improving",
                value=self._format_player_improving(improving),
                inline=False
            )

        if activity:
            start_idx = page * runs_per_page
            page_runs = activity[start_idx:start_idx + runs_per_page]
            recent_text = ""
            for i, record in enumerate(page_runs, start_idx + 1):
                settings_parts = record['settings'].split('|')
                run_mode = settings_parts[4] if len(settings_parts) > 4 else ""
                category_info = dm.format_category_key(record['settings'])
                display_info = self._format_time_for_display(
                    dm.get_run_time(record['run']), run_mode
                )
                date = dm.get_run_date(record['run'])
                run_link = dm.get_run_link(record['run'])
                if run_link:
                    recent_text += f"{i}. **{category_info}**\n   {display_info} • {date} • [View Run]({run_link})\n\n"
                else:
                    recent_text += f"{i}. **{category_info}**\n   {display_info} • {date}\n\n"
            if not recent_text:
                recent_text = "No more runs to show."
            embed.add_field(name="🕒 Current Holds", value=recent_text, inline=False)
        else:
            embed.add_field(
                name="🕒 Current Holds",
                value="No current world records held.",
                inline=False
            )

        embed.set_footer(
            text=f"Data from FastSnakeStats • {player_data['date']} • Page {page + 1}/{total_pages}"
        )
        return embed

    def create_stats_embed(self, stats_data: Dict, page: int = 0) -> discord.Embed:
        """Create a rich embed for stats display with pagination"""
        embed = discord.Embed(
            title="📊 Top Record Holders",
            color=0xff9900,  # Orange for statistics
            timestamp=datetime.now()
        )
        
        # Add top by percentage with pagination
        players_per_page = 10
        start_idx = page * players_per_page
        end_idx = start_idx + players_per_page
        page_players = stats_data['top_by_percentage'][start_idx:end_idx]
        
        top_by_percentage_text = ""
        for i, (player, count) in enumerate(page_players, start_idx + 1):
            percentage = (count / stats_data['total_world_records']) * 100
            top_by_percentage_text += f"{i}. **{player}** - **{count}** records • {percentage:.1f}%\n"
        
        if not top_by_percentage_text:
            top_by_percentage_text = "No more players to show."
        
        embed.add_field(
            name="🏆 Most Records",
            value=top_by_percentage_text,
            inline=False
        )
        
        # Add total world records at the bottom
        embed.add_field(
            name="📈 Total World Records",
            value=str(stats_data['total_world_records']),
            inline=False
        )
        
        # Add footer with page info
        total_pages = (len(stats_data['top_by_percentage']) + players_per_page - 1) // players_per_page
        embed.set_footer(text=f"Data from FastSnakeStats • {stats_data['date']} • Page {page + 1}/{total_pages}")
        
        return embed
    
    def create_weekly_report_embed(self, report_data: Dict, page: int = 0) -> discord.Embed:
        """Create a rich embed for weekly report display with pagination"""
        embed = discord.Embed(
            title="📈 Weekly Record Report",
            description=f"Record changes from {report_data['week_ago_date']} to {report_data['current_date']}",
            color=0x00ff88,  # Green for reports
            timestamp=datetime.now()
        )
        
        # Add summary statistics
        embed.add_field(
            name="📊 Summary",
            value=f"**Total Changes:** {report_data['total_changes']}\n"
                  f"**New Records:** {len(report_data['new_records'])}\n"
                  f"**Record Changes:** {len(report_data['record_changes'])}\n"
                  f"**Improved Records:** {len(report_data['improved_records'])}",
            inline=False
        )
        
        # Determine what to show based on page
        items_per_page = 3
        all_items = []
        
        # Add new records
        for item in report_data['new_records']:
            all_items.append(('🆕', item, 'new'))
        
        # Add record changes
        for item in report_data['record_changes']:
            all_items.append(('🔄', item, 'change'))
        
        # Add improved records
        for item in report_data['improved_records']:
            all_items.append(('⚡', item, 'improved'))
        
        if not all_items:
            embed.add_field(
                name="📝 No Changes",
                value="No record changes were detected in the last 7 days.",
                inline=False
            )
        else:
            # Paginate through all items
            start_idx = page * items_per_page
            end_idx = start_idx + items_per_page
            page_items = all_items[start_idx:end_idx]
            
            changes_text = ""
            for emoji, item, item_type in page_items:
                settings_parts = item['settings'].split('|')
                run_mode = settings_parts[4]
                category_info = dm.format_category_key(record['settings'])
                
                if item_type == 'new':
                    display_time = self._format_time_for_display(item['time'], run_mode)
                    changes_text += f"{emoji} **NEW RECORD** - {category_info}\n"
                    changes_text += f"   👤 **{item['player']}** • {display_time} • {item['date']}\n\n"
                
                elif item_type == 'change':
                    old_display_time = self._format_time_for_display(item['old_time'], run_mode)
                    new_display_time = self._format_time_for_display(item['new_time'], run_mode)
                    changes_text += f"{emoji} **RECORD CHANGE** - {category_info}\n"
                    changes_text += f"   🔄 **{item['old_player']}** → **{item['new_player']}**\n"
                    changes_text += f"   ⏱️ {old_display_time} → {new_display_time}\n"
                    if item['improvement']:
                        improvement_str = self._format_improvement(item['improvement'])
                        changes_text += f"   📈 Improvement: {improvement_str}\n"
                    changes_text += f"   📅 {item['new_date']}\n\n"
                
                elif item_type == 'improved':
                    old_display_time = self._format_time_for_display(item['old_time'], run_mode)
                    new_display_time = self._format_time_for_display(item['new_time'], run_mode)
                    changes_text += f"{emoji} **IMPROVED RECORD** - {category_info}\n"
                    changes_text += f"   👤 **{item['player']}**\n"
                    changes_text += f"   ⏱️ {old_display_time} → {new_display_time}\n"
                    if item['improvement']:
                        improvement_str = self._format_improvement(item['improvement'])
                        changes_text += f"   📈 Improvement: {improvement_str}\n"
                    changes_text += f"   📅 {item['new_date']}\n\n"
            
            if not changes_text:
                changes_text = "No more changes to show."
            
            embed.add_field(
                name="📝 Record Changes",
                value=changes_text,
                inline=False
            )
        
        # Add footer with page info
        total_pages = (len(all_items) + items_per_page - 1) // items_per_page
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        
        return embed
    
    def _format_improvement(self, improvement_ms: float) -> str:
        """Format improvement time in a readable way"""
        if improvement_ms < 1000:
            return f"{improvement_ms:.0f}ms"
        elif improvement_ms < 60000:
            seconds = improvement_ms / 1000
            return f"{seconds:.1f}s"
        else:
            minutes = improvement_ms / 60000
            return f"{minutes:.1f}m"
    
    def _format_time_for_display(self, time_str: str, run_mode: str) -> str:
        """Format time string for display, handling High Score mode specially"""
        if run_mode == "High Score":
            # Check for both old format (0m 0s Xms) and new format (Xs Yms)
            if time_str.startswith("0m 0s ") or (time_str.endswith("ms") and "m " not in time_str and "h " not in time_str):
                # Extract the milliseconds part for High Score
                if time_str.startswith("0m 0s "):
                    score = time_str.replace("0m 0s ", "").replace("ms", "")
                else:
                    # New format: "Xs Yms" -> extract Y
                    score = time_str.split("s ")[1].replace("ms", "")
                return f"{score} apples"
            else:
                return time_str
        else:
            return time_str

    def _format_explorer_time(self, iso_time: str, run_mode: str) -> str:
        """Format ISO duration from explorer JSON, with High Score apple display."""
        return self._format_time_for_display(dm.parse_time(iso_time), run_mode)

    def _format_category_line(self, settings_key: str) -> str:
        return dm.format_category_key(settings_key)

    async def get_leaderboards_data(
        self, apple_amount: str, speed: str, size: str, date: Optional[str] = None
    ) -> Optional[Dict]:
        """Build full WR table for fixed apple/speed/size across all modes."""
        try:
            if apple_amount not in dm.APPLE_AMOUNTS or speed not in dm.SPEEDS or size not in dm.SIZES:
                return None
            if date and not await github_cache_fetcher.is_date_available(date):
                return None

            if date:
                world_records = await github_cache_fetcher.fetch_world_records_for_date(date)
            else:
                world_records = await github_cache_fetcher.fetch_current_world_records()

            if not world_records:
                return None

            prefix = f"{apple_amount}|{speed}|{size}|"
            mode_order = {name: i for i, name in enumerate(dm.get_ordered_gamemodes())}
            run_order = {name: i for i, name in enumerate(dm.get_ordered_run_modes())}
            rows = []

            for settings_key, runs in world_records.items():
                if not settings_key.startswith(prefix) or not runs:
                    continue
                parts = settings_key.split('|')
                if len(parts) != 5:
                    continue
                gamemode, run_mode = parts[3], parts[4]
                best = runs[0]
                time_str = dm.get_run_time(best)
                rows.append({
                    'settings': settings_key,
                    'gamemode': gamemode,
                    'run_mode': run_mode,
                    'player': dm.get_player_name(best),
                    'time': self._format_time_for_display(time_str, run_mode),
                    'date': dm.get_run_date(best),
                    'link': dm.get_run_link(best),
                })

            rows.sort(
                key=lambda r: (
                    mode_order.get(r['gamemode'], 999),
                    run_order.get(r['run_mode'], 999),
                )
            )

            return {
                'apple_amount': apple_amount,
                'speed': speed,
                'size': size,
                'rows': rows,
                'date': date or await github_cache_fetcher.get_most_recent_date(),
            }
        except Exception as e:
            print(f"Error getting leaderboards data: {e}")
            return None

    async def activity_year_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        heatmap = await github_cache_fetcher.get_activity_heatmap()
        years = sorted({entry.get('date', '')[:4] for entry in (heatmap or []) if entry.get('date')}, reverse=True)
        if current:
            years = [year for year in years if current in year]
        return [app_commands.Choice(name=year, value=year) for year in years[:25]]

    async def monthly_month_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete from live FastSnakeStats complete-month scan (no hardcoding)."""
        months = await github_cache_fetcher.get_complete_year_months()
        needle = (current or "").strip().lower()
        choices: List[app_commands.Choice[str]] = []
        for ym in months:
            bounds = self._year_month_bounds(ym)
            label = bounds[2] if bounds else ym
            hay = f"{ym} {label}".lower()
            if needle and needle not in hay:
                continue
            choices.append(app_commands.Choice(name=f"{label} ({ym})", value=ym))
            if len(choices) >= 25:
                break
        return choices

    def create_progression_embed(self, settings_key: str, flips: List[Dict], page: int = 0) -> discord.Embed:
        items_per_page = 8
        total_pages = max(1, (len(flips) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_flips = flips[start:start + items_per_page]
        run_mode = settings_key.split('|')[4] if '|' in settings_key else ''

        embed = discord.Embed(
            title="📈 WR Progression",
            description=self._format_category_line(settings_key),
            color=0x3498db,
            timestamp=datetime.now()
        )
        lines = []
        for i, flip in enumerate(page_flips, start + 1):
            display_time = self._format_explorer_time(flip.get('t', ''), run_mode)
            lines.append(f"{i}. **{flip.get('d', 'N/A')}** — **{flip.get('n', 'Unknown')}** • {display_time}")
        embed.add_field(
            name="Timeline",
            value="\n".join(lines) if lines else "No progression data.",
            inline=False
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def create_longevity_embed(
        self,
        items: List[Dict],
        filter_mode: str,
        page: int = 0,
        filter_label: str = "",
    ) -> discord.Embed:
        items_per_page = 5
        total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = items[start:start + items_per_page]
        title_suffix = "Still Standing" if filter_mode == "standing" else "All-Time"
        title = f"⏳ Longest-Held WRs — {title_suffix}"
        if filter_label:
            title += f" — {filter_label}"

        embed = discord.Embed(
            title=title,
            color=0x9b59b6,
            timestamp=datetime.now()
        )
        lines = []
        for i, item in enumerate(page_items, start + 1):
            category = item.get('category', '')
            standing = " • still standing" if item.get('stillStanding') else ""
            end_label = "present" if item.get('stillStanding') else item.get('end', '?')
            lines.append(
                f"{i}. **{item.get('days', '?')} days** — **{item.get('playerName', 'Unknown')}** — "
                f"{self._format_category_line(category)} — "
                f"{self._format_linked_hold_time(item)} • "
                f"{item.get('start', '?')} → {end_label}{standing}"
            )
        embed.add_field(
            name="Holders",
            value="\n".join(lines) if lines else "No longevity data.",
            inline=False
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def _format_linked_hold_time(self, item: Dict) -> str:
        """Format hold time, linking to the SRC run when a weblink is present."""
        category = item.get('category', '')
        run_mode = category.split('|')[4] if '|' in category else ''
        display_time = self._format_explorer_time(item.get('time', ''), run_mode)
        link = item.get('weblink')
        if link and display_time and display_time != 'N/A':
            return f"[{display_time}]({link})"
        return display_time

    def create_improving_embed(self, items: List[Dict], window: str, page: int = 0) -> discord.Embed:
        items_per_page = 10
        total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = items[start:start + items_per_page]

        embed = discord.Embed(
            title=f"🚀 Improving Players — {window}",
            color=0x2ecc71,
            timestamp=datetime.now()
        )
        lines = []
        for i, item in enumerate(page_items, start + 1):
            lines.append(
                f"{i}. **{item.get('playerName', 'Unknown')}** — "
                f"**+{item.get('delta', 0)}** "
                f"({item.get('startCount', '?')} → {item.get('endCount', '?')})"
            )
        embed.add_field(
            name="Largest WR Gains",
            value="\n".join(lines) if lines else "No improving-player data for this window.",
            inline=False
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def _parse_category_parts(self, settings_key: str) -> Optional[Dict[str, str]]:
        parts = settings_key.split('|')
        if len(parts) != 5:
            return None
        return {
            'apple_amount': parts[0],
            'speed': parts[1],
            'size': parts[2],
            'game_mode': parts[3],
            'run_mode': parts[4],
        }

    def _category_matches_filters(
        self,
        settings_key: str,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ) -> bool:
        parts = self._parse_category_parts(settings_key)
        if not parts:
            return False
        checks = {
            'apple_amount': apple_amount,
            'speed': speed,
            'size': size,
        }
        for key, value in checks.items():
            if value and parts[key] != value:
                return False
        if game_mode == MASTERY_MODE_HS_ONLY:
            if parts['game_mode'] not in dm.HIGHSCORE_MODES:
                return False
        elif game_mode == MASTERY_MODE_NO_PEACEFUL:
            if parts['game_mode'] == "Peaceful":
                return False
        elif game_mode and parts['game_mode'] != game_mode:
            return False
        if run_mode == "Timed":
            if parts['run_mode'] == "High Score":
                return False
        elif run_mode and parts['run_mode'] != run_mode:
            return False
        return True

    def _format_category_filters(
        self,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
        tied: Optional[str] = None,
        show: Optional[str] = None,
        holds: Optional[str] = None,
    ) -> str:
        bits = [v for v in (game_mode, apple_amount, speed, size, run_mode) if v]
        if tied and tied != "all":
            bits.append(f"{tied} only")
        if show and show != "all":
            bits.append(show)
        if holds:
            bits.append(f"holds:{holds}")
        return " • ".join(bits)

    def _any_category_filters(
        self,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ) -> bool:
        return any((game_mode, apple_amount, speed, size, run_mode))

    def _filter_category_rows(
        self,
        items: List[Dict],
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ) -> List[Dict]:
        if not self._any_category_filters(game_mode, apple_amount, speed, size, run_mode):
            return items
        return [
            item for item in items
            if self._category_matches_filters(
                item.get('category', ''),
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            )
        ]

    def _filter_longevity_tied(self, items: List[Dict], tied: Optional[str] = None) -> List[Dict]:
        """Match FastSnakeStats longevity/career tied chips (missing tiedHolders => 1)."""
        if not tied or tied == "all":
            return items
        if tied == "untied":
            return [item for item in items if (item.get("tiedHolders") or 1) <= 1]
        if tied == "tied":
            return [item for item in items if (item.get("tiedHolders") or 1) > 1]
        return items

    def _filter_popularity_tied(self, items: List[Dict], tied: Optional[str] = None) -> List[Dict]:
        """Match FastSnakeStats popularity Both/Untied/Tied (0 = unheld present WR)."""
        if not tied or tied == "all":
            return items
        if tied == "untied":
            return [item for item in items if (item.get("tiedHolders") or 0) == 1]
        if tied == "tied":
            return [item for item in items if (item.get("tiedHolders") or 0) > 1]
        return items

    def _career_metrics(self, row: Dict, tied: Optional[str] = None) -> Dict:
        """Pick WR-days / best-hold fields for career tied mode."""
        if tied == "untied":
            return {
                "wrDays": row.get("wrDaysUntied") or 0,
                "bestAll": row.get("bestAllUntied"),
                "bestStanding": row.get("bestStandingUntied"),
            }
        if tied == "tied":
            return {
                "wrDays": row.get("wrDaysTied") or 0,
                "bestAll": row.get("bestAllTied"),
                "bestStanding": row.get("bestStandingTied"),
            }
        return {
            "wrDays": row.get("wrDays") or 0,
            "bestAll": row.get("bestAll"),
            "bestStanding": row.get("bestStanding"),
        }

    async def _get_player_hold_items(
        self,
        player_id: Optional[str] = None,
        player_name: Optional[str] = None,
        holds: str = "all",
        tied: Optional[str] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ) -> Optional[List[Dict]]:
        """Player hold history from longevity.all (FastSnakeStats Player tab)."""
        longevity = await github_cache_fetcher.get_longevity("all")
        if longevity is None:
            return None
        name_lower = (player_name or "").lower().strip()
        rows = []
        for row in longevity:
            if player_id and row.get("playerId") == player_id:
                rows.append(row)
            elif name_lower and (row.get("playerName") or "").lower() == name_lower:
                rows.append(row)

        hold_mode = holds or "all"
        if hold_mode == "present":
            rows = [r for r in rows if r.get("stillStanding")]
            rows = self._filter_longevity_tied(rows, tied)
        elif hold_mode == "old":
            rows = [r for r in rows if not r.get("stillStanding")]
        # all / latest keep every hold

        rows = self._filter_category_rows(
            rows,
            game_mode=game_mode,
            apple_amount=apple_amount,
            speed=speed,
            size=size,
            run_mode=run_mode,
        )

        if hold_mode == "old":
            rows.sort(
                key=lambda r: (
                    str(r.get("end") or ""),
                    r.get("days") or 0,
                    str(r.get("start") or ""),
                ),
                reverse=True,
            )
        elif hold_mode == "latest":
            rows.sort(
                key=lambda r: (
                    str(r.get("start") or ""),
                    1 if r.get("stillStanding") else 0,
                    r.get("days") or 0,
                ),
                reverse=True,
            )
        else:
            rows.sort(
                key=lambda r: (-(r.get("days") or 0), str(r.get("start") or ""))
            )
        return rows

    async def _build_ranked_category_lists_from_progression(
        self,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
        limit: int = 50,
    ) -> Optional[Dict[str, List[Dict]]]:
        """Rebuild contested/popularity/stale for a filter from full progression."""
        explorer = await github_cache_fetcher.fetch_statistics_explorer()
        if not explorer:
            return None
        progression = explorer.get('progression') or {}
        latest = ((explorer.get('meta') or {}).get('dateRange') or {}).get('latest')
        if not latest:
            latest = datetime.now().strftime('%Y-%m-%d')

        contested: List[Dict] = []
        popularity: List[Dict] = []
        stale: List[Dict] = []

        for category, flips in progression.items():
            if not flips:
                continue
            if not self._category_matches_filters(
                category,
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            ):
                continue

            holders = {flip.get('i') or flip.get('n') for flip in flips if flip.get('i') or flip.get('n')}
            flip_count = max(0, len(flips) - 1)
            first = flips[0].get('d') or latest
            last = flips[-1].get('d') or latest
            days_with_record = max(1, self._hold_day_count(first, latest) + 1)
            hold_days = self._hold_day_count(last, latest)
            row = {
                'category': category,
                'flips': flip_count,
                'uniqueHolders': len(holders),
                'tiedHolders': 1,
                'daysWithRecord': days_with_record,
                'holdStart': last,
                'holdDays': hold_days,
            }
            contested.append(row)
            # Match FastSnakeStats popularity exclusion
            parts = self._parse_category_parts(category) or {}
            if not (
                parts.get('game_mode') == 'Statue'
                and parts.get('run_mode') == 'High Score'
                and parts.get('size') == 'Small'
                and parts.get('apple_amount') == 'Bomb'
            ):
                popularity.append(row)
            if days_with_record > 0:
                stale.append(row)

        contested.sort(key=lambda r: (-r['flips'], -r['uniqueHolders']))
        popularity.sort(key=lambda r: (-r['uniqueHolders'], -r['daysWithRecord']))
        stale.sort(
            key=lambda r: (r['flips'], r['uniqueHolders'], r['tiedHolders'], -r['holdDays'])
        )
        return {
            'contested': contested[:limit],
            'popularity': popularity[:limit],
            'stale': stale[:limit],
        }

    async def _get_contested_items(self, limit: int = 50, **filters) -> Optional[List[Dict]]:
        items = await github_cache_fetcher.get_contested()
        if items is None:
            return None
        if self._any_category_filters(**filters):
            items = self._filter_category_rows(items, **filters)
        return items[:limit]

    async def _get_popularity_items(
        self, tied: Optional[str] = None, limit: int = 50, **filters
    ) -> Optional[List[Dict]]:
        items = await github_cache_fetcher.get_popularity()
        if items is None:
            return None
        if self._any_category_filters(**filters):
            items = self._filter_category_rows(items, **filters)
        items = self._filter_popularity_tied(items, tied)
        return items[:limit]

    async def _get_stale_items(self, limit: int = 50, **filters) -> Optional[List[Dict]]:
        items = await github_cache_fetcher.get_stale()
        if items is None:
            return None
        if self._any_category_filters(**filters):
            items = self._filter_category_rows(items, **filters)
        return items[:limit]

    async def _get_legends_items(
        self,
        show: str = "all",
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ) -> Optional[List[Dict]]:
        """Merged Legends + Unicorns list matching FastSnakeStats Show filter."""
        legends = await github_cache_fetcher.get_legends()
        unicorns = await github_cache_fetcher.get_unicorns()
        if legends is None and unicorns is None:
            return None
        tagged: List[Dict] = []
        if show in ("all", "legends"):
            for row in legends or []:
                tagged.append({**row, "legendType": "Legend"})
        if show in ("all", "unicorns"):
            for row in unicorns or []:
                tagged.append({**row, "legendType": "Unicorn"})
        tagged = self._filter_category_rows(
            tagged,
            game_mode=game_mode,
            apple_amount=apple_amount,
            speed=speed,
            size=size,
            run_mode=run_mode,
        )
        if show == "all":
            tagged.sort(
                key=lambda r: (
                    -(r.get("score") or 0),
                    0 if r.get("stillStanding") else 1,
                    -(r.get("days") or 0),
                    str(r.get("start") or ""),
                )
            )
        return tagged

    def _normalize_mastery_completion(self, item) -> Optional[Dict]:
        if isinstance(item, str):
            return {"category": item, "weblink": None, "time": None, "tier": None}
        if not isinstance(item, dict):
            return None
        category = item.get("category") or item.get("c")
        if not category:
            return None
        return {
            "category": category,
            "weblink": item.get("weblink"),
            "runId": item.get("runId"),
            "time": item.get("time"),
            "tier": item.get("tier"),
        }

    def _summarize_mastery_rows(self, rows: List[Dict]) -> Dict:
        by_speed = {"Normal": 0, "Fast": 0, "Slow": 0}
        by_size = {"Standard": 0, "Small": 0, "Large": 0}
        for row in rows:
            parts = self._parse_category_parts(row.get("category", ""))
            if not parts:
                continue
            if parts["speed"] in by_speed:
                by_speed[parts["speed"]] += 1
            if parts["size"] in by_size:
                by_size[parts["size"]] += 1
        return {"bySpeed": by_speed, "bySize": by_size, "total": len(rows)}

    def _count_mastery_universe(
        self,
        data: Dict,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
    ) -> int:
        meta = data.get("meta") or {}
        apples = [apple_amount] if apple_amount else list(
            meta.get("appleAmounts")
            or ["1 Apple", "3 Apples", "5 Apples", "10 Apples", "Dice", "Bomb", "Tally"]
        )
        speeds = [speed] if speed else list(meta.get("speeds") or ["Normal", "Fast", "Slow"])
        sizes = [size] if size else list(meta.get("sizes") or ["Standard", "Small", "Large"])
        all_modes = list(
            meta.get("modes")
            or dm.get_ordered_gamemodes()
        )
        if game_mode == MASTERY_MODE_HS_ONLY:
            modes = [m for m in all_modes if m in dm.HIGHSCORE_MODES]
        elif game_mode == MASTERY_MODE_NO_PEACEFUL:
            modes = [m for m in all_modes if m != "Peaceful"]
        elif game_mode:
            modes = [game_mode] if game_mode in all_modes else []
        else:
            modes = all_modes
        return len(apples) * len(speeds) * len(sizes) * len(modes)

    def _filter_mastery_completions(
        self,
        completed: List,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
    ) -> List[Dict]:
        rows = []
        for item in completed or []:
            row = self._normalize_mastery_completion(item)
            if not row:
                continue
            if not self._category_matches_filters(
                row["category"],
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
            ):
                continue
            rows.append(row)
        return rows

    async def _get_mastery_leaderboard(
        self,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        limit: int = 50,
    ) -> Optional[Dict]:
        data = await github_cache_fetcher.fetch_mastery_challenge()
        if not data:
            return None
        filters = dict(
            game_mode=game_mode,
            apple_amount=apple_amount,
            speed=speed,
            size=size,
        )
        board_count = self._count_mastery_universe(data, **filters)
        by_player = data.get("byPlayer") or {}
        rows = []
        community_seen: Dict[str, bool] = {}
        for player_id, entry in by_player.items():
            matched = self._filter_mastery_completions(entry.get("completed") or [], **filters)
            if not matched:
                continue
            metrics = self._summarize_mastery_rows(matched)
            rows.append({
                "playerId": player_id,
                "playerName": entry.get("playerName"),
                "total": metrics["total"],
                "bySpeed": metrics["bySpeed"],
                "bySize": metrics["bySize"],
            })
            for row in matched:
                community_seen[row["category"]] = True
        rows.sort(
            key=lambda r: (-(r.get("total") or 0), str(r.get("playerName") or ""))
        )
        community_rows = [{"category": c} for c in community_seen]
        community_metrics = self._summarize_mastery_rows(community_rows)
        inhuman_list = (data.get("meta") or {}).get("inhumanBoards") or []
        inhuman_universe = [
            c for c in inhuman_list
            if self._category_matches_filters(c, **filters)
        ]
        inhuman_have = sum(1 for c in inhuman_universe if community_seen.get(c))
        return {
            "meta": data.get("meta") or {},
            "board_count": board_count,
            "community": {
                "playerName": "Community Mastery",
                "community": True,
                "total": community_metrics["total"],
                "bySpeed": community_metrics["bySpeed"],
                "bySize": community_metrics["bySize"],
            },
            "inhuman_have": inhuman_have,
            "inhuman_max": len(inhuman_universe),
            "rows": rows[:limit],
            "player_count": len(rows),
            "filter_label": self._format_category_filters(**filters),
        }

    async def _get_player_mastery_items(
        self,
        player_id: Optional[str] = None,
        player_name: Optional[str] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
    ) -> Optional[Dict]:
        data = await github_cache_fetcher.fetch_mastery_challenge()
        if not data:
            return None
        entry = await github_cache_fetcher.get_mastery_player(
            player_id=player_id, player_name=player_name
        )
        filters = dict(
            game_mode=game_mode,
            apple_amount=apple_amount,
            speed=speed,
            size=size,
        )
        board_count = self._count_mastery_universe(data, **filters)
        completed = (entry.get("completed") or []) if entry else []
        all_rows = [
            r for r in (self._normalize_mastery_completion(i) for i in completed) if r
        ]
        rows = self._filter_mastery_completions(completed, **filters)
        rows.sort(key=lambda r: str(r.get("category") or ""))
        metrics = self._summarize_mastery_rows(rows)
        return {
            "player_name": (entry or {}).get("playerName") or player_name or "Unknown",
            "player_id": (entry or {}).get("playerId") or player_id,
            "board_count": board_count,
            "unfiltered_total": len(all_rows),
            "rows": rows,
            "metrics": metrics,
            "entry": entry,
            "filter_label": self._format_category_filters(**filters),
            "found": entry is not None,
        }

    def create_contested_embed(
        self, items: List[Dict], page: int = 0, filter_label: str = ""
    ) -> discord.Embed:
        items_per_page = 8
        total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = items[start:start + items_per_page]
        title = "🔥 Most Contested Categories"
        if filter_label:
            title += f" — {filter_label}"

        embed = discord.Embed(
            title=title,
            color=0xe74c3c,
            timestamp=datetime.now()
        )
        lines = []
        for i, item in enumerate(page_items, start + 1):
            lines.append(
                f"{i}. {self._format_category_line(item.get('category', ''))} — "
                f"**{item.get('flips', 0)}** flips • "
                f"**{item.get('uniqueHolders', 0)}** holders • "
                f"{item.get('daysWithRecord', 0)} days"
            )
        embed.add_field(
            name="Top Flips",
            value="\n".join(lines) if lines else "No contested data.",
            inline=False
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def create_popularity_embed(
        self, items: List[Dict], page: int = 0, filter_label: str = ""
    ) -> discord.Embed:
        items_per_page = 8
        total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = items[start:start + items_per_page]
        title = "⭐ Most Popular Categories"
        if filter_label:
            title += f" — {filter_label}"

        embed = discord.Embed(
            title=title,
            color=0xf1c40f,
            timestamp=datetime.now()
        )
        lines = []
        for i, item in enumerate(page_items, start + 1):
            lines.append(
                f"{i}. {self._format_category_line(item.get('category', ''))} — "
                f"**{item.get('uniqueHolders', 0)}** unique holders • "
                f"**{item.get('flips', 0)}** flips • "
                f"{item.get('daysWithRecord', 0)} days"
            )
        embed.add_field(
            name="Most Unique Holders",
            value="\n".join(lines) if lines else "No popularity data.",
            inline=False
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def create_stale_embed(
        self, items: List[Dict], page: int = 0, filter_label: str = ""
    ) -> discord.Embed:
        items_per_page = 8
        total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = items[start:start + items_per_page]
        title = "🧊 Stalest Categories"
        if filter_label:
            title += f" — {filter_label}"

        embed = discord.Embed(
            title=title,
            color=0x95a5a6,
            timestamp=datetime.now()
        )
        lines = []
        for i, item in enumerate(page_items, start + 1):
            hold_start = item.get('holdStart')
            since = f" • since {hold_start}" if hold_start else ""
            lines.append(
                f"{i}. {self._format_category_line(item.get('category', ''))} — "
                f"**{item.get('holdDays', 0)}** days held • "
                f"**{item.get('flips', 0)}** flips • "
                f"**{item.get('uniqueHolders', 0)}** holders{since}"
            )
        embed.add_field(
            name="Least Activity",
            value="\n".join(lines) if lines else "No stale data.",
            inline=False
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def _format_achievement_hold_line(self, index: int, item: Dict) -> str:
        display_time = self._format_linked_hold_time(item)
        standing = " • still standing" if item.get('stillStanding') else ""
        end_label = "present" if item.get('stillStanding') else item.get('end', '?')
        return (
            f"{index}. **{item.get('playerName', 'Unknown')}** — "
            f"{self._format_category_line(item.get('category', ''))} — "
            f"**{item.get('days', '?')}** days • {display_time} • "
            f"{item.get('start', '?')} → {end_label}{standing}"
        )

    def create_unicorns_embed(self, items: List[Dict], page: int = 0) -> discord.Embed:
        return self.create_legends_embed(items, page=page, show="unicorns")

    def create_legends_embed(
        self, items: List[Dict], page: int = 0, show: str = "legends", filter_label: str = ""
    ) -> discord.Embed:
        items_per_page = 5
        total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = items[start:start + items_per_page]

        if show == "unicorns":
            title = "🦄 Unicorns — Lottery Holds"
            description = "Lottery-tier category holds (still standing first)"
            color = 0xe91e63
        elif show == "all":
            title = "🏆 Legends — Mythic + Lottery"
            description = "Mythic and Lottery holds (hardest first)"
            color = 0x9b59b6
        else:
            title = "🏆 Legends — Mythic Holds"
            description = "Mythic-tier category holds (hardest first)"
            color = 0x9b59b6
        if filter_label:
            title += f" — {filter_label}"

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now()
        )
        lines = []
        for i, item in enumerate(page_items, start + 1):
            line = self._format_achievement_hold_line(i, item)
            legend_type = item.get("legendType")
            if show == "all" and legend_type:
                line += f" • *{legend_type}*"
            lines.append(line)
        embed.add_field(
            name="Holders",
            value="\n".join(lines) if lines else "No legend data.",
            inline=False
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def create_career_embed(
        self, items: List[Dict], tied: str = "all", page: int = 0
    ) -> discord.Embed:
        items_per_page = 10
        total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = items[start:start + items_per_page]
        tied_label = {
            "all": "All holds",
            "untied": "Untied only",
            "tied": "Tied only",
        }.get(tied, "All holds")

        embed = discord.Embed(
            title=f"📚 Career WR-days — {tied_label}",
            description="Players ranked by total days holding a world record",
            color=0x1abc9c,
            timestamp=datetime.now(),
        )
        lines = []
        for i, item in enumerate(page_items, start + 1):
            best = item.get("bestAll") or {}
            best_bits = ""
            if best.get("days") is not None:
                best_bits = (
                    f" • best {best.get('days')}d "
                    f"({self._format_category_line(best.get('category', ''))})"
                )
            lines.append(
                f"{i}. **{item.get('playerName', 'Unknown')}** — "
                f"**{item.get('wrDays', 0)}** WR-days{best_bits}"
            )
        embed.add_field(
            name="Top Careers",
            value="\n".join(lines) if lines else "No career data.",
            inline=False,
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def create_player_holds_embed(
        self,
        player_name: str,
        items: List[Dict],
        holds: str = "all",
        page: int = 0,
        filter_label: str = "",
    ) -> discord.Embed:
        items_per_page = 5
        total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = items[start:start + items_per_page]
        mode_label = {
            "all": "All holds",
            "present": "Present holds",
            "old": "Old holds",
            "latest": "Latest activity",
        }.get(holds, "All holds")
        title = f"👤 {player_name} — {mode_label}"
        if filter_label:
            title += f" — {filter_label}"
        sort_hint = {
            "old": "most recently taken first",
            "latest": "newest acquired first",
        }.get(holds, "longest first")

        embed = discord.Embed(
            title=title,
            description=f"{len(items)} hold{'s' if len(items) != 1 else ''} · {sort_hint}",
            color=0x0099ff,
            timestamp=datetime.now(),
        )
        lines = []
        for i, item in enumerate(page_items, start + 1):
            standing = " • still standing" if item.get("stillStanding") else ""
            end_label = "present" if item.get("stillStanding") else item.get("end", "?")
            lines.append(
                f"{i}. **{item.get('days', '?')} days** — "
                f"{self._format_category_line(item.get('category', ''))} — "
                f"{self._format_linked_hold_time(item)} • "
                f"{item.get('start', '?')} → {end_label}{standing}"
            )
        embed.add_field(
            name="Holds",
            value="\n".join(lines) if lines else "No holds match these filters.",
            inline=False,
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def _format_mastery_breakdown(self, metrics: Dict, board_count: int) -> str:
        bs = metrics.get("bySpeed") or {}
        bz = metrics.get("bySize") or {}
        total = metrics.get("total", 0)
        return (
            f"**{total} / {board_count}** boards\n"
            f"N **{bs.get('Normal', 0)}** · F **{bs.get('Fast', 0)}** · S **{bs.get('Slow', 0)}**\n"
            f"Std **{bz.get('Standard', 0)}** · Sm **{bz.get('Small', 0)}** · Lg **{bz.get('Large', 0)}**"
        )

    def create_mastery_leaderboard_embed(self, data: Dict, page: int = 0) -> discord.Embed:
        rows = data.get("rows") or []
        community = data.get("community") or {}
        board_count = data.get("board_count") or 0
        filter_label = data.get("filter_label") or ""
        items_per_page = 10
        total_pages = max(1, (len(rows) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = rows[start:start + items_per_page]
        title = "🏅 Mastery Challenge — All Apples"
        if filter_label:
            title += f" — {filter_label}"

        embed = discord.Embed(
            title=title,
            description=(
                f"Verified All Apples completions · **{data.get('player_count', len(rows))}** players · "
                f"max **{board_count}** for filters · "
                f"Inhuman **{data.get('inhuman_have', 0)} / {data.get('inhuman_max', 0)}**"
            ),
            color=0xf39c12,
            timestamp=datetime.now(),
        )
        if page == 0 and community:
            embed.add_field(
                name="0. Community Mastery",
                value=self._format_mastery_breakdown(
                    {
                        "total": community.get("total", 0),
                        "bySpeed": community.get("bySpeed") or {},
                        "bySize": community.get("bySize") or {},
                    },
                    board_count,
                ),
                inline=False,
            )
        lines = []
        for i, item in enumerate(page_items, start + 1):
            lines.append(
                f"{i}. **{item.get('playerName', 'Unknown')}** — "
                f"**{item.get('total', 0)} / {board_count}** · "
                f"N{item.get('bySpeed', {}).get('Normal', 0)} "
                f"F{item.get('bySpeed', {}).get('Fast', 0)} "
                f"S{item.get('bySpeed', {}).get('Slow', 0)} · "
                f"Std{item.get('bySize', {}).get('Standard', 0)} "
                f"Sm{item.get('bySize', {}).get('Small', 0)} "
                f"Lg{item.get('bySize', {}).get('Large', 0)}"
            )
        embed.add_field(
            name="Leaderboard",
            value="\n".join(lines) if lines else "No mastery completions match these filters.",
            inline=False,
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def create_player_mastery_embed(self, data: Dict, page: int = 0) -> discord.Embed:
        rows = data.get("rows") or []
        metrics = data.get("metrics") or {}
        board_count = data.get("board_count") or 0
        filter_label = data.get("filter_label") or ""
        items_per_page = 8
        total_pages = max(1, (len(rows) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = rows[start:start + items_per_page]
        title = f"🏅 {data.get('player_name', 'Player')} — Mastery"
        if filter_label:
            title += f" — {filter_label}"

        embed = discord.Embed(
            title=title,
            description=self._format_mastery_breakdown(metrics, board_count),
            color=0xf39c12,
            timestamp=datetime.now(),
        )
        unfiltered = data.get("unfiltered_total")
        if unfiltered is not None and unfiltered != len(rows):
            embed.description = (
                (embed.description or "")
                + f"\n*{len(rows)} shown · {unfiltered} unfiltered · All Apples*"
            )
        else:
            embed.description = (embed.description or "") + "\n*All Apples completions*"

        lines = []
        for i, item in enumerate(page_items, start + 1):
            time_str = self._format_linked_hold_time(item)
            tier = item.get("tier")
            tier_bit = f" · {tier}" if tier else ""
            lines.append(
                f"{i}. {self._format_category_line(item.get('category', ''))} — "
                f"{time_str}{tier_bit}"
            )
        embed.add_field(
            name="Completed boards",
            value="\n".join(lines) if lines else "No mastery boards match these filters.",
            inline=False,
        )
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{total_pages}")
        return embed

    def create_unheld_embed(self, unheld_data: Dict, page: int = 0) -> discord.Embed:
        items = unheld_data.get('rows') or []
        items_per_page = 8
        total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_items = items[start:start + items_per_page]
        tier = unheld_data.get('tier')
        filter_label = unheld_data.get('filter_label') or ""
        title_bits = []
        if tier:
            title_bits.append(str(tier))
        if filter_label:
            title_bits.append(filter_label)
        title = (
            f"🕳️ Unheld Categories — {' • '.join(title_bits)}"
            if title_bits else "🕳️ Unheld Categories"
        )

        embed = discord.Embed(
            title=title,
            description="Never-held categories, easiest first",
            color=0x34495e,
            timestamp=datetime.now()
        )
        lines = []
        for i, item in enumerate(page_items, start + 1):
            score = item.get('score')
            score_text = f" (score {score})" if score is not None else ""
            lines.append(
                f"{i}. {self._format_category_line(item.get('category', ''))} — "
                f"**{item.get('tier', '?')}**{score_text}"
            )
        embed.add_field(
            name="Open Categories",
            value="\n".join(lines) if lines else "No unheld categories for this filter.",
            inline=False
        )
        shown = unheld_data.get('shown', len(items))
        total = unheld_data.get('total', shown)
        embed.set_footer(
            text=(
                f"Data from FastSnakeStats • {shown} shown · {total} unheld total "
                f"• Page {page + 1}/{total_pages}"
            )
        )
        return embed

    def create_activity_embed(self, year: str, summary: Dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"📅 Activity — {year}",
            color=0x1abc9c,
            timestamp=datetime.now()
        )
        embed.add_field(
            name="Year Totals",
            value=(
                f"**New WRs:** {summary['total_new_wrs']}\n"
                f"**Active days:** {summary['active_days']}"
            ),
            inline=False
        )
        top_days = summary.get('top_days') or []
        if top_days:
            lines = []
            for i, day in enumerate(top_days, 1):
                lines.append(
                    f"{i}. **{day['date']}** — {day['newWrs']} new WRs"
                )
            embed.add_field(
                name="Busiest Days",
                value="\n".join(lines),
                inline=False
            )
        embed.set_footer(
            text="Data from FastSnakeStats • New WR = #1 changed that day"
        )
        return embed

    def create_leaderboards_embed(self, board_data: Dict, page: int = 0) -> discord.Embed:
        items_per_page = 8
        rows = board_data.get('rows') or []
        total_pages = max(1, (len(rows) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_rows = rows[start:start + items_per_page]

        embed = discord.Embed(
            title=(
                f"🏆 Leaderboards — {board_data['apple_amount']} • "
                f"{board_data['speed']} • {board_data['size']}"
            ),
            color=0x00ff00,
            timestamp=datetime.now()
        )
        lines = []
        for row in page_rows:
            line = f"**{row['gamemode']} • {row['run_mode']}** — {row['player']} — {row['time']}"
            if row.get('link'):
                line += f" • [View]({row['link']})"
            lines.append(line)
        embed.add_field(
            name=f"World Records ({len(rows)} categories)",
            value="\n".join(lines) if lines else "No records found for this combination.",
            inline=False
        )
        embed.set_footer(
            text=f"Data from FastSnakeStats • {board_data['date']} • Page {page + 1}/{total_pages}"
        )
        return embed

    @app_commands.command(name="record", description="Get world record for specific settings")
    @app_commands.describe(
        game_mode="Game mode (Classic, Wall, Portal, Bridge, etc.)",
        apple_amount="Number of apples",
        speed="Game speed",
        size="Game size",
        run_mode="Run mode (25 Apples, 50 Apples, etc.)",
        date="Historical date - optional"
    )
    @app_commands.autocomplete(
        date=record_date_autocomplete,
        game_mode=record_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=record_run_mode_autocomplete,
    )
    async def record_command(self, interaction: discord.Interaction, game_mode: str, apple_amount: str, speed: str, size: str, run_mode: str, date: Optional[str] = None):
        """Get world record for specific settings"""
        await interaction.response.defer()
        
        try:
            if not dm.validate_settings(apple_amount, speed, size, game_mode):
                await interaction.followup.send(
                    f"❌ Invalid settings combination. Check `/record` options and try again."
                )
                return

            # Get record data
            record_data = await self.get_record_data(apple_amount, speed, size, game_mode, date, run_mode)
            
            if not record_data:
                settings_key = dm.get_settings_key(apple_amount, speed, size, game_mode, run_mode)
                if date:
                    await interaction.followup.send(
                        f"❌ No record found for `{settings_key}` on {date}. "
                        "Use `/available-dates` to see working dates."
                    )
                else:
                    await interaction.followup.send(
                        f"❌ No record found for `{settings_key}`. "
                        "This category may not have runs in the cache yet."
                    )
                return
            
            # Create embed
            embed = self.create_record_embed(record_data, record_data['settings'])
            
            # Add run link if available
            run_link = dm.get_run_link(record_data['run'])
            if run_link:
                embed.add_field(
                    name="🔗 Speedrun.com Link",
                    value=f"[View Run]({run_link})",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in record command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching the record. Please try again.")
    
    @app_commands.command(name="available-dates", description="List available historical dates")
    async def available_dates_command(self, interaction: discord.Interaction):
        """List available historical dates"""
        await interaction.response.defer()
        
        try:
            dates = await github_cache_fetcher.get_available_dates()
            
            if not dates:
                await interaction.followup.send("❌ No historical data available.")
                return
            
            # Get cache stats
            stats = await github_cache_fetcher.get_cache_stats()
            
            embed = discord.Embed(
                title="📅 Available Historical Dates",
                color=0x0099ff,
                timestamp=datetime.now()
            )
            
            # Show date range
            if stats and stats.get('dateRange'):
                date_range = stats['dateRange']
                start = date_range.get('start') or date_range.get('earliest') or 'N/A'
                end = date_range.get('end') or date_range.get('latest') or 'N/A'
                embed.add_field(
                    name="Date Range",
                    value=f"{start} to {end}",
                    inline=False
                )
            
            # Show total dates
            embed.add_field(
                name="Total Dates",
                value=str(len(dates)),
                inline=True
            )
            
            # Show last updated
            if stats and stats.get('lastUpdated'):
                embed.add_field(
                    name="Last Updated",
                    value=stats['lastUpdated'][:10],  # Just the date part
                    inline=True
                )
            
            # Show recent dates (last 10)
            recent_dates = dates[-10:] if len(dates) > 10 else dates
            embed.add_field(
                name="Recent Dates",
                value="\n".join(recent_dates),
                inline=False
            )
            
            embed.set_footer(text="Use /record with a date parameter to view historical records")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in available-dates command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching available dates.")
    
    @app_commands.command(
        name="player",
        description="Player profile, or explorer hold history with holds=…",
    )
    @app_commands.describe(
        player_name="Player name to look up",
        date="Historical date - optional (profile snapshot)",
        holds="Explorer hold list mode (omitted = profile); Mastery = All Apples challenge",
        tied="Tied filter for present holds only",
        game_mode="Optional game mode filter (holds/Mastery; includes HS-only / Excluding Peaceful)",
        apple_amount="Optional apple count filter (holds/Mastery list)",
        speed="Optional speed filter (holds/Mastery list)",
        size="Optional size filter (holds/Mastery list)",
        run_mode="Optional run mode filter; Timed = non-HS (WR holds list)",
    )
    @app_commands.choices(
        holds=[
            app_commands.Choice(name="All holds", value="all"),
            app_commands.Choice(name="Present", value="present"),
            app_commands.Choice(name="Old", value="old"),
            app_commands.Choice(name="Latest activity", value="latest"),
            app_commands.Choice(name="Mastery", value="mastery"),
        ],
        tied=[
            app_commands.Choice(name="All holds", value="all"),
            app_commands.Choice(name="Untied only", value="untied"),
            app_commands.Choice(name="Tied only", value="tied"),
        ],
    )
    @app_commands.autocomplete(
        date=player_date_autocomplete,
        player_name=player_name_autocomplete,
        game_mode=mastery_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=list_run_mode_autocomplete,
    )
    async def player_command(
        self,
        interaction: discord.Interaction,
        player_name: str,
        date: Optional[str] = None,
        holds: Optional[app_commands.Choice[str]] = None,
        tied: Optional[app_commands.Choice[str]] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ):
        """Get player statistics and recent activity"""
        await interaction.response.defer()
        
        try:
            hold_mode = holds.value if holds else None
            if hold_mode == "mastery":
                peak_stats = await github_cache_fetcher.get_player_peak_stats(player_name)
                display_name = (peak_stats or {}).get("name") or player_name
                player_id = (peak_stats or {}).get("id")
                filters = dict(
                    game_mode=game_mode,
                    apple_amount=apple_amount,
                    speed=speed,
                    size=size,
                )
                data = await self._get_player_mastery_items(
                    player_id=player_id,
                    player_name=display_name,
                    **filters,
                )
                if data is None:
                    await interaction.followup.send("❌ Mastery data unavailable.")
                    return
                if not data.get("found") and not data.get("rows"):
                    await interaction.followup.send(
                        f"❌ No Mastery completions found for **{display_name}**."
                    )
                    return
                if not data.get("rows"):
                    suffix = f" for `{data.get('filter_label')}`" if data.get("filter_label") else ""
                    await interaction.followup.send(
                        f"❌ No Mastery boards match{suffix} for **{display_name}**."
                    )
                    return
                embed = self.create_player_mastery_embed(data, page=0)
                total_pages = max(1, (len(data["rows"]) + 7) // 8)
                if total_pages > 1:
                    view = ListPaginationView(
                        interaction.user.id,
                        total_pages,
                        lambda page: self.create_player_mastery_embed(data, page),
                    )
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed)
                return

            if hold_mode:
                peak_stats = await github_cache_fetcher.get_player_peak_stats(player_name)
                display_name = (peak_stats or {}).get("name") or player_name
                player_id = (peak_stats or {}).get("id")
                tied_mode = tied.value if tied else "all"
                if hold_mode != "present":
                    tied_mode = "all"
                filters = dict(
                    game_mode=game_mode,
                    apple_amount=apple_amount,
                    speed=speed,
                    size=size,
                    run_mode=run_mode,
                )
                filter_label = self._format_category_filters(
                    **filters, tied=tied_mode if hold_mode == "present" else None
                )
                items = await self._get_player_hold_items(
                    player_id=player_id,
                    player_name=display_name,
                    holds=hold_mode,
                    tied=tied_mode,
                    **filters,
                )
                if items is None:
                    await interaction.followup.send("❌ Player hold data unavailable.")
                    return
                if not items:
                    suffix = f" for `{filter_label}`" if filter_label else ""
                    await interaction.followup.send(
                        f"❌ No holds found for **{display_name}**{suffix}."
                    )
                    return
                embed = self.create_player_holds_embed(
                    display_name, items, hold_mode, page=0, filter_label=filter_label
                )
                total_pages = max(1, (len(items) + 4) // 5)
                if total_pages > 1:
                    view = ListPaginationView(
                        interaction.user.id,
                        total_pages,
                        lambda page: self.create_player_holds_embed(
                            display_name, items, hold_mode, page, filter_label
                        ),
                    )
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed)
                return

            player_data = await self.get_player_data(player_name, date)
            
            if not player_data:
                if date:
                    await interaction.followup.send(f"❌ No data available for date: {date}. Use `/available-dates` to see working dates.")
                else:
                    await interaction.followup.send(f"❌ No data found for player: {player_name}")
                return
            
            embed = self.create_player_embed(player_data, page=0)
            
            activity_len = len(player_data.get('recent_activity') or [])
            total_pages = max(1, (activity_len + 4) // 5)
            if total_pages > 1:
                view = PlayerPaginationView(
                    player_data,
                    interaction.user.id,
                    embed_factory=self.create_player_embed,
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in player command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching player data. Please try again.")
    
    @app_commands.command(name="stats", description="Get top record holders statistics")
    @app_commands.describe(
        date="Historical date - optional"
    )
    @app_commands.autocomplete(date=stats_date_autocomplete)
    async def stats_command(self, interaction: discord.Interaction, date: Optional[str] = None):
        """Get top record holders statistics"""
        await interaction.response.defer()
        
        try:
            # Get stats data
            stats_data = await self.get_stats_data(date)
            
            if not stats_data:
                await interaction.followup.send("❌ No statistics data available.")
                return
            
            # Create embed with pagination
            embed = self.create_stats_embed(stats_data, page=0)
            
            # Create view with pagination buttons (only if multiple pages)
            total_pages = (len(stats_data['top_by_percentage']) + 9) // 10  # 10 players per page
            if total_pages > 1:
                view = StatsPaginationView(stats_data, interaction.user.id)
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in stats command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching statistics. Please try again.")
    
    @app_commands.command(
        name="random",
        description="Random valid challenge settings (optional filters / difficulty tier)",
    )
    @app_commands.describe(
        tier="Optional difficulty tier",
        game_mode="Optional game mode filter",
        apple_amount="Optional apple count filter",
        speed="Optional speed filter",
        size="Optional size filter",
        run_mode="Optional run mode filter",
    )
    @app_commands.choices(tier=[
        app_commands.Choice(name="Free", value="Free"),
        app_commands.Choice(name="Warmup", value="Warmup"),
        app_commands.Choice(name="Easy", value="Easy"),
        app_commands.Choice(name="Medium", value="Medium"),
        app_commands.Choice(name="Hard", value="Hard"),
        app_commands.Choice(name="Mythic", value="Mythic"),
        app_commands.Choice(name="Lottery", value="Lottery"),
        app_commands.Choice(name="Inhuman", value="Inhuman"),
    ])
    @app_commands.autocomplete(
        game_mode=record_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=random_size_autocomplete,
        run_mode=random_run_mode_autocomplete,
    )
    async def random_command(
        self,
        interaction: discord.Interaction,
        tier: Optional[app_commands.Choice[str]] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ):
        """Get a random valid combination of game settings"""
        await interaction.response.defer()
        try:
            if run_mode == "High Score" and game_mode:
                if apple_amount and not dm.allows_high_score(apple_amount, game_mode):
                    await interaction.followup.send(
                        f"❌ High Score does not exist for `{apple_amount}` + `{game_mode}`."
                    )
                    return
                if not apple_amount and not (
                    dm.is_high_score_mode(game_mode)
                    or dm.is_tally_ce_highscore_mode(game_mode)
                ):
                    await interaction.followup.send(
                        f"❌ `{game_mode}` is not a high-score mode, so High Score runs don't exist for it."
                    )
                    return
            if run_mode == "100 Apples" and size == "Small":
                await interaction.followup.send(
                    "❌ `100 Apples` on `Small` is not a valid category."
                )
                return

            tier_value = tier.value if tier else None
            combination = self.get_random_combination(
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
                tier=tier_value,
            )
            if not combination:
                bits = [
                    v for v in (
                        tier_value, game_mode, apple_amount, speed, size, run_mode
                    ) if v
                ]
                label = " • ".join(bits) if bits else "those filters"
                await interaction.followup.send(
                    f"❌ No valid categories found for {label}."
                )
                return

            settings_key = combination["settings_key"]
            record_data = await self.get_record_data(
                combination["apple_amount"],
                combination["speed"],
                combination["size"],
                combination["game_mode"],
                run_mode=combination["run_mode"],
            )

            embed = discord.Embed(
                title="🎲 Random Challenge",
                description=dm.format_category_key(settings_key),
                color=0x9b59b6,
                timestamp=datetime.now(),
            )
            embed.add_field(name="🎮 Game Mode", value=combination["game_mode"], inline=True)
            embed.add_field(name="🍎 Apple Amount", value=combination["apple_amount"], inline=True)
            embed.add_field(name="⚡ Speed", value=combination["speed"], inline=True)
            embed.add_field(name="📏 Size", value=combination["size"], inline=True)
            embed.add_field(name="🎯 Run Mode", value=combination["run_mode"], inline=True)
            embed.add_field(name="📶 Difficulty", value=combination["tier"], inline=True)

            if record_data and record_data.get("run"):
                run = record_data["run"]
                time_str = self._format_time_for_display(
                    dm.get_run_time(run), combination["run_mode"]
                )
                player = dm.get_player_name(run)
                date = dm.get_run_date(run)
                link = dm.get_run_link(run)
                record_line = f"**{player}** — {time_str}"
                if date and date != "N/A":
                    record_line += f" • `{date}`"
                if link:
                    record_line += f" • [View Run]({link})"
                embed.add_field(name="🏆 Current WR", value=record_line, inline=False)
            else:
                embed.add_field(
                    name="🏆 Current WR",
                    value="Unheld — no world record yet.",
                    inline=False,
                )

            embed.set_footer(text="Data from FastSnakeStats • Valid categories only")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in random command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating a random combination."
            )
    
    @app_commands.command(name="report", description="View weekly report of record changes and new achievements")
    async def report_command(self, interaction: discord.Interaction):
        """View weekly report of record changes and new achievements"""
        await interaction.response.defer()
        
        try:
            # Get weekly report data
            report_data = await self.get_weekly_report_data()
            
            if not report_data:
                await interaction.followup.send("❌ Unable to fetch weekly report data. Please try again later.")
                return
            
            # Create embed with pagination
            embed = self.create_weekly_report_embed(report_data, page=0)
            
            # Create view with pagination buttons (only if multiple pages)
            all_items = (len(report_data['new_records']) + 
                        len(report_data['record_changes']) + 
                        len(report_data['improved_records']))
            items_per_page = 3
            total_pages = (all_items + items_per_page - 1) // items_per_page
            
            if total_pages > 1:
                view = ReportPaginationView(report_data, interaction.user.id)
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in report command: {e}")
            await interaction.followup.send("❌ An error occurred while generating the weekly report. Please try again.")

    @app_commands.command(
        name="monthly",
        description="Monthly oldest-records update (beaten longstanding WRs + current oldest)",
    )
    @app_commands.describe(
        month="Optional year-month (YYYY-MM). Autocomplete lists months with complete FastSnakeStats data.",
    )
    @app_commands.autocomplete(month=monthly_month_autocomplete)
    async def monthly_command(
        self,
        interaction: discord.Interaction,
        month: Optional[str] = None,
    ):
        """Test / preview the monthly oldest-records report."""
        await interaction.response.defer()
        try:
            if month:
                month = month.strip()
                if not await github_cache_fetcher.is_year_month_complete(month):
                    await interaction.followup.send(
                        f"❌ `{month}` does not have complete FastSnakeStats data yet. "
                        "Pick a month from the autocomplete list (computed live from the cache)."
                    )
                    return

            report_data = await self.get_monthly_oldest_report_data(year_month=month)
            if not report_data:
                await interaction.followup.send(
                    "❌ Unable to fetch monthly oldest-records data. Please try again later."
                )
                return

            embeds = self.build_monthly_report_embeds(report_data)
            await interaction.followup.send(embeds=embeds)
        except Exception as e:
            print(f"Error in monthly command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating the monthly report."
            )

    @app_commands.command(name="progression", description="WR change timeline for a category")
    @app_commands.describe(
        game_mode="Game mode",
        apple_amount="Number of apples",
        speed="Game speed",
        size="Game size",
        run_mode="Run mode",
    )
    @app_commands.autocomplete(
        game_mode=record_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=record_run_mode_autocomplete,
    )
    async def progression_command(
        self,
        interaction: discord.Interaction,
        game_mode: str,
        apple_amount: str,
        speed: str,
        size: str,
        run_mode: str,
    ):
        await interaction.response.defer()
        try:
            if not dm.validate_settings(apple_amount, speed, size, game_mode):
                await interaction.followup.send("❌ Invalid settings combination.")
                return
            if run_mode not in dm.RUN_MODES:
                await interaction.followup.send("❌ Invalid run mode.")
                return

            settings_key = dm.get_settings_key(apple_amount, speed, size, game_mode, run_mode)
            flips = await github_cache_fetcher.get_progression(settings_key)
            if not flips:
                await interaction.followup.send(f"❌ No progression data for `{settings_key}`.")
                return

            embed = self.create_progression_embed(settings_key, flips, page=0)
            total_pages = max(1, (len(flips) + 7) // 8)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_progression_embed(settings_key, flips, page),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in progression command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching progression data.")

    @app_commands.command(name="longevity", description="Longest-held world records")
    @app_commands.describe(
        filter="all = all-time holds, standing = still unbroken",
        tied="All / untied-only / tied-only holds",
        game_mode="Optional mode or High score modes only",
        apple_amount="Optional apple count filter",
        speed="Optional speed filter",
        size="Optional size filter",
        run_mode="Optional run mode filter; Timed = all non-High Score",
    )
    @app_commands.choices(
        filter=[
            app_commands.Choice(name="Still standing", value="standing"),
            app_commands.Choice(name="All-time", value="all"),
        ],
        tied=[
            app_commands.Choice(name="All holds", value="all"),
            app_commands.Choice(name="Untied only", value="untied"),
            app_commands.Choice(name="Tied only", value="tied"),
        ],
    )
    @app_commands.autocomplete(
        game_mode=list_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=list_run_mode_autocomplete,
    )
    async def longevity_command(
        self,
        interaction: discord.Interaction,
        filter: Optional[app_commands.Choice[str]] = None,
        tied: Optional[app_commands.Choice[str]] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            filter_mode = filter.value if filter else "standing"
            tied_mode = tied.value if tied else "all"
            filters = dict(
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            )
            filter_label = self._format_category_filters(**filters, tied=tied_mode)
            items = await self._get_longevity_items(
                mode=filter_mode, tied=tied_mode, **filters
            )
            if items is None:
                await interaction.followup.send("❌ Longevity data unavailable.")
                return
            if not items:
                suffix = f" for `{filter_label}`" if filter_label else ""
                await interaction.followup.send(f"❌ No longevity entries found{suffix}.")
                return

            embed = self.create_longevity_embed(
                items, filter_mode, page=0, filter_label=filter_label
            )
            total_pages = max(1, (len(items) + 4) // 5)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_longevity_embed(
                        items, filter_mode, page, filter_label
                    ),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in longevity command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching longevity data.")

    @app_commands.command(name="improving", description="Players gaining the most world records")
    @app_commands.describe(window="Time window for WR gains")
    @app_commands.choices(window=[
        app_commands.Choice(name="7 days", value="7d"),
        app_commands.Choice(name="30 days", value="30d"),
        app_commands.Choice(name="90 days", value="90d"),
        app_commands.Choice(name="365 days", value="365d"),
    ])
    async def improving_command(
        self,
        interaction: discord.Interaction,
        window: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer()
        try:
            window_key = window.value if window else "30d"
            items = await github_cache_fetcher.get_improving(window_key)
            if items is None:
                await interaction.followup.send("❌ Improving-player data unavailable.")
                return
            if not items:
                await interaction.followup.send(f"❌ No improving players for window `{window_key}`.")
                return

            embed = self.create_improving_embed(items, window_key, page=0)
            total_pages = max(1, (len(items) + 9) // 10)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_improving_embed(items, window_key, page),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in improving command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching improving players.")

    @app_commands.command(name="contested", description="Categories with the most WR flips")
    @app_commands.describe(
        game_mode="Optional mode or High score modes only",
        apple_amount="Optional apple count filter",
        speed="Optional speed filter",
        size="Optional size filter",
        run_mode="Optional run mode filter; Timed = all non-High Score",
    )
    @app_commands.autocomplete(
        game_mode=list_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=list_run_mode_autocomplete,
    )
    async def contested_command(
        self,
        interaction: discord.Interaction,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            filters = dict(
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            )
            filter_label = self._format_category_filters(**filters)
            items = await self._get_contested_items(**filters)
            if items is None:
                await interaction.followup.send("❌ Contested categories data unavailable.")
                return
            if not items:
                suffix = f" for `{filter_label}`" if filter_label else ""
                await interaction.followup.send(f"❌ No contested category data found{suffix}.")
                return

            embed = self.create_contested_embed(items, page=0, filter_label=filter_label)
            total_pages = max(1, (len(items) + 7) // 8)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_contested_embed(items, page, filter_label),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in contested command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching contested categories.")

    @app_commands.command(name="popularity", description="Categories with the most unique WR holders")
    @app_commands.describe(
        tied="Both / untied / tied present WRs",
        game_mode="Optional mode or High score modes only",
        apple_amount="Optional apple count filter",
        speed="Optional speed filter",
        size="Optional size filter",
        run_mode="Optional run mode filter; Timed = all non-High Score",
    )
    @app_commands.choices(tied=[
        app_commands.Choice(name="Both", value="all"),
        app_commands.Choice(name="Untied", value="untied"),
        app_commands.Choice(name="Tied", value="tied"),
    ])
    @app_commands.autocomplete(
        game_mode=list_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=list_run_mode_autocomplete,
    )
    async def popularity_command(
        self,
        interaction: discord.Interaction,
        tied: Optional[app_commands.Choice[str]] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            tied_mode = tied.value if tied else "all"
            filters = dict(
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            )
            filter_label = self._format_category_filters(**filters, tied=tied_mode)
            items = await self._get_popularity_items(tied=tied_mode, **filters)
            if items is None:
                await interaction.followup.send("❌ Popularity data unavailable.")
                return
            if not items:
                suffix = f" for `{filter_label}`" if filter_label else ""
                await interaction.followup.send(f"❌ No popularity data found{suffix}.")
                return

            embed = self.create_popularity_embed(items, page=0, filter_label=filter_label)
            total_pages = max(1, (len(items) + 7) // 8)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_popularity_embed(items, page, filter_label),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in popularity command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching popularity data.")

    @app_commands.command(
        name="stale",
        description="Least-flipped / longest-unchanged held categories",
    )
    @app_commands.describe(
        game_mode="Optional mode or High score modes only",
        apple_amount="Optional apple count filter",
        speed="Optional speed filter",
        size="Optional size filter",
        run_mode="Optional run mode filter; Timed = all non-High Score",
    )
    @app_commands.autocomplete(
        game_mode=list_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=list_run_mode_autocomplete,
    )
    async def stale_command(
        self,
        interaction: discord.Interaction,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            filters = dict(
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            )
            filter_label = self._format_category_filters(**filters)
            items = await self._get_stale_items(**filters)
            if items is None:
                await interaction.followup.send("❌ Stale categories data unavailable.")
                return
            if not items:
                suffix = f" for `{filter_label}`" if filter_label else ""
                await interaction.followup.send(f"❌ No stale category data found{suffix}.")
                return

            embed = self.create_stale_embed(items, page=0, filter_label=filter_label)
            total_pages = max(1, (len(items) + 7) // 8)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_stale_embed(items, page, filter_label),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in stale command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching stale categories.")

    @app_commands.command(
        name="career",
        description="Career WR-days leaderboard (all / untied / tied holds)",
    )
    @app_commands.describe(tied="All holds, untied-only, or tied-only WR-days")
    @app_commands.choices(tied=[
        app_commands.Choice(name="All holds", value="all"),
        app_commands.Choice(name="Untied only", value="untied"),
        app_commands.Choice(name="Tied only", value="tied"),
    ])
    async def career_command(
        self,
        interaction: discord.Interaction,
        tied: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer()
        try:
            tied_mode = tied.value if tied else "all"
            rows = await github_cache_fetcher.get_career()
            if rows is None:
                await interaction.followup.send("❌ Career data unavailable.")
                return
            items = []
            for row in rows:
                metrics = self._career_metrics(row, tied_mode)
                if metrics["wrDays"] <= 0 and not metrics["bestAll"] and not metrics["bestStanding"]:
                    continue
                items.append({
                    "playerId": row.get("playerId"),
                    "playerName": row.get("playerName"),
                    "wrDays": metrics["wrDays"],
                    "bestAll": metrics["bestAll"],
                    "bestStanding": metrics["bestStanding"],
                })
            items.sort(
                key=lambda r: (
                    -(r.get("wrDays") or 0),
                    str(r.get("playerName") or ""),
                )
            )
            items = items[:50]
            if not items:
                await interaction.followup.send("❌ No career entries for that tied filter.")
                return

            embed = self.create_career_embed(items, tied=tied_mode, page=0)
            total_pages = max(1, (len(items) + 9) // 10)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_career_embed(items, tied_mode, page),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in career command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching career data.")

    @app_commands.command(
        name="mastery",
        description="Mastery Challenge: All Apples completions leaderboard or player boards",
    )
    @app_commands.describe(
        player_name="Optional player — show their completed Mastery boards",
        game_mode="Mode or group (High score modes only / Excluding Peaceful)",
        apple_amount="Optional apple count filter",
        speed="Optional speed filter",
        size="Optional size filter",
    )
    @app_commands.autocomplete(
        player_name=player_name_autocomplete,
        game_mode=mastery_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
    )
    async def mastery_command(
        self,
        interaction: discord.Interaction,
        player_name: Optional[str] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            filters = dict(
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
            )
            if player_name:
                peak_stats = await github_cache_fetcher.get_player_peak_stats(player_name)
                display_name = (peak_stats or {}).get("name") or player_name
                player_id = (peak_stats or {}).get("id")
                data = await self._get_player_mastery_items(
                    player_id=player_id,
                    player_name=display_name,
                    **filters,
                )
                if data is None:
                    await interaction.followup.send("❌ Mastery data unavailable.")
                    return
                if not data.get("found") and not data.get("rows"):
                    await interaction.followup.send(
                        f"❌ No Mastery completions found for **{display_name}**."
                    )
                    return
                if not data.get("rows"):
                    suffix = f" for `{data.get('filter_label')}`" if data.get("filter_label") else ""
                    await interaction.followup.send(
                        f"❌ No Mastery boards match{suffix} for **{display_name}**."
                    )
                    return
                embed = self.create_player_mastery_embed(data, page=0)
                total_pages = max(1, (len(data["rows"]) + 7) // 8)
                if total_pages > 1:
                    view = ListPaginationView(
                        interaction.user.id,
                        total_pages,
                        lambda page: self.create_player_mastery_embed(data, page),
                    )
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed)
                return

            data = await self._get_mastery_leaderboard(**filters)
            if data is None:
                await interaction.followup.send("❌ Mastery data unavailable.")
                return
            if not data.get("rows") and not (data.get("community") or {}).get("total"):
                suffix = f" for `{data.get('filter_label')}`" if data.get("filter_label") else ""
                await interaction.followup.send(
                    f"❌ No Mastery completions found{suffix}."
                )
                return

            embed = self.create_mastery_leaderboard_embed(data, page=0)
            total_pages = max(1, (len(data.get("rows") or []) + 9) // 10)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_mastery_leaderboard_embed(data, page),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in mastery command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching Mastery data.")

    @app_commands.command(
        name="unicorns",
        description="Lottery-tier unicorn category holds (alias of /legends show:unicorns)",
    )
    @app_commands.describe(
        game_mode="Optional mode or High score modes only",
        apple_amount="Optional apple count filter",
        speed="Optional speed filter",
        size="Optional size filter",
        run_mode="Optional run mode filter; Timed = all non-High Score",
    )
    @app_commands.autocomplete(
        game_mode=list_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=list_run_mode_autocomplete,
    )
    async def unicorns_command(
        self,
        interaction: discord.Interaction,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            filters = dict(
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            )
            filter_label = self._format_category_filters(**filters)
            items = await self._get_legends_items(show="unicorns", **filters)
            if items is None:
                await interaction.followup.send("❌ Unicorns data unavailable.")
                return
            if not items:
                suffix = f" for `{filter_label}`" if filter_label else ""
                await interaction.followup.send(f"❌ No unicorn holds found{suffix}.")
                return

            embed = self.create_legends_embed(
                items, page=0, show="unicorns", filter_label=filter_label
            )
            total_pages = max(1, (len(items) + 4) // 5)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_legends_embed(
                        items, page, "unicorns", filter_label
                    ),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in unicorns command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching unicorns.")

    @app_commands.command(
        name="legends",
        description="Mythic/Lottery holds (Show: All / Legends / Unicorns)",
    )
    @app_commands.describe(
        show="All (merged), Legends only, or Unicorns only",
        game_mode="Optional mode or High score modes only",
        apple_amount="Optional apple count filter",
        speed="Optional speed filter",
        size="Optional size filter",
        run_mode="Optional run mode filter; Timed = all non-High Score",
    )
    @app_commands.choices(show=[
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Legends", value="legends"),
        app_commands.Choice(name="Unicorns", value="unicorns"),
    ])
    @app_commands.autocomplete(
        game_mode=list_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=list_run_mode_autocomplete,
    )
    async def legends_command(
        self,
        interaction: discord.Interaction,
        show: Optional[app_commands.Choice[str]] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            show_mode = show.value if show else "all"
            filters = dict(
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            )
            filter_label = self._format_category_filters(**filters)
            items = await self._get_legends_items(show=show_mode, **filters)
            if items is None:
                await interaction.followup.send("❌ Legends data unavailable.")
                return
            if not items:
                suffix = f" for `{filter_label}`" if filter_label else ""
                await interaction.followup.send(f"❌ No legend holds found{suffix}.")
                return

            embed = self.create_legends_embed(
                items, page=0, show=show_mode, filter_label=filter_label
            )
            total_pages = max(1, (len(items) + 4) // 5)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_legends_embed(
                        items, page, show_mode, filter_label
                    ),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in legends command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching legends.")

    @app_commands.command(
        name="unheld",
        description="Never-held categories, easiest first",
    )
    @app_commands.describe(
        tier="Optional difficulty tier filter",
        game_mode="Optional mode or High score modes only",
        apple_amount="Optional apple count filter",
        speed="Optional speed filter",
        size="Optional size filter",
        run_mode="Optional run mode filter",
    )
    @app_commands.choices(tier=[
        app_commands.Choice(name="Free", value="Free"),
        app_commands.Choice(name="Warmup", value="Warmup"),
        app_commands.Choice(name="Easy", value="Easy"),
        app_commands.Choice(name="Medium", value="Medium"),
        app_commands.Choice(name="Hard", value="Hard"),
        app_commands.Choice(name="Mythic", value="Mythic"),
        app_commands.Choice(name="Lottery", value="Lottery"),
        app_commands.Choice(name="Inhuman", value="Inhuman"),
    ])
    @app_commands.autocomplete(
        game_mode=list_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=list_run_mode_autocomplete,
    )
    async def unheld_command(
        self,
        interaction: discord.Interaction,
        tier: Optional[app_commands.Choice[str]] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            tier_value = tier.value if tier else None
            if tier_value == "Free":
                gif_path = os.path.join(os.path.dirname(__file__), "assets", "unheld_free.gif")
                await interaction.followup.send(
                    file=discord.File(gif_path, filename="unheld_free.gif")
                )
                return

            if tier_value == "Inhuman" and random.randint(1, 25) == 1:
                gif_path = os.path.join(os.path.dirname(__file__), "assets", "unheld_inhuman.gif")
                await interaction.followup.send(
                    file=discord.File(gif_path, filename="unheld_inhuman.gif")
                )
                return

            unheld_data = await github_cache_fetcher.get_unheld(tier_value)
            if unheld_data is None:
                await interaction.followup.send("❌ Unheld categories data unavailable.")
                return

            filters = dict(
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            )
            filter_label = self._format_category_filters(**filters)
            rows = self._filter_category_rows(unheld_data.get('rows') or [], **filters)
            unheld_data = {
                **unheld_data,
                'rows': rows,
                'shown': len(rows),
                'filter_label': filter_label,
            }
            if not rows:
                bits = [b for b in (tier_value, filter_label) if b]
                label = " • ".join(bits) if bits else "any filter"
                await interaction.followup.send(f"❌ No unheld categories found for {label}.")
                return

            embed = self.create_unheld_embed(unheld_data, page=0)
            total_pages = max(1, (len(rows) + 7) // 8)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_unheld_embed(unheld_data, page),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in unheld command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching unheld categories.")

    def create_chronicle_era_embed(self, era: Dict) -> discord.Embed:
        """Era newspaper embed for a loud WR day."""
        date = era.get("date") or "?"
        flips = era.get("flips", 0)
        new_wrs = era.get("newWrs", 0)
        debuts = era.get("debuts") or []
        embed = discord.Embed(
            title=f"📰 Era Newspaper — {date}",
            description=(
                f"**{flips}** flip{'s' if flips != 1 else ''} · "
                f"**{new_wrs}** new WR{'s' if new_wrs != 1 else ''}"
                + (f" · **{len(debuts)}** setting debut{'s' if len(debuts) != 1 else ''}" if debuts else "")
            ),
            color=0x8b5a2b,
            timestamp=datetime.now(),
        )
        top_flips = era.get("topFlips") or []
        if top_flips:
            lines = []
            for flip in top_flips[:8]:
                cat = self._format_category_line(flip.get("category", ""))
                frm = flip.get("from") or "—"
                to = flip.get("to") or "?"
                time_str = dm.parse_time(flip.get("time") or "") if flip.get("time") else ""
                tier = flip.get("tier") or ""
                bits = [f"{frm} → **{to}**"]
                if time_str:
                    bits.append(time_str)
                if tier:
                    bits.append(tier)
                lines.append(f"{cat}\n{' · '.join(bits)}")
            embed.add_field(name="Top flips", value="\n".join(lines)[:1020], inline=False)
        gainers = era.get("netGainers") or []
        if gainers:
            embed.add_field(
                name="Net gainers",
                value="\n".join(
                    f"**{g.get('name', '?')}** +{g.get('delta', 0)} → {g.get('to', '?')}"
                    for g in gainers[:8]
                ),
                inline=True,
            )
        losers = era.get("netLosers") or []
        if losers:
            embed.add_field(
                name="Net losers",
                value="\n".join(
                    f"**{g.get('name', '?')}** {g.get('delta', 0)} → {g.get('to', '?')}"
                    for g in losers[:8]
                ),
                inline=True,
            )
        if debuts:
            embed.add_field(
                name="Setting debuts",
                value="\n".join(
                    f"**{d.get('kindLabel') or d.get('kind')}** `{d.get('value')}`"
                    + (f" — {d.get('player')}" if d.get("player") else "")
                    for d in debuts[:10]
                )[:1020],
                inline=False,
            )
        embed.set_footer(text="Data from FastSnakeStats • Chronicle")
        return embed

    def create_chronicle_empire_embed(self, empire: Dict) -> discord.Embed:
        """Empire arc embed for a player's WR-count history."""
        name = empire.get("name") or "Unknown"
        peak = empire.get("peak") or {}
        latest = empire.get("latest") or {}
        peak_str = (
            f"{peak.get('count')} on `{peak.get('date')}`"
            if peak.get("count") is not None else "—"
        )
        latest_pct = latest.get("percentage")
        latest_str = (
            f"{latest.get('count')} on `{latest.get('date')}`"
            + (f" ({latest_pct}%)" if latest_pct is not None else "")
            if latest.get("count") is not None else "—"
        )
        embed = discord.Embed(
            title=f"🏰 Empire — {name}",
            description=(
                f"**Peak:** {peak_str}\n"
                f"**Now:** {latest_str}\n"
                f"**Drop from peak:** −{empire.get('peakDrop', 0)}"
            ),
            color=0x6b4c9a,
            timestamp=datetime.now(),
        )
        tps = empire.get("turningPoints") or []
        if tps:
            lines = []
            for tp in tps[:8]:
                delta = tp.get("delta") or 0
                sign = "+" if delta >= 0 else ""
                lines.append(
                    f"`{tp.get('date')}` **{sign}{delta}** "
                    f"({tp.get('from')} → {tp.get('to')})"
                )
            embed.add_field(name="Turning points", value="\n".join(lines), inline=False)
        series = empire.get("series") or []
        if series:
            embed.add_field(
                name="Arc span",
                value=f"`{series[0].get('d')}` → `{series[-1].get('d')}` · {len(series)} points",
                inline=False,
            )
        embed.set_footer(text="Data from FastSnakeStats • Chronicle")
        return embed

    def create_chronicle_war_embed(self, war: Dict, page: int = 0) -> discord.Embed:
        """Board war reel — WR handoff events for one category."""
        category = war.get("category") or ""
        events = war.get("events") or []
        per_page = 8
        total_pages = max(1, (len(events) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        start = page * per_page
        page_events = events[start:start + per_page]

        embed = discord.Embed(
            title="⚔️ Board War Reel",
            description=(
                f"{self._format_category_line(category)}\n"
                f"**{war.get('flips', 0)}** flips · **{war.get('eventCount', len(events))}** events"
                + (" · currently tied" if war.get("tied") else "")
            ),
            color=0xb33a3a,
            timestamp=datetime.now(),
        )
        lines = []
        for event in page_events:
            runs = event.get("runs") or []
            names = ", ".join(r.get("n") or "?" for r in runs) or "?"
            times = []
            for run in runs:
                t = run.get("t")
                if t:
                    times.append(dm.parse_time(t))
            time_bit = f" · {' / '.join(times)}" if times else ""
            lines.append(f"`{event.get('d')}` **{names}**{time_bit}")
        if lines:
            embed.add_field(name="Handoffs", value="\n".join(lines), inline=False)
        embed.set_footer(
            text=f"Data from FastSnakeStats • Chronicle • Page {page + 1}/{total_pages}"
        )
        return embed

    def create_chronicle_wars_list_embed(self, wars: List[Dict], page: int = 0) -> discord.Embed:
        """Top contested board wars list."""
        per_page = 10
        total_pages = max(1, (len(wars) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        start = page * per_page
        page_wars = wars[start:start + per_page]
        embed = discord.Embed(
            title="⚔️ Most Contested Board Wars",
            description="Use `/chronicle section:War` with category filters to open a reel.",
            color=0xb33a3a,
            timestamp=datetime.now(),
        )
        lines = []
        for i, war in enumerate(page_wars, start + 1):
            tied = " · tied" if war.get("tied") else ""
            lines.append(
                f"**{i}.** {self._format_category_line(war.get('category', ''))}\n"
                f"{war.get('flips', 0)} flips · {war.get('eventCount', 0)} events{tied}"
            )
        embed.add_field(name="Wars", value="\n".join(lines) or "None", inline=False)
        embed.set_footer(
            text=f"Data from FastSnakeStats • Chronicle • Page {page + 1}/{total_pages}"
        )
        return embed

    def create_chronicle_debuts_embed(self, intros: List[Dict], page: int = 0) -> discord.Embed:
        """Setting introductions / first-seen debuts."""
        per_page = 12
        total_pages = max(1, (len(intros) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        start = page * per_page
        page_items = intros[start:start + per_page]
        embed = discord.Embed(
            title="✨ Setting Debuts",
            description="First verified appearance of each setting in the runs archive.",
            color=0x2e8b57,
            timestamp=datetime.now(),
        )
        lines = []
        for item in page_items:
            kind = item.get("kindLabel") or item.get("kind") or "?"
            player = item.get("player") or "?"
            lines.append(
                f"`{item.get('date')}` **{kind}** `{item.get('value')}` — {player}"
            )
        embed.add_field(name="Introductions", value="\n".join(lines) or "None", inline=False)
        embed.set_footer(
            text=f"Data from FastSnakeStats • Chronicle • Page {page + 1}/{total_pages}"
        )
        return embed

    @app_commands.command(
        name="chronicle",
        description="Chronicle: era newspaper, empire arcs, board wars, setting debuts",
    )
    @app_commands.describe(
        section="Era newspaper, empire arc, board war reel, or setting debuts",
        player="Player name for Empire (defaults to top empire)",
        date="Era date YYYY-MM-DD (defaults to latest loud day)",
        game_mode="Optional mode filter for War",
        apple_amount="Optional apple count filter for War",
        speed="Optional speed filter for War",
        size="Optional size filter for War",
        run_mode="Optional run mode filter for War",
        list_wars="If true with War section, list top wars instead of one reel",
    )
    @app_commands.choices(section=[
        app_commands.Choice(name="Era", value="era"),
        app_commands.Choice(name="Empire", value="empire"),
        app_commands.Choice(name="War", value="war"),
        app_commands.Choice(name="Debuts", value="debuts"),
    ])
    @app_commands.autocomplete(
        player=player_name_autocomplete,
        game_mode=record_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=record_run_mode_autocomplete,
    )
    async def chronicle_command(
        self,
        interaction: discord.Interaction,
        section: app_commands.Choice[str],
        player: Optional[str] = None,
        date: Optional[str] = None,
        game_mode: Optional[str] = None,
        apple_amount: Optional[str] = None,
        speed: Optional[str] = None,
        size: Optional[str] = None,
        run_mode: Optional[str] = None,
        list_wars: Optional[bool] = None,
    ):
        await interaction.response.defer()
        try:
            section_key = section.value
            data = await github_cache_fetcher.fetch_chronicle()
            if not data:
                await interaction.followup.send("❌ Chronicle data unavailable.")
                return

            if section_key == "era":
                era = await github_cache_fetcher.get_chronicle_era(date)
                if not era:
                    msg = (
                        f"❌ No era found for `{date}`."
                        if date else "❌ No era newspaper data found."
                    )
                    await interaction.followup.send(msg)
                    return
                await interaction.followup.send(embed=self.create_chronicle_era_embed(era))
                return

            if section_key == "empire":
                empire = await github_cache_fetcher.get_chronicle_empire(
                    player_name=player
                )
                if not empire:
                    msg = (
                        f"❌ No empire arc found for **{player}**."
                        if player else "❌ No empire data found."
                    )
                    await interaction.followup.send(msg)
                    return
                await interaction.followup.send(
                    embed=self.create_chronicle_empire_embed(empire)
                )
                return

            if section_key == "debuts":
                intros = await github_cache_fetcher.get_chronicle_introductions()
                if not intros:
                    await interaction.followup.send("❌ No setting debuts found.")
                    return
                embed = self.create_chronicle_debuts_embed(intros, page=0)
                total_pages = max(1, (len(intros) + 11) // 12)
                if total_pages > 1:
                    view = ListPaginationView(
                        interaction.user.id,
                        total_pages,
                        lambda page: self.create_chronicle_debuts_embed(intros, page),
                    )
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed)
                return

            # War section
            wars = await github_cache_fetcher.get_chronicle_wars()
            if not wars:
                await interaction.followup.send("❌ No board war data found.")
                return

            filters = dict(
                game_mode=game_mode,
                apple_amount=apple_amount,
                speed=speed,
                size=size,
                run_mode=run_mode,
            )
            # No filters / explicit list: top contested wars. Filters: open matching reel.
            if list_wars or not self._any_category_filters(**filters):
                embed = self.create_chronicle_wars_list_embed(wars, page=0)
                total_pages = max(1, (len(wars) + 9) // 10)
                if total_pages > 1:
                    view = ListPaginationView(
                        interaction.user.id,
                        total_pages,
                        lambda page: self.create_chronicle_wars_list_embed(wars, page),
                    )
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed)
                return

            filtered = self._filter_category_rows(wars, **filters)
            if not filtered:
                label = self._format_category_filters(**filters)
                await interaction.followup.send(
                    f"❌ No board wars match `{label}`."
                )
                return

            war = filtered[0]
            events = war.get("events") or []
            embed = self.create_chronicle_war_embed(war, page=0)
            total_pages = max(1, (len(events) + 7) // 8)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_chronicle_war_embed(war, page),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in chronicle command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while fetching Chronicle data."
            )

    def _player_hold_map(self, world_records: Dict, player_name: str) -> Dict[str, List]:
        needle = (player_name or "").lower().strip()
        held: Dict[str, List] = {}
        if not needle:
            return held
        for key, runs in (world_records or {}).items():
            mine = [
                run for run in (runs or [])
                if dm.get_player_name(run).lower() == needle
            ]
            if mine:
                held[key] = mine
        return held

    def create_compare_embed(self, data: Dict, page: int = 0) -> discord.Embed:
        name_a = data["name_a"]
        name_b = data["name_b"]
        only_a = data["only_a"]
        only_b = data["only_b"]
        shared = data["shared"]
        rows = data["rows"]
        per_page = 8
        total_pages = max(1, (len(rows) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        page_rows = rows[page * per_page: page * per_page + per_page]

        embed = discord.Embed(
            title=f"Compare — {name_a} vs {name_b}",
            description=(
                f"**{name_a}:** {data['count_a']} WRs ({data['pct_a']:.2f}%)\n"
                f"**{name_b}:** {data['count_b']} WRs ({data['pct_b']:.2f}%)\n"
                f"Unique {name_a}: **{len(only_a)}** · Unique {name_b}: **{len(only_b)}** · "
                f"Shared/tied: **{len(shared)}**"
            ),
            color=0x5865f2,
            timestamp=datetime.now(),
        )
        if page_rows:
            lines = []
            for row in page_rows:
                cat = self._format_category_line(row["category"])
                if row["side"] == "a":
                    lines.append(f"**{name_a} only** — {cat}")
                elif row["side"] == "b":
                    lines.append(f"**{name_b} only** — {cat}")
                else:
                    lines.append(f"**Tied** — {cat}")
            embed.add_field(name="Boards", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Boards", value="No overlapping or unique boards.", inline=False)
        embed.set_footer(
            text=f"Data from FastSnakeStats • {data['date']} • Page {page + 1}/{total_pages}"
        )
        return embed

    @app_commands.command(
        name="compare",
        description="Compare two players' current (or historical) WR holds",
    )
    @app_commands.describe(
        player_a="First player",
        player_b="Second player",
        date="Historical date - optional",
    )
    @app_commands.autocomplete(
        player_a=player_name_autocomplete,
        player_b=player_name_autocomplete,
        date=player_date_autocomplete,
    )
    async def compare_command(
        self,
        interaction: discord.Interaction,
        player_a: str,
        player_b: str,
        date: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            if player_a.strip().lower() == player_b.strip().lower():
                await interaction.followup.send("Pick two different players to compare.")
                return
            if date and not await github_cache_fetcher.is_date_available(date):
                await interaction.followup.send(
                    f"❌ No data available for date: {date}. Use `/available-dates`."
                )
                return

            peak_a = await github_cache_fetcher.get_player_peak_stats(player_a)
            peak_b = await github_cache_fetcher.get_player_peak_stats(player_b)
            name_a = (peak_a or {}).get("name") or player_a
            name_b = (peak_b or {}).get("name") or player_b

            if date:
                world_records = await github_cache_fetcher.fetch_world_records_for_date(date)
            else:
                world_records = await github_cache_fetcher.fetch_current_world_records()
            if not world_records:
                await interaction.followup.send("❌ Could not load world records.")
                return

            held_a = self._player_hold_map(world_records, name_a)
            held_b = self._player_hold_map(world_records, name_b)
            keys_a = set(held_a)
            keys_b = set(held_b)
            only_a = sorted(keys_a - keys_b)
            only_b = sorted(keys_b - keys_a)
            shared = sorted(keys_a & keys_b)
            total = sum(1 for runs in world_records.values() if runs)
            count_a = len(keys_a)
            count_b = len(keys_b)
            pct_a = round((count_a / total) * 100, 2) if total else 0.0
            pct_b = round((count_b / total) * 100, 2) if total else 0.0

            rows = (
                [{"side": "a", "category": k} for k in only_a]
                + [{"side": "b", "category": k} for k in only_b]
                + [{"side": "shared", "category": k} for k in shared]
            )
            snapshot = date or await github_cache_fetcher.get_most_recent_date() or "latest"
            data = {
                "name_a": name_a,
                "name_b": name_b,
                "count_a": count_a,
                "count_b": count_b,
                "pct_a": pct_a,
                "pct_b": pct_b,
                "only_a": only_a,
                "only_b": only_b,
                "shared": shared,
                "rows": rows,
                "date": snapshot,
            }
            embed = self.create_compare_embed(data, page=0)
            total_pages = max(1, (len(rows) + 7) // 8)
            if total_pages > 1:
                view = ListPaginationView(
                    interaction.user.id,
                    total_pages,
                    lambda page: self.create_compare_embed(data, page),
                )
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in compare command: {e}")
            await interaction.followup.send("❌ An error occurred while comparing players.")

    HELP_PAGES = [
        (
            "Records & time travel",
            "- `/record` — WR for a category (optional date)\n"
            "- `/leaderboards` — full WR table for count/speed/size\n"
            "- `/available-dates` — dates with FastSnakeStats snapshots\n"
            "- `/watch add` — ping you when that category's WR changes\n"
            "- `/watch list` / `/watch remove` / `/watch clear`",
        ),
        (
            "Players",
            "- `/player` — profile, holds, or Mastery boards\n"
            "- `/compare` — unique vs shared WR holds between two players\n"
            "- `/career` — career WR-days leaderboard\n"
            "- `/mastery` — All Apples challenge leaderboard or one player\n"
            "- `/chronicle` — era newspaper, empire arcs, board wars, debuts",
        ),
        (
            "Statistics explorer",
            "- `/stats` — top holders by count / percentage\n"
            "- `/report` — weekly WR changes\n"
            "- `/monthly` — oldest-records update\n"
            "- `/random` — random valid challenge + current WR\n"
            "- `/progression` `/longevity` `/improving` `/contested`\n"
            "- `/popularity` `/stale` `/legends` `/unicorns` `/unheld` `/activity`",
        ),
        (
            "Tools",
            "- `/caption` — ESMBot-style caption on an image or GIF\n"
            "- Select Image — right-click a message → Apps → Select Image\n"
            "- `/wallall` — solve small-board Wall All (paste pudding `pattern 12…` copy, or a 90-cell 0/1 or 1/2 grid)\n"
            "- `pattern <grid>` — same solver; pudding clipboard paste works as-is\n"
            "- `/help` — this command list",
        ),
    ]

    def create_help_embed(self, page: int = 0) -> discord.Embed:
        total = len(self.HELP_PAGES)
        page = max(0, min(page, total - 1))
        title, body = self.HELP_PAGES[page]
        embed = discord.Embed(
            title="PuddingBot help",
            description=f"**{title}**\n{body}",
            color=0xf5c518,
            timestamp=datetime.now(),
        )
        embed.set_footer(text=f"Page {page + 1}/{total}")
        return embed

    @app_commands.command(name="help", description="List PuddingBot slash commands")
    async def help_command(self, interaction: discord.Interaction):
        embed = self.create_help_embed(0)
        view = ListPaginationView(
            interaction.user.id,
            len(self.HELP_PAGES),
            self.create_help_embed,
        )
        await interaction.response.send_message(embed=embed, view=view)

    async def watch_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        watches = wr_watch.list_user_watches(interaction.user.id)
        needle = (current or "").lower()
        choices: List[app_commands.Choice[str]] = []
        for watch in watches:
            category = watch.get("category") or ""
            if not category:
                continue
            label = dm.format_category_key(category, with_icons=False)
            if needle and needle not in category.lower() and needle not in label.lower():
                continue
            choices.append(app_commands.Choice(name=label[:100], value=category))
            if len(choices) >= 25:
                break
        return choices

    @watch_group.command(name="add", description="Watch a category for WR changes")
    @app_commands.describe(
        game_mode="Game mode",
        apple_amount="Apple count",
        speed="Speed",
        size="Size",
        run_mode="Run mode",
    )
    @app_commands.autocomplete(
        game_mode=record_game_mode_autocomplete,
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        run_mode=record_run_mode_autocomplete,
    )
    async def watch_add_command(
        self,
        interaction: discord.Interaction,
        game_mode: str,
        apple_amount: str,
        speed: str,
        size: str,
        run_mode: str,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            if not dm.is_valid_category(apple_amount, speed, size, game_mode, run_mode):
                await interaction.followup.send("That settings combination isn't a valid board.", ephemeral=True)
                return
            if interaction.channel is None:
                await interaction.followup.send("Run this in a channel I can post in.", ephemeral=True)
                return
            category = dm.get_settings_key(apple_amount, speed, size, game_mode, run_mode)
            records = await github_cache_fetcher.fetch_current_world_records()
            runs = (records or {}).get(category) or []
            fingerprint = wr_watch.fingerprint_runs(runs)
            player = dm.get_player_name(runs[0]) if runs else "unheld"
            time_str = dm.get_run_time(runs[0]) if runs else "—"
            entry, err = wr_watch.add_watch(
                user_id=interaction.user.id,
                channel_id=interaction.channel.id,
                guild_id=interaction.guild.id if interaction.guild else None,
                category=category,
                fingerprint=fingerprint,
                player=player,
                time_str=time_str,
            )
            if err:
                await interaction.followup.send(err, ephemeral=True)
                return
            current = self._watch_holder_line(runs)
            await interaction.followup.send(
                f"Watching {self._format_category_line(category)} in this channel.\n"
                f"Current: {current}\n"
                f"I'll ping you here when the WR changes (checked about once a day).",
                ephemeral=True,
            )
        except Exception as e:
            print(f"Error in /watch add: {e}")
            await interaction.followup.send("Failed to add that watch.", ephemeral=True)

    @watch_group.command(name="list", description="List your WR watches")
    async def watch_list_command(self, interaction: discord.Interaction):
        watches = wr_watch.list_user_watches(interaction.user.id)
        if not watches:
            await interaction.response.send_message(
                "You have no watches. Use `/watch add` on a category.",
                ephemeral=True,
            )
            return
        lines = []
        for watch in watches:
            cat = self._format_category_line(watch.get("category") or "")
            holder = watch.get("player") or "unheld"
            time_str = watch.get("time") or "—"
            lines.append(f"• {cat} — {holder} · {time_str}")
        text = "\n".join(lines)
        if len(text) > 1900:
            text = text[:1900] + "\n…"
        await interaction.response.send_message(f"**Your watches ({len(watches)})**\n{text}", ephemeral=True)

    @watch_group.command(name="remove", description="Stop watching a category")
    @app_commands.describe(category="Category key from /watch list autocomplete")
    @app_commands.autocomplete(category=watch_remove_autocomplete)
    async def watch_remove_command(self, interaction: discord.Interaction, category: str):
        removed = wr_watch.remove_watch(interaction.user.id, category)
        if not removed:
            await interaction.response.send_message(
                "You weren't watching that category.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Stopped watching {self._format_category_line(category)}.",
            ephemeral=True,
        )

    @watch_group.command(name="clear", description="Remove all of your WR watches")
    async def watch_clear_command(self, interaction: discord.Interaction):
        removed = wr_watch.clear_user_watches(interaction.user.id)
        await interaction.response.send_message(
            f"Cleared **{removed}** watch(es)." if removed else "You had no watches.",
            ephemeral=True,
        )

    @app_commands.command(
        name="activity",
        description="Yearly new-WR activity (day the #1 actually changed)",
    )
    @app_commands.describe(year="Year to summarize (defaults to latest)")
    @app_commands.autocomplete(year=activity_year_autocomplete)
    async def activity_command(self, interaction: discord.Interaction, year: Optional[str] = None):
        await interaction.response.defer()
        try:
            heatmap = await github_cache_fetcher.get_activity_heatmap()
            if heatmap is None:
                await interaction.followup.send("❌ Activity data unavailable.")
                return
            if not heatmap:
                await interaction.followup.send("❌ No activity heatmap data found.")
                return

            years = sorted({entry.get('date', '')[:4] for entry in heatmap if entry.get('date')})
            selected_year = year or (years[-1] if years else None)
            if not selected_year or selected_year not in years:
                await interaction.followup.send(
                    f"❌ Invalid year. Available: {', '.join(years[-10:])}"
                )
                return

            # Heatmap `flips` = #1 player/time changed vs previous day.
            # Ignore heatmap `newWrs` (SRC run.date == snapshot day / verify timing).
            year_entries = []
            for e in heatmap:
                if not (e.get('date') or '').startswith(selected_year):
                    continue
                year_entries.append({
                    'date': e.get('date'),
                    'newWrs': e.get('flips', 0) or 0,
                })

            total_new = sum(e['newWrs'] for e in year_entries)
            active_days = sum(1 for e in year_entries if e['newWrs'] > 0)
            top_days = sorted(year_entries, key=lambda e: e['newWrs'], reverse=True)[:10]

            summary = {
                'total_new_wrs': total_new,
                'active_days': active_days,
                'top_days': top_days,
            }
            embed = self.create_activity_embed(selected_year, summary)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in activity command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching activity data.")

    @app_commands.command(
        name="leaderboards",
        description="Full WR table for a count, speed, and size across all categories",
    )
    @app_commands.describe(
        apple_amount="Number of apples",
        speed="Game speed",
        size="Game size",
        date="Historical date - optional",
    )
    @app_commands.autocomplete(
        apple_amount=record_apple_amount_autocomplete,
        speed=record_speed_autocomplete,
        size=record_size_autocomplete,
        date=record_date_autocomplete,
    )
    async def leaderboards_command(
        self,
        interaction: discord.Interaction,
        apple_amount: str,
        speed: str,
        size: str,
        date: Optional[str] = None,
    ):
        await interaction.response.defer()
        try:
            board_data = await self.get_leaderboards_data(apple_amount, speed, size, date)
            if not board_data:
                if date:
                    await interaction.followup.send(
                        f"❌ No leaderboard data for that combination on {date}."
                    )
                else:
                    await interaction.followup.send(
                        "❌ No leaderboard data for that combination."
                    )
                return

            if not board_data['rows']:
                await interaction.followup.send(
                    f"❌ No world records found for "
                    f"{apple_amount} • {speed} • {size}."
                )
                return

            embed = self.create_leaderboards_embed(board_data, page=0)
            total_pages = max(1, (len(board_data['rows']) + 7) // 8)
            if total_pages > 1:
                view = LeaderboardsPaginationView(board_data, interaction.user.id)
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"Error in leaderboards command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching leaderboards.")

class ListPaginationView(discord.ui.View):
    """Generic Prev/Next pagination for explorer list embeds."""

    def __init__(self, user_id: int, total_pages: int, embed_factory):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.current_page = 0
        self.total_pages = max(1, total_pages)
        self.embed_factory = embed_factory

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.gray, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pagination is not for you!", ephemeral=True)
            return
        self.current_page = max(0, self.current_page - 1)
        await self.update_view(interaction)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pagination is not for you!", ephemeral=True)
            return
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        await self.update_view(interaction)

    async def update_view(self, interaction: discord.Interaction):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        embed = self.embed_factory(self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)


class LeaderboardsPaginationView(discord.ui.View):
    """Pagination for /leaderboards tables."""

    def __init__(self, board_data: Dict, user_id: int):
        super().__init__(timeout=300)
        self.board_data = board_data
        self.user_id = user_id
        self.current_page = 0
        self.items_per_page = 8
        rows_len = len(board_data.get('rows') or [])
        self.total_pages = max(1, (rows_len + self.items_per_page - 1) // self.items_per_page)

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.gray, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pagination is not for you!", ephemeral=True)
            return
        self.current_page = max(0, self.current_page - 1)
        await self.update_view(interaction)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pagination is not for you!", ephemeral=True)
            return
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        await self.update_view(interaction)

    async def update_view(self, interaction: discord.Interaction):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        embed = self.create_leaderboards_embed(self.board_data, self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)

    def create_leaderboards_embed(self, board_data: Dict, page: int = 0) -> discord.Embed:
        items_per_page = self.items_per_page
        rows = board_data.get('rows') or []
        total_pages = max(1, (len(rows) + items_per_page - 1) // items_per_page)
        start = page * items_per_page
        page_rows = rows[start:start + items_per_page]

        embed = discord.Embed(
            title=(
                f"🏆 Leaderboards — {board_data['apple_amount']} • "
                f"{board_data['speed']} • {board_data['size']}"
            ),
            color=0x00ff00,
            timestamp=datetime.now()
        )
        lines = []
        for row in page_rows:
            line = f"**{row['gamemode']} • {row['run_mode']}** — {row['player']} — {row['time']}"
            if row.get('link'):
                line += f" • [View]({row['link']})"
            lines.append(line)
        embed.add_field(
            name=f"World Records ({len(rows)} categories)",
            value="\n".join(lines) if lines else "No records found for this combination.",
            inline=False
        )
        embed.set_footer(
            text=f"Data from FastSnakeStats • {board_data['date']} • Page {page + 1}/{total_pages}"
        )
        return embed

class StatsPaginationView(discord.ui.View):
    """View for paginating through stats results"""
    
    def __init__(self, stats_data: Dict, user_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.stats_data = stats_data
        self.user_id = user_id
        self.current_page = 0
        self.players_per_page = 10
        self.total_pages = (len(stats_data['top_by_percentage']) + self.players_per_page - 1) // self.players_per_page
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.gray, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pagination is not for you!", ephemeral=True)
            return
        
        self.current_page = max(0, self.current_page - 1)
        await self.update_view(interaction)
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pagination is not for you!", ephemeral=True)
            return
        
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        await self.update_view(interaction)
    
    async def update_view(self, interaction: discord.Interaction):
        """Update the view with new page"""
        # Update button states
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        
        # Create new embed
        embed = self.create_stats_embed(self.stats_data, self.current_page)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_stats_embed(self, stats_data: Dict, page: int = 0) -> discord.Embed:
        """Create a rich embed for stats display with pagination"""
        embed = discord.Embed(
            title="📊 Top Record Holders",
            color=0xff9900,  # Orange for statistics
            timestamp=datetime.now()
        )
        
        # Add top by percentage with pagination
        start_idx = page * self.players_per_page
        end_idx = start_idx + self.players_per_page
        page_players = stats_data['top_by_percentage'][start_idx:end_idx]
        
        top_by_percentage_text = ""
        for i, (player, count) in enumerate(page_players, start_idx + 1):
            percentage = (count / stats_data['total_world_records']) * 100
            top_by_percentage_text += f"{i}. **{player}** - **{count}** records • {percentage:.1f}%\n"
        
        if not top_by_percentage_text:
            top_by_percentage_text = "No more players to show."
        
        embed.add_field(
            name="🏆 Most Records",
            value=top_by_percentage_text,
            inline=False
        )
        
        # Add total world records at the bottom
        embed.add_field(
            name="📈 Total World Records",
            value=str(stats_data['total_world_records']),
            inline=False
        )
        
        # Add footer with page info
        embed.set_footer(text=f"Data from FastSnakeStats • {stats_data['date']} • Page {page + 1}/{self.total_pages}")
        
        return embed

class PlayerPaginationView(discord.ui.View):
    """View for paginating through player holds"""
    
    def __init__(self, player_data: Dict, user_id: int, embed_factory):
        super().__init__(timeout=300)  # 5 minute timeout
        self.player_data = player_data
        self.user_id = user_id
        self.embed_factory = embed_factory
        self.current_page = 0
        self.runs_per_page = 5
        activity_len = len(player_data.get('recent_activity') or [])
        self.total_pages = max(1, (activity_len + self.runs_per_page - 1) // self.runs_per_page)
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.gray, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pagination is not for you!", ephemeral=True)
            return
        
        self.current_page = max(0, self.current_page - 1)
        await self.update_view(interaction)
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pagination is not for you!", ephemeral=True)
            return
        
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        await self.update_view(interaction)
    
    async def update_view(self, interaction: discord.Interaction):
        """Update the view with new page"""
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        embed = self.embed_factory(self.player_data, self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)

class ReportPaginationView(discord.ui.View):
    """View for paginating through report results"""
    
    def __init__(self, report_data: Dict, user_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.report_data = report_data
        self.user_id = user_id
        self.current_page = 0
        self.items_per_page = 3
        
        # Calculate total items and pages
        all_items = (len(report_data['new_records']) + 
                    len(report_data['record_changes']) + 
                    len(report_data['improved_records']))
        self.total_pages = (all_items + self.items_per_page - 1) // self.items_per_page
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.gray, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pagination is not for you!", ephemeral=True)
            return
        
        self.current_page = max(0, self.current_page - 1)
        await self.update_view(interaction)
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pagination is not for you!", ephemeral=True)
            return
        
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        await self.update_view(interaction)
    
    async def update_view(self, interaction: discord.Interaction):
        """Update the view with new page"""
        # Update button states
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        
        # Create new embed
        embed = self.create_weekly_report_embed(self.report_data, self.current_page)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_weekly_report_embed(self, report_data: Dict, page: int = 0) -> discord.Embed:
        """Create a rich embed for weekly report display with pagination"""
        embed = discord.Embed(
            title="📈 Weekly Record Report",
            description=f"Record changes from {report_data['week_ago_date']} to {report_data['current_date']}",
            color=0x00ff88,  # Green for reports
            timestamp=datetime.now()
        )
        
        # Add summary statistics
        embed.add_field(
            name="📊 Summary",
            value=f"**Total Changes:** {report_data['total_changes']}\n"
                  f"**New Records:** {len(report_data['new_records'])}\n"
                  f"**Record Changes:** {len(report_data['record_changes'])}\n"
                  f"**Improved Records:** {len(report_data['improved_records'])}",
            inline=False
        )
        
        # Determine what to show based on page
        all_items = []
        
        # Add new records
        for item in report_data['new_records']:
            all_items.append(('🆕', item, 'new'))
        
        # Add record changes
        for item in report_data['record_changes']:
            all_items.append(('🔄', item, 'change'))
        
        # Add improved records
        for item in report_data['improved_records']:
            all_items.append(('⚡', item, 'improved'))
        
        if not all_items:
            embed.add_field(
                name="📝 No Changes",
                value="No record changes were detected in the last 7 days.",
                inline=False
            )
        else:
            # Paginate through all items
            start_idx = page * self.items_per_page
            end_idx = start_idx + self.items_per_page
            page_items = all_items[start_idx:end_idx]
            
            changes_text = ""
            for emoji, item, item_type in page_items:
                settings_parts = item['settings'].split('|')
                run_mode = settings_parts[4]
                category_info = dm.format_category_key(record['settings'])
                
                if item_type == 'new':
                    display_time = self._format_time_for_display(item['time'], run_mode)
                    changes_text += f"{emoji} **NEW RECORD** - {category_info}\n"
                    changes_text += f"   👤 **{item['player']}** • {display_time} • {item['date']}\n\n"
                
                elif item_type == 'change':
                    old_display_time = self._format_time_for_display(item['old_time'], run_mode)
                    new_display_time = self._format_time_for_display(item['new_time'], run_mode)
                    changes_text += f"{emoji} **RECORD CHANGE** - {category_info}\n"
                    changes_text += f"   🔄 **{item['old_player']}** → **{item['new_player']}**\n"
                    changes_text += f"   ⏱️ {old_display_time} → {new_display_time}\n"
                    if item['improvement']:
                        improvement_str = self._format_improvement(item['improvement'])
                        changes_text += f"   📈 Improvement: {improvement_str}\n"
                    changes_text += f"   📅 {item['new_date']}\n\n"
                
                elif item_type == 'improved':
                    old_display_time = self._format_time_for_display(item['old_time'], run_mode)
                    new_display_time = self._format_time_for_display(item['new_time'], run_mode)
                    changes_text += f"{emoji} **IMPROVED RECORD** - {category_info}\n"
                    changes_text += f"   👤 **{item['player']}**\n"
                    changes_text += f"   ⏱️ {old_display_time} → {new_display_time}\n"
                    if item['improvement']:
                        improvement_str = self._format_improvement(item['improvement'])
                        changes_text += f"   📈 Improvement: {improvement_str}\n"
                    changes_text += f"   📅 {item['new_date']}\n\n"
            
            if not changes_text:
                changes_text = "No more changes to show."
            
            embed.add_field(
                name="📝 Record Changes",
                value=changes_text,
                inline=False
            )
        
        # Add footer with page info
        embed.set_footer(text=f"Data from FastSnakeStats • Page {page + 1}/{self.total_pages}")
        
        return embed
    
    def _format_improvement(self, improvement_ms: float) -> str:
        """Format improvement time in a readable way"""
        if improvement_ms < 1000:
            return f"{improvement_ms:.0f}ms"
        elif improvement_ms < 60000:
            seconds = improvement_ms / 1000
            return f"{seconds:.1f}s"
        else:
            minutes = improvement_ms / 60000
            return f"{minutes:.1f}m"
    
    def _format_time_for_display(self, time_str: str, run_mode: str) -> str:
        """Format time string for display, handling High Score mode specially"""
        if run_mode == "High Score":
            # Check for both old format (0m 0s Xms) and new format (Xs Yms)
            if time_str.startswith("0m 0s ") or (time_str.endswith("ms") and "m " not in time_str and "h " not in time_str):
                # Extract the milliseconds part for High Score
                if time_str.startswith("0m 0s "):
                    score = time_str.replace("0m 0s ", "").replace("ms", "")
                else:
                    # New format: "Xs Yms" -> extract Y
                    score = time_str.split("s ")[1].replace("ms", "")
                return f"{score} apples"
            else:
                return time_str
        else:
            return time_str

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(FastSnakeStats(bot))

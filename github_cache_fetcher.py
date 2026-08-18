import os
import requests
import json
from typing import Optional, Dict, List, Any
from datetime import datetime

class GitHubCacheFetcher:
    """Fetches world records from FastSnakeStats runs-derived WR timelines."""
    
    def __init__(self):
        self.base_url = 'https://raw.githubusercontent.com/DarkSnakeGang/FastSnakeStats/refs/heads/main'
        self.runs_dates_url = f"{self.base_url}/time-travel-cache/metadata/available-dates-runs.json"
        self.timelines_url = f"{self.base_url}/time-travel-cache/runs-derived/wr-timelines.json"
        self.player_stats_url = f"{self.base_url}/time-travel-cache/metadata/player-stats.json"
        self.statistics_explorer_url = f"{self.base_url}/time-travel-cache/metadata/statistics-explorer.json"
        self.mastery_challenge_url = f"{self.base_url}/time-travel-cache/metadata/mastery-challenge.json"
        self.chronicle_url = f"{self.base_url}/time-travel-cache/metadata/chronicle.json"
        # Sibling FastSnakeStats checkout used when GitHub lags
        self._local_fss_root = os.path.normpath(os.path.join(
            os.path.dirname(__file__),
            '..',
            'FastSnakeStats',
            'time-travel-cache',
        ))
        self._local_runs_dates_path = os.path.join(
            self._local_fss_root, 'metadata', 'available-dates-runs.json'
        )
        self._local_timelines_path = os.path.join(
            self._local_fss_root, 'runs-derived', 'wr-timelines.json'
        )
        self._local_statistics_explorer_path = os.path.join(
            self._local_fss_root, 'metadata', 'statistics-explorer.json'
        )
        self._local_mastery_challenge_path = os.path.join(
            self._local_fss_root, 'metadata', 'mastery-challenge.json'
        )
        self._local_chronicle_path = os.path.join(
            self._local_fss_root, 'metadata', 'chronicle.json'
        )
        self.fallback_to_api = True
        self._runs_dates: Optional[Dict] = None
        self._timelines: Optional[Dict] = None
        self._player_stats_cache: Optional[Dict] = None
        self._player_stats_cache_fetched_at: Optional[datetime] = None
        self._statistics_explorer_cache: Optional[Dict] = None
        self._statistics_explorer_cache_fetched_at: Optional[datetime] = None
        self._mastery_challenge_cache: Optional[Dict] = None
        self._mastery_challenge_cache_fetched_at: Optional[datetime] = None
        self._chronicle_cache: Optional[Dict] = None
        self._chronicle_cache_fetched_at: Optional[datetime] = None

    def _load_local_json(self, path: str) -> Optional[Dict]:
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                return json.load(handle)
        except Exception as error:
            print(f'Error reading local JSON {path}: {error}')
            return None

    def _load_runs_dates(self) -> Optional[Dict]:
        """Load available-dates-runs.json (local sibling first, then GitHub)."""
        if self._runs_dates is not None:
            return self._runs_dates

        local = self._load_local_json(self._local_runs_dates_path)
        if local and local.get('availableDates'):
            self._runs_dates = local
            return self._runs_dates

        try:
            response = requests.get(self.runs_dates_url, timeout=15)
            if response.ok:
                metadata = response.json()
                if metadata.get('availableDates'):
                    self._runs_dates = metadata
                    return self._runs_dates
            print('Runs-derived dates metadata not available')
        except Exception as error:
            print(f'Error fetching runs-derived dates: {error}')
        return None

    def _load_timelines(self) -> Optional[Dict]:
        """Load wr-timelines.json once (local sibling first, then GitHub)."""
        if self._timelines is not None:
            return self._timelines

        local = self._load_local_json(self._local_timelines_path)
        if local and local.get('boards'):
            self._timelines = local
            print('Loaded local runs-derived WR timelines')
            return self._timelines

        try:
            print('Fetching runs-derived WR timelines from GitHub...')
            response = requests.get(self.timelines_url, timeout=120)
            if not response.ok:
                print(f'WR timelines not available ({response.status_code})')
                return None
            self._timelines = response.json()
            print('Successfully loaded runs-derived WR timelines')
            return self._timelines
        except Exception as error:
            print(f'Error fetching WR timelines: {error}')
            return None

    @staticmethod
    def _wr_as_of(timeline: List[Dict], date: str) -> List[Dict]:
        """Binary-search last timeline event with d <= date; return its runs."""
        if not timeline:
            return []
        lo = 0
        hi = len(timeline) - 1
        best = -1
        while lo <= hi:
            mid = (lo + hi) >> 1
            if timeline[mid].get('d', '') <= date:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if best < 0:
            return []
        return timeline[best].get('runs') or []

    def _build_derived_day(self, timelines: Dict, date: str) -> Dict:
        """Expand compact timeline runs into daily-cache-compatible records."""
        boards = (timelines or {}).get('boards') or {}
        records: Dict[str, Any] = {}
        for category, timeline in boards.items():
            top = self._wr_as_of(timeline or [], date)
            parts = category.split('|')
            count_part = parts[4] if len(parts) > 4 else ''
            settings_count = (
                'H' if count_part == 'High Score'
                else str(count_part or '').replace(' Apples', '')
            )
            records[category] = {
                'success': len(top) > 0,
                'settings': [
                    parts[0] if len(parts) > 0 else '',
                    parts[1] if len(parts) > 1 else '',
                    parts[2] if len(parts) > 2 else '',
                    0,
                    settings_count,
                ],
                'runs': [
                    self._expand_compact_run(run, date) for run in top
                ],
            }
        return {
            'date': date,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'source': 'runs-derived',
            'records': records,
        }

    @staticmethod
    def _expand_compact_run(run: Dict, date: str) -> Dict:
        """Expand a compact timeline run into SRC-like run shape."""
        is_guest = bool(run.get('g')) or str(run.get('p', '')).startswith('guest:')
        name_style = run.get('ns') or {
            'style': 'solid',
            'color': {'dark': '#9e9e9e', 'light': '#9e9e9e'},
        }
        if is_guest:
            player = {
                'rel': 'guest',
                'name': run.get('n'),
                'name-style': name_style,
            }
        else:
            player = {
                'rel': 'user',
                'id': run.get('p'),
                'names': {'international': run.get('n')},
                'weblink': f"https://www.speedrun.com/user/{run.get('p')}",
                'name-style': run.get('ns') or None,
            }
        return {
            'id': run.get('id'),
            'date': date,
            'weblink': run.get('w'),
            'times': {
                'primary': run.get('t'),
                'primary_t': run.get('pt'),
            },
            'players': {'data': [player]},
            'values': {},
        }
    
    async def get_most_recent_date(self) -> Optional[str]:
        """Get the most recent available date from runs-derived metadata"""
        try:
            metadata = self._load_runs_dates()
            if metadata and metadata.get('availableDates'):
                return metadata['availableDates'][-1]
            print('Runs-derived dates metadata not available')
        except Exception as error:
            print(f'Error fetching most recent date: {error}')
        return None
    
    async def is_date_available(self, date: str) -> bool:
        """Check if a specific date is available in runs-derived cache"""
        try:
            dates = await self.get_available_dates()
            return date in dates
        except Exception as error:
            print(f'Error checking date availability: {error}')
            return False
    
    async def fetch_cache_for_date(self, date: str) -> Optional[Dict]:
        """Build a day snapshot from runs-derived WR timelines"""
        try:
            timelines = self._load_timelines()
            if not timelines:
                print(f"WR timelines unavailable; cannot build snapshot for {date}")
                return None
            print(f"Built runs-derived snapshot for {date}")
            return self._build_derived_day(timelines, date)
        except Exception as error:
            print(f"Error building runs-derived cache for {date}: {error}")
            return None
    
    def convert_cache_format(self, github_cache: Dict, target_date: str) -> Optional[Dict]:
        """Convert GitHub cache format to the format expected by the app"""
        if not github_cache or 'records' not in github_cache:
            return None
        
        converted_data = {}
        
        # Convert each record from GitHub format to app format
        for key, record in github_cache['records'].items():
            if record.get('success') and record.get('runs') and isinstance(record['runs'], list):
                # The runs are already in the correct format from our script
                # Just ensure they have the right structure
                converted_runs = []
                for run in record['runs']:
                    # Check if this is already in the correct format
                    if (run.get('players') and run['players'].get('data') and 
                        isinstance(run['players']['data'], list) and len(run['players']['data']) > 0):
                        # Already in correct format, return as is
                        converted_run = {
                            'times': run.get('times', {}),
                            'date': run.get('date', target_date),
                            'id': run.get('id', ''),
                            'weblink': run.get('weblink', ''),
                            'players': run['players'],
                            'values': run.get('values', {})
                        }
                        converted_runs.append(converted_run)
                    else:
                        # Handle legacy format (if any)
                        print(f"Legacy format detected for run {run.get('id', 'unknown')}, skipping")
                
                converted_data[key] = converted_runs
            else:
                # Handle empty results
                converted_data[key] = []
        
        return converted_data
    
    async def fetch_current_world_records(self) -> Optional[Dict]:
        """Fetch world records for current settings (most recent available data)"""
        most_recent_date = await self.get_most_recent_date()
        if not most_recent_date:
            print('No GitHub cache available')
            return None
        
        cache_data = await self.fetch_cache_for_date(most_recent_date)
        if not cache_data:
            print('Failed to fetch GitHub cache')
            return None
        
        return self.convert_cache_format(cache_data, most_recent_date)
    
    async def fetch_world_records_for_date(self, date: str) -> Optional[Dict]:
        """Fetch world records for a specific date"""
        # Don't check metadata - just try to fetch the cache directly
        cache_data = await self.fetch_cache_for_date(date)
        if not cache_data:
            print(f"Failed to fetch GitHub cache for {date}")
            return None
        
        return self.convert_cache_format(cache_data, date)
    
    async def get_available_dates(self) -> List[str]:
        """Get available dates from runs-derived metadata"""
        try:
            metadata = self._load_runs_dates()
            if not metadata:
                return []
            return metadata.get('availableDates', [])
        except Exception as error:
            print(f'Error fetching available dates: {error}')
            return []

    async def get_complete_year_months(self) -> List[str]:
        """Return YYYY-MM months with a full calendar of runs-derived dates.

        Computed on the fly from available-dates-runs.json — no hardcoded month list.
        A month is complete only when every day 1..N is present (so the current
        partial month and any gap months are excluded automatically).
        """
        from calendar import monthrange

        dates = await self.get_available_dates()
        if not dates:
            return []

        days_by_month: Dict[str, set] = {}
        for day in dates:
            if len(day) < 10:
                continue
            ym = day[:7]
            try:
                days_by_month.setdefault(ym, set()).add(int(day[8:10]))
            except ValueError:
                continue

        complete: List[str] = []
        for ym, days in days_by_month.items():
            try:
                year, month = map(int, ym.split('-'))
                expected = monthrange(year, month)[1]
            except ValueError:
                continue
            if set(range(1, expected + 1)).issubset(days):
                complete.append(ym)

        complete.sort(reverse=True)
        return complete

    async def is_year_month_complete(self, year_month: str) -> bool:
        """True if FastSnakeStats currently has every day of YYYY-MM."""
        if not year_month:
            return False
        complete = await self.get_complete_year_months()
        return year_month in complete
    
    async def is_github_cache_available(self) -> bool:
        """Check if runs-derived cache is accessible"""
        try:
            metadata = self._load_runs_dates()
            return bool(metadata and metadata.get('availableDates'))
        except Exception as error:
            print(f'Error checking GitHub cache availability: {error}')
            return False
    
    async def get_cache_stats(self) -> Optional[Dict]:
        """Get cache statistics from runs-derived metadata"""
        try:
            metadata = self._load_runs_dates()
            if not metadata:
                return None

            date_range = metadata.get('dateRange') or {}
            # Normalize earliest/latest (runs-derived) alongside legacy start/end
            normalized_range = {
                'start': date_range.get('start') or date_range.get('earliest'),
                'end': date_range.get('end') or date_range.get('latest'),
                'earliest': date_range.get('earliest') or date_range.get('start'),
                'latest': date_range.get('latest') or date_range.get('end'),
            } if date_range else None

            return {
                'totalDates': metadata.get('totalDates', 0),
                'dateRange': normalized_range,
                'lastUpdated': metadata.get('lastUpdated'),
                'source': metadata.get('source', 'runs-derived'),
            }
        except Exception as error:
            print(f'Error fetching cache stats: {error}')
            return None

    async def fetch_player_stats_metadata(self, force_refresh: bool = False) -> Optional[Dict]:
        """Fetch player peak-stats metadata (cached in memory for 1 hour)."""
        try:
            if (
                not force_refresh
                and self._player_stats_cache is not None
                and self._player_stats_cache_fetched_at is not None
                and (datetime.utcnow() - self._player_stats_cache_fetched_at).total_seconds() < 3600
            ):
                return self._player_stats_cache

            response = requests.get(self.player_stats_url, timeout=20)
            if not response.ok:
                print('Player stats metadata not available')
                return self._player_stats_cache

            metadata = response.json()
            self._player_stats_cache = metadata
            self._player_stats_cache_fetched_at = datetime.utcnow()
            return metadata
        except Exception as error:
            print(f'Error fetching player stats metadata: {error}')
            return self._player_stats_cache

    async def search_player_names(self, query: str, limit: int = 25) -> List[str]:
        """Player names from player-stats.json (startswith, then contains)."""
        metadata = await self.fetch_player_stats_metadata()
        if not metadata or not metadata.get('players'):
            return []

        players = [p for p in metadata['players'] if p.get('name')]
        needle = (query or '').lower().strip()
        if needle:
            players = [
                p for p in players if needle in (p.get('name') or '').lower()
            ]
            players.sort(
                key=lambda p: (
                    0 if (p.get('name') or '').lower().startswith(needle) else 1,
                    -(p.get('totalRecords') or 0),
                    (p.get('name') or '').lower(),
                )
            )
        else:
            players.sort(
                key=lambda p: (-(p.get('totalRecords') or 0), (p.get('name') or '').lower())
            )

        names: List[str] = []
        seen = set()
        for player in players:
            name = player.get('name') or ''
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(name)
            if len(names) >= limit:
                break
        return names

    async def get_player_peak_stats(self, player_name: str) -> Optional[Dict]:
        """Look up peak records / peak percentage for a player (case-insensitive)."""
        metadata = await self.fetch_player_stats_metadata()
        if not metadata or not metadata.get('players'):
            return None

        needle = player_name.lower().strip()
        for player in metadata['players']:
            name = player.get('name') or ''
            if name.lower() == needle:
                return {
                    'id': player.get('id'),
                    'name': name,
                    'totalRecords': player.get('totalRecords'),
                    'totalDates': player.get('totalDates'),
                    'peakRecords': player.get('peakRecords'),
                    'peakPercentage': player.get('peakPercentage'),
                    'latest': player.get('latest'),
                    'lastUpdated': metadata.get('lastUpdated'),
                }
        return None

    async def get_player_longevity_best(
        self, player_id: Optional[str] = None, player_name: Optional[str] = None
    ) -> Optional[Dict]:
        """Best all-time and still-standing holds for a player."""
        if not player_id and not player_name:
            return None

        career = await self.get_player_career(player_id=player_id, player_name=player_name)
        if career and (career.get('bestAll') or career.get('bestStanding')):
            return {
                'allTime': career.get('bestAll'),
                'standing': career.get('bestStanding'),
            }

        explorer = await self.fetch_statistics_explorer()
        if not explorer:
            return None

        progression = explorer.get('progression') or {}
        latest = ((explorer.get('meta') or {}).get('dateRange') or {}).get('latest')
        if not latest:
            latest = datetime.utcnow().strftime('%Y-%m-%d')

        name_lower = (player_name or '').lower().strip()
        best_all = None
        best_standing = None

        for category, flips in progression.items():
            if not flips:
                continue
            for i, flip in enumerate(flips):
                fid = flip.get('i')
                fname = (flip.get('n') or '').lower()
                if player_id and fid == player_id:
                    matched = True
                elif name_lower and fname == name_lower:
                    matched = True
                else:
                    matched = False
                if not matched:
                    continue

                start = flip.get('d')
                if not start:
                    continue
                next_flip = flips[i + 1] if i + 1 < len(flips) else None
                next_date = next_flip.get('d') if next_flip else None
                if next_date:
                    end = next_date
                    still_standing = False
                else:
                    end = latest
                    still_standing = True
                try:
                    days = (
                        datetime.fromisoformat(end).date()
                        - datetime.fromisoformat(start).date()
                    ).days
                except ValueError:
                    continue

                row = {
                    'category': category,
                    'playerId': fid,
                    'playerName': flip.get('n') or player_name or 'Unknown',
                    'time': flip.get('t') or '',
                    'weblink': flip.get('w'),
                    'start': start,
                    'end': end,
                    'days': days,
                    'stillStanding': still_standing,
                }
                if best_all is None or days > best_all['days']:
                    best_all = row
                if still_standing and (best_standing is None or days > best_standing['days']):
                    best_standing = row

        return {'allTime': best_all, 'standing': best_standing}

    async def get_player_career(
        self, player_id: Optional[str] = None, player_name: Optional[str] = None
    ) -> Optional[Dict]:
        """Look up explorer career row for a player (WR-days, holds, best longevity)."""
        if not player_id and not player_name:
            return None
        explorer = await self.fetch_statistics_explorer()
        if not explorer:
            return None
        rows = explorer.get('career') or []
        if not rows:
            return None

        name_lower = (player_name or '').lower().strip()
        for row in rows:
            if player_id and row.get('playerId') == player_id:
                return row
            if name_lower and (row.get('playerName') or '').lower() == name_lower:
                return row
        return None

    async def get_player_improving(
        self, player_id: Optional[str] = None, player_name: Optional[str] = None
    ) -> Optional[Dict[str, Dict]]:
        """Improving deltas for a player across explorer windows."""
        if not player_id and not player_name:
            return None
        explorer = await self.fetch_statistics_explorer()
        if not explorer or not explorer.get('improving'):
            return None

        name_lower = (player_name or '').lower().strip()
        found: Dict[str, Dict] = {}
        for window, rows in (explorer.get('improving') or {}).items():
            for row in rows or []:
                if player_id and row.get('playerId') == player_id:
                    found[window] = row
                    break
                if name_lower and (row.get('playerName') or '').lower() == name_lower:
                    found[window] = row
                    break
        return found or None

    def _load_local_statistics_explorer(self) -> Optional[Dict]:
        """Load sibling FastSnakeStats explorer JSON when present."""
        return self._load_local_json(self._local_statistics_explorer_path)

    def _prefer_explorer_with_career(self, remote: Optional[Dict]) -> Optional[Dict]:
        """Prefer local explorer when it has career data GitHub does not yet."""
        local = self._load_local_statistics_explorer()
        if not local:
            return remote
        local_has_career = bool(local.get('career'))
        remote_has_career = bool(remote and remote.get('career'))
        if local_has_career and not remote_has_career:
            return local
        if not remote:
            return local
        local_ver = ((local.get('meta') or {}).get('analyzerVersion') or 0)
        remote_ver = ((remote.get('meta') or {}).get('analyzerVersion') or 0)
        if local_has_career and local_ver > remote_ver:
            return local
        return remote

    async def fetch_statistics_explorer(self, force_refresh: bool = False) -> Optional[Dict]:
        """Fetch statistics-explorer metadata (cached in memory for 1 hour)."""
        try:
            if (
                not force_refresh
                and self._statistics_explorer_cache is not None
                and self._statistics_explorer_cache_fetched_at is not None
                and (datetime.utcnow() - self._statistics_explorer_cache_fetched_at).total_seconds() < 3600
            ):
                return self._statistics_explorer_cache

            metadata = None
            response = requests.get(self.statistics_explorer_url, timeout=60)
            if response.ok:
                metadata = response.json()
            else:
                print('Statistics explorer metadata not available from GitHub')

            metadata = self._prefer_explorer_with_career(metadata)
            if metadata is None:
                return self._statistics_explorer_cache

            self._statistics_explorer_cache = metadata
            self._statistics_explorer_cache_fetched_at = datetime.utcnow()
            return metadata
        except Exception as error:
            print(f'Error fetching statistics explorer metadata: {error}')
            local = self._prefer_explorer_with_career(None)
            if local is not None:
                self._statistics_explorer_cache = local
                self._statistics_explorer_cache_fetched_at = datetime.utcnow()
                return local
            return self._statistics_explorer_cache

    async def get_progression(self, settings_key: str) -> Optional[List[Dict]]:
        """Get WR progression timeline for a category key."""
        data = await self.fetch_statistics_explorer()
        if not data or not data.get('progression'):
            return None
        series = data['progression'].get(settings_key)
        return series if series else None

    async def get_longevity(self, mode: str = 'standing') -> Optional[List[Dict]]:
        """Get longevity list (`all` or `standing`)."""
        data = await self.fetch_statistics_explorer()
        if not data or not data.get('longevity'):
            return None
        key = 'standing' if mode == 'standing' else 'all'
        return data['longevity'].get(key) or []

    async def get_improving(self, window: str = '30d') -> Optional[List[Dict]]:
        """Get improving players for a window (`7d`, `30d`, `90d`, `365d`)."""
        data = await self.fetch_statistics_explorer()
        if not data or not data.get('improving'):
            return None
        return data['improving'].get(window) or []

    async def get_contested(self) -> Optional[List[Dict]]:
        """Get most contested categories."""
        data = await self.fetch_statistics_explorer()
        if not data:
            return None
        return data.get('contested') or []

    async def get_popularity(self) -> Optional[List[Dict]]:
        """Get most popular categories by unique holders."""
        data = await self.fetch_statistics_explorer()
        if not data:
            return None
        return data.get('popularity') or []

    async def get_stale(self) -> Optional[List[Dict]]:
        """Get least-flipped / stalest held categories."""
        data = await self.fetch_statistics_explorer()
        if not data:
            return None
        return data.get('stale') or []

    async def get_career(self) -> Optional[List[Dict]]:
        """Get career WR-days leaderboard rows."""
        data = await self.fetch_statistics_explorer()
        if not data:
            return None
        return data.get('career') or []

    async def get_unicorns(self) -> Optional[List[Dict]]:
        """Get Lottery-tier unicorn holds (present and past)."""
        data = await self.fetch_statistics_explorer()
        if not data:
            return None
        return data.get('unicorns') or []

    async def get_legends(self) -> Optional[List[Dict]]:
        """Get Mythic-tier legend holds (present and past)."""
        data = await self.fetch_statistics_explorer()
        if not data:
            return None
        return data.get('legends') or []

    async def get_unheld(self, tier: Optional[str] = None) -> Optional[Dict]:
        """Get never-held categories (optional difficulty tier filter)."""
        data = await self.fetch_statistics_explorer()
        if not data or not data.get('unheld'):
            return None

        unheld = data['unheld']
        rows = list(unheld.get('rows') or [])
        if tier:
            rows = [row for row in rows if (row.get('tier') or '') == tier]

        return {
            'tiers': unheld.get('tiers') or [],
            'total': unheld.get('total', len(unheld.get('rows') or [])),
            'shown': len(rows),
            'tier': tier,
            'rows': rows,
        }

    async def get_activity_heatmap(self) -> Optional[List[Dict]]:
        """Get daily activity heatmap entries."""
        data = await self.fetch_statistics_explorer()
        if not data:
            return None
        return data.get('activityHeatmap') or []

    def _load_local_mastery_challenge(self) -> Optional[Dict]:
        return self._load_local_json(self._local_mastery_challenge_path)

    def _prefer_mastery_challenge(self, remote: Optional[Dict]) -> Optional[Dict]:
        """Prefer local mastery JSON when it is newer than GitHub."""
        local = self._load_local_mastery_challenge()
        if not local:
            return remote
        if not remote:
            return local
        local_updated = ((local.get('meta') or {}).get('lastUpdated') or '')
        remote_updated = ((remote.get('meta') or {}).get('lastUpdated') or '')
        if local_updated and local_updated > remote_updated:
            return local
        local_seen = ((local.get('meta') or {}).get('seenRuns') or 0)
        remote_seen = ((remote.get('meta') or {}).get('seenRuns') or 0)
        if local_seen > remote_seen:
            return local
        return remote

    async def fetch_mastery_challenge(self, force_refresh: bool = False) -> Optional[Dict]:
        """Fetch mastery-challenge metadata (cached in memory for 1 hour)."""
        try:
            if (
                not force_refresh
                and self._mastery_challenge_cache is not None
                and self._mastery_challenge_cache_fetched_at is not None
                and (datetime.utcnow() - self._mastery_challenge_cache_fetched_at).total_seconds() < 3600
            ):
                return self._mastery_challenge_cache

            response = requests.get(self.mastery_challenge_url, timeout=30)
            remote = response.json() if response.ok else None
            if not response.ok:
                print(f'GitHub mastery challenge not available ({response.status_code})')

            data = self._prefer_mastery_challenge(remote)
            if data:
                self._mastery_challenge_cache = data
                self._mastery_challenge_cache_fetched_at = datetime.utcnow()
                return data

            local = self._prefer_mastery_challenge(None)
            if local:
                self._mastery_challenge_cache = local
                self._mastery_challenge_cache_fetched_at = datetime.utcnow()
                return local
            return self._mastery_challenge_cache
        except Exception as error:
            print(f'Error fetching mastery challenge: {error}')
            local = self._prefer_mastery_challenge(None)
            if local:
                self._mastery_challenge_cache = local
                self._mastery_challenge_cache_fetched_at = datetime.utcnow()
                return local
            return self._mastery_challenge_cache

    async def get_mastery_player(
        self, player_id: Optional[str] = None, player_name: Optional[str] = None
    ) -> Optional[Dict]:
        """Look up a player's mastery entry by id or name."""
        data = await self.fetch_mastery_challenge()
        if not data:
            return None
        by_player = data.get('byPlayer') or {}
        if player_id and player_id in by_player:
            entry = dict(by_player[player_id])
            entry['playerId'] = player_id
            return entry
        name_lower = (player_name or '').lower().strip()
        if not name_lower:
            return None
        for pid, entry in by_player.items():
            if (entry.get('playerName') or '').lower() == name_lower:
                out = dict(entry)
                out['playerId'] = pid
                return out
        return None

    def _load_local_chronicle(self) -> Optional[Dict]:
        return self._load_local_json(self._local_chronicle_path)

    def _prefer_chronicle(self, remote: Optional[Dict]) -> Optional[Dict]:
        """Prefer local chronicle JSON when it is newer than GitHub."""
        local = self._load_local_chronicle()
        if not local:
            return remote
        if not remote:
            return local
        local_updated = ((local.get('meta') or {}).get('lastUpdated') or '')
        remote_updated = ((remote.get('meta') or {}).get('lastUpdated') or '')
        if local_updated and local_updated > remote_updated:
            return local
        local_eras = ((local.get('meta') or {}).get('eraCount') or 0)
        remote_eras = ((remote.get('meta') or {}).get('eraCount') or 0)
        if local_eras > remote_eras:
            return local
        return remote

    async def fetch_chronicle(self, force_refresh: bool = False) -> Optional[Dict]:
        """Fetch chronicle metadata (cached in memory for 1 hour)."""
        try:
            if (
                not force_refresh
                and self._chronicle_cache is not None
                and self._chronicle_cache_fetched_at is not None
                and (datetime.utcnow() - self._chronicle_cache_fetched_at).total_seconds() < 3600
            ):
                return self._chronicle_cache

            response = requests.get(self.chronicle_url, timeout=60)
            remote = response.json() if response.ok else None
            if not response.ok:
                print(f'GitHub chronicle not available ({response.status_code})')

            data = self._prefer_chronicle(remote)
            if data:
                self._chronicle_cache = data
                self._chronicle_cache_fetched_at = datetime.utcnow()
                return data

            local = self._prefer_chronicle(None)
            if local:
                self._chronicle_cache = local
                self._chronicle_cache_fetched_at = datetime.utcnow()
                return local
            return self._chronicle_cache
        except Exception as error:
            print(f'Error fetching chronicle: {error}')
            local = self._prefer_chronicle(None)
            if local:
                self._chronicle_cache = local
                self._chronicle_cache_fetched_at = datetime.utcnow()
                return local
            return self._chronicle_cache

    async def get_chronicle_era(self, date: Optional[str] = None) -> Optional[Dict]:
        """Get an era newspaper day (default: latest chronological loud day)."""
        data = await self.fetch_chronicle()
        if not data:
            return None
        eras = list(data.get('eras') or [])
        if not eras:
            return None
        eras_chrono = sorted(eras, key=lambda e: e.get('date') or '')
        if date:
            for era in eras_chrono:
                if era.get('date') == date:
                    return era
            return None
        defaults = (data.get('meta') or {}).get('defaults') or {}
        default_date = defaults.get('eraDate')
        if default_date:
            for era in eras_chrono:
                if era.get('date') == default_date:
                    return era
        return eras_chrono[-1] if eras_chrono else None

    async def get_chronicle_empire(
        self, player_id: Optional[str] = None, player_name: Optional[str] = None
    ) -> Optional[Dict]:
        """Look up a player's empire arc (default: top empire by peak drop)."""
        data = await self.fetch_chronicle()
        if not data:
            return None
        empires = list(data.get('empires') or [])
        if not empires:
            return None
        if player_id:
            for empire in empires:
                if empire.get('id') == player_id:
                    return empire
        name_lower = (player_name or '').lower().strip()
        if name_lower:
            for empire in empires:
                if (empire.get('name') or '').lower() == name_lower:
                    return empire
            return None
        defaults = (data.get('meta') or {}).get('defaults') or {}
        default_id = defaults.get('empireId')
        if default_id:
            for empire in empires:
                if empire.get('id') == default_id:
                    return empire
        return empires[0]

    async def get_chronicle_wars(self) -> Optional[List[Dict]]:
        """Get contested board war reels ranked by flips."""
        data = await self.fetch_chronicle()
        if not data:
            return None
        return list(data.get('wars') or [])

    async def get_chronicle_war(self, category: Optional[str] = None) -> Optional[Dict]:
        """Get one board war (default: top contested / meta default)."""
        wars = await self.get_chronicle_wars()
        if not wars:
            return None
        if category:
            for war in wars:
                if war.get('category') == category:
                    return war
            return None
        data = await self.fetch_chronicle()
        defaults = ((data or {}).get('meta') or {}).get('defaults') or {}
        default_cat = defaults.get('warCategory')
        if default_cat:
            for war in wars:
                if war.get('category') == default_cat:
                    return war
        return wars[0]

    async def get_chronicle_introductions(self) -> Optional[List[Dict]]:
        """First-seen settings (count/speed/size/mode/run) from runs archive."""
        data = await self.fetch_chronicle()
        if not data:
            return None
        return list(data.get('introductions') or [])


# Create global instance
github_cache_fetcher = GitHubCacheFetcher()

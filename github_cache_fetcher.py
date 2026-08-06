import os
import requests
import json
from typing import Optional, Dict, List, Any
from datetime import datetime

class GitHubCacheFetcher:
    """Fetches world records data from GitHub-hosted cache files"""
    
    def __init__(self):
        self.base_url = 'https://raw.githubusercontent.com/DarkSnakeGang/FastSnakeStats/refs/heads/main'
        self.cache_dir = 'daily'
        self.metadata_url = f"{self.base_url}/time-travel-cache/metadata/available-dates.json"
        self.player_stats_url = f"{self.base_url}/time-travel-cache/metadata/player-stats.json"
        self.statistics_explorer_url = f"{self.base_url}/time-travel-cache/metadata/statistics-explorer.json"
        # Sibling FastSnakeStats checkout (analyzer v11+ has career) used when GitHub lags
        self._local_statistics_explorer_path = os.path.normpath(os.path.join(
            os.path.dirname(__file__),
            '..',
            'FastSnakeStats',
            'time-travel-cache',
            'metadata',
            'statistics-explorer.json',
        ))
        self.fallback_to_api = True
        self._player_stats_cache: Optional[Dict] = None
        self._player_stats_cache_fetched_at: Optional[datetime] = None
        self._statistics_explorer_cache: Optional[Dict] = None
        self._statistics_explorer_cache_fetched_at: Optional[datetime] = None
    
    async def get_most_recent_date(self) -> Optional[str]:
        """Get the most recent available date from GitHub"""
        try:
            response = requests.get(self.metadata_url, timeout=10)
            if not response.ok:
                print('GitHub metadata not available (404), GitHub cache not set up yet')
                return None
            
            metadata = response.json()
            if metadata.get('availableDates') and len(metadata['availableDates']) > 0:
                return metadata['availableDates'][-1]
        except Exception as error:
            print(f'Error fetching GitHub metadata: {error}')
        return None
    
    async def is_date_available(self, date: str) -> bool:
        """Check if a specific date is available in GitHub cache"""
        try:
            response = requests.get(self.metadata_url, timeout=10)
            if not response.ok:
                print('GitHub metadata not available (404), cannot check date availability')
                return False
            
            metadata = response.json()
            return metadata.get('availableDates') and date in metadata['availableDates']
        except Exception as error:
            print(f'Error checking date availability: {error}')
            return False
    
    async def fetch_cache_for_date(self, date: str) -> Optional[Dict]:
        """Fetch cache data for a specific date from GitHub"""
        try:
            year, month = date.split('-')[:2]
            cache_url = f"{self.base_url}/time-travel-cache/{self.cache_dir}/{year}/{month}/{date}.json"
            print(f"Fetching GitHub cache for {date}...")
            
            response = requests.get(cache_url, timeout=15)
            if not response.ok:
                print(f"GitHub cache not available for {date}")
                return None
            
            cache_data = response.json()
            print(f"Successfully fetched GitHub cache for {date}")
            return cache_data
        except Exception as error:
            print(f"Error fetching GitHub cache for {date}: {error}")
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
        """Get available dates from GitHub"""
        try:
            response = requests.get(self.metadata_url, timeout=10)
            if not response.ok:
                return []
            
            metadata = response.json()
            return metadata.get('availableDates', [])
        except Exception as error:
            print(f'Error fetching available dates: {error}')
            return []

    async def get_complete_year_months(self) -> List[str]:
        """Return YYYY-MM months with a full calendar of daily cache files.

        Computed on the fly from available-dates.json — no hardcoded month list.
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
        """Check if GitHub cache is accessible"""
        try:
            response = requests.get(self.metadata_url, timeout=10)
            return response.ok
        except Exception as error:
            print(f'Error checking GitHub cache availability: {error}')
            return False
    
    async def get_cache_stats(self) -> Optional[Dict]:
        """Get cache statistics from GitHub"""
        try:
            response = requests.get(self.metadata_url, timeout=10)
            if not response.ok:
                return None
            
            metadata = response.json()
            return {
                'totalDates': metadata.get('totalDates', 0),
                'dateRange': metadata.get('dateRange'),
                'lastUpdated': metadata.get('lastUpdated')
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
        path = self._local_statistics_explorer_path
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                return json.load(handle)
        except Exception as error:
            print(f'Error reading local statistics explorer: {error}')
            return None

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

# Create global instance
github_cache_fetcher = GitHubCacheFetcher()

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
        self.fallback_to_api = True
    
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

# Create global instance
github_cache_fetcher = GitHubCacheFetcher()

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict, List
import asyncio
from datetime import datetime

from github_cache_fetcher import github_cache_fetcher
import data_management as dm

class FastSnakeStats(commands.Cog):
    """FastSnakeStats Discord bot integration"""
    
    def __init__(self, bot):
        self.bot = bot
        self.cache_data = {}
        self.last_cache_update = None
    
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
            
            # Search through all settings for this player
            for settings_key, runs in world_records.items():
                if not runs or len(runs) == 0:
                    continue
                
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
            
            if not player_records:
                return None
            
            # Sort by date (most recent first)
            player_records.sort(key=lambda x: dm.get_run_date(x['run']), reverse=True)
            
            return {
                'player_name': player_name,
                'world_records_held': total_runs,  # Now matches /stats calculation
                'recent_activity': player_records,  # All runs, not just 10
                'date': date or await github_cache_fetcher.get_most_recent_date()
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
    
    def get_random_combination(self) -> Dict[str, str]:
        """Generate a random combination of game settings"""
        import random
        
        # Get all available options
        apple_amounts = list(dm.APPLE_AMOUNTS.keys())
        speeds = list(dm.SPEEDS.keys())
        sizes = list(dm.SIZES.keys())
        gamemodes = list(dm.GAMEMODES.keys())
        run_modes = list(dm.RUN_MODES.keys())
        
        # Generate random combination
        combination = {
            'game_mode': random.choice(gamemodes),
            'apple_amount': random.choice(apple_amounts),
            'speed': random.choice(speeds),
            'size': random.choice(sizes),
            'run_mode': random.choice(run_modes)
        }
        
        return combination
    
    def create_record_embed(self, record_data: Dict, settings_key: str) -> discord.Embed:
        """Create a rich embed for record display"""
        run = record_data['run']
        settings_parts = settings_key.split('|')
        
        embed = discord.Embed(
            title=f"🏆 World Record - {' | '.join(settings_parts[:4])}",
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
    
    def create_player_embed(self, player_data: Dict, page: int = 0) -> discord.Embed:
        """Create a rich embed for player display with pagination"""
        embed = discord.Embed(
            title=f"👤 Player Profile - {player_data['player_name']}",
            color=0x0099ff,  # Blue for player profiles
            timestamp=datetime.now()
        )
        
        # Add statistics fields
        embed.add_field(
            name="📊 Statistics",
            value=f"**World Records:** {player_data['world_records_held']}",
            inline=False
        )
        
        # Add recent activity with pagination
        if player_data['recent_activity']:
            runs_per_page = 5
            start_idx = page * runs_per_page
            end_idx = start_idx + runs_per_page
            page_runs = player_data['recent_activity'][start_idx:end_idx]
            
            recent_text = ""
            for i, record in enumerate(page_runs, start_idx + 1):
                settings_parts = record['settings'].split('|')
                
                # Full category details
                apple_amount = settings_parts[0]
                speed = settings_parts[1]
                size = settings_parts[2]
                gamemode = settings_parts[3]
                run_mode = settings_parts[4]
                
                category_info = f"{gamemode} • {apple_amount} • {speed} • {size} • {run_mode}"
                
                # Handle High Score mode display
                if run_mode == "High Score":
                    time_str = dm.get_run_time(record['run'])
                    # Check for both old format (0m 0s Xms) and new format (Xs Yms)
                    if time_str.startswith("0m 0s ") or (time_str.endswith("ms") and "m " not in time_str and "h " not in time_str):
                        # Extract the milliseconds part for High Score
                        if time_str.startswith("0m 0s "):
                            score = time_str.replace("0m 0s ", "").replace("ms", "")
                        else:
                            # New format: "Xs Yms" -> extract Y
                            score = time_str.split("s ")[1].replace("ms", "")
                        display_info = f"{score} apples"
                    else:
                        display_info = time_str
                else:
                    display_info = dm.get_run_time(record['run'])
                
                date = dm.get_run_date(record['run'])
                run_link = dm.get_run_link(record['run'])
                
                if run_link:
                    recent_text += f"{i}. **{category_info}**\n   {display_info} • {date} • [View Run]({run_link})\n\n"
                else:
                    recent_text += f"{i}. **{category_info}**\n   {display_info} • {date}\n\n"
            
            if not recent_text:
                recent_text = "No more runs to show."
            
            embed.add_field(
                name="🕒 Recent Activity",
                value=recent_text,
                inline=False
            )
        
        # Add footer with page info
        total_pages = (len(player_data['recent_activity']) + 4) // 5  # 5 runs per page
        embed.set_footer(text=f"Data from FastSnakeStats • {player_data['date']} • Page {page + 1}/{total_pages}")
        
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
                category_info = f"{settings_parts[3]} • {settings_parts[0]} • {settings_parts[1]} • {settings_parts[2]} • {run_mode}"
                
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
    
    @app_commands.command(name="record", description="Get world record for specific settings")
    @app_commands.describe(
        game_mode="Game mode (Classic, Wall, Portal, etc.)",
        apple_amount="Number of apples",
        speed="Game speed",
        size="Game size",
        run_mode="Run mode (25 Apples, 50 Apples, etc.)",
        date="Historical date - optional"
    )
    @app_commands.autocomplete(date=record_date_autocomplete)
    @app_commands.choices(
        game_mode=[
            app_commands.Choice(name="Classic", value="Classic"),
            app_commands.Choice(name="Wall", value="Wall"),
            app_commands.Choice(name="Portal", value="Portal"),
            app_commands.Choice(name="Cheese", value="Cheese"),
            app_commands.Choice(name="Borderless", value="Borderless"),
            app_commands.Choice(name="Twin", value="Twin"),
            app_commands.Choice(name="Winged", value="Winged"),
            app_commands.Choice(name="Yin Yang", value="Yin Yang"),
            app_commands.Choice(name="Key", value="Key"),
            app_commands.Choice(name="Sokoban", value="Sokoban"),
            app_commands.Choice(name="Poison", value="Poison"),
            app_commands.Choice(name="Dimension", value="Dimension"),
            app_commands.Choice(name="Minesweeper", value="Minesweeper"),
            app_commands.Choice(name="Statue", value="Statue"),
            app_commands.Choice(name="Light", value="Light"),
            app_commands.Choice(name="Shield", value="Shield"),
            app_commands.Choice(name="Arrow", value="Arrow"),
            app_commands.Choice(name="Hotdog", value="Hotdog"),
            app_commands.Choice(name="Magnet", value="Magnet"),
            app_commands.Choice(name="Gate", value="Gate"),
            app_commands.Choice(name="Peaceful", value="Peaceful")
        ],
        apple_amount=[
            app_commands.Choice(name="1 Apple", value="1 Apple"),
            app_commands.Choice(name="3 Apples", value="3 Apples"),
            app_commands.Choice(name="5 Apples", value="5 Apples"),
            app_commands.Choice(name="Dice", value="Dice")
        ],
        speed=[
            app_commands.Choice(name="Normal", value="Normal"),
            app_commands.Choice(name="Slow", value="Slow"),
            app_commands.Choice(name="Fast", value="Fast")
        ],
        size=[
            app_commands.Choice(name="Standard", value="Standard"),
            app_commands.Choice(name="Small", value="Small"),
            app_commands.Choice(name="Large", value="Large")
        ],
        run_mode=[
            app_commands.Choice(name="25 Apples", value="25 Apples"),
            app_commands.Choice(name="50 Apples", value="50 Apples"),
            app_commands.Choice(name="100 Apples", value="100 Apples"),
            app_commands.Choice(name="All Apples", value="All Apples"),
            app_commands.Choice(name="High Score", value="High Score")
        ]
    )
    async def record_command(self, interaction: discord.Interaction, game_mode: str, apple_amount: str, speed: str, size: str, run_mode: str, date: Optional[str] = None):
        """Get world record for specific settings"""
        await interaction.response.defer()
        
        try:
            # Get record data
            record_data = await self.get_record_data(apple_amount, speed, size, game_mode, date, run_mode)
            
            if not record_data:
                if date:
                    await interaction.followup.send(f"❌ No data available for date: {date}. Use `/available-dates` to see working dates.")
                else:
                    settings_key = dm.get_settings_key(apple_amount, speed, size, game_mode, run_mode)
                    await interaction.followup.send(f"❌ No record found for: {settings_key}")
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
                embed.add_field(
                    name="Date Range",
                    value=f"{date_range.get('start', 'N/A')} to {date_range.get('end', 'N/A')}",
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
    
    @app_commands.command(name="player", description="Get player statistics and recent activity")
    @app_commands.describe(
        player_name="Player name to look up",
        date="Historical date - optional"
    )
    @app_commands.autocomplete(date=player_date_autocomplete)
    async def player_command(self, interaction: discord.Interaction, player_name: str, date: Optional[str] = None):
        """Get player statistics and recent activity"""
        await interaction.response.defer()
        
        try:
            # Get player data
            player_data = await self.get_player_data(player_name, date)
            
            if not player_data:
                if date:
                    await interaction.followup.send(f"❌ No data available for date: {date}. Use `/available-dates` to see working dates.")
                else:
                    await interaction.followup.send(f"❌ No data found for player: {player_name}")
                return
            
            # Create embed with pagination
            embed = self.create_player_embed(player_data, page=0)
            
            # Create view with pagination buttons (only if multiple pages)
            total_pages = (len(player_data['recent_activity']) + 4) // 5  # 5 runs per page
            if total_pages > 1:
                view = PlayerPaginationView(player_data, interaction.user.id)
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
    
    @app_commands.command(name="random", description="Get a random combination of game settings to try")
    async def random_command(self, interaction: discord.Interaction):
        """Get a random combination of game settings"""
        await interaction.response.defer()
        
        try:
            # Generate random combination
            combination = self.get_random_combination()
            
            # Create embed
            embed = discord.Embed(
                title="🎲 Random Challenge",
                description="Here's a random combination to try!",
                color=0x9b59b6,  # Purple for random
                timestamp=datetime.now()
            )
            
            # Add the combination details
            embed.add_field(
                name="🎮 Game Mode",
                value=combination['game_mode'],
                inline=True
            )
            
            embed.add_field(
                name="🍎 Apple Amount",
                value=combination['apple_amount'],
                inline=True
            )
            
            embed.add_field(
                name="⚡ Speed",
                value=combination['speed'],
                inline=True
            )
            
            embed.add_field(
                name="📏 Size",
                value=combination['size'],
                inline=True
            )
            
            embed.add_field(
                name="🎯 Run Mode",
                value=combination['run_mode'],
                inline=True
            )
            
            embed.set_footer(text="Try this combination and see how you do!")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in random command: {e}")
            await interaction.followup.send("❌ An error occurred while generating random combination. Please try again.")
    
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
    """View for paginating through player results"""
    
    def __init__(self, player_data: Dict, user_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.player_data = player_data
        self.user_id = user_id
        self.current_page = 0
        self.runs_per_page = 5
        self.total_pages = (len(player_data['recent_activity']) + self.runs_per_page - 1) // self.runs_per_page
    
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
        embed = self.create_player_embed(self.player_data, self.current_page)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_player_embed(self, player_data: Dict, page: int = 0) -> discord.Embed:
        """Create a rich embed for player display with pagination"""
        embed = discord.Embed(
            title=f"👤 Player Profile - {player_data['player_name']}",
            color=0x0099ff,  # Blue for player profiles
            timestamp=datetime.now()
        )
        
        # Add statistics fields
        embed.add_field(
            name="📊 Statistics",
            value=f"**World Records:** {player_data['world_records_held']}",
            inline=False
        )
        
        # Add recent activity with pagination
        if player_data['recent_activity']:
            start_idx = page * self.runs_per_page
            end_idx = start_idx + self.runs_per_page
            page_runs = player_data['recent_activity'][start_idx:end_idx]
            
            recent_text = ""
            for i, record in enumerate(page_runs, start_idx + 1):
                settings_parts = record['settings'].split('|')
                
                # Full category details
                apple_amount = settings_parts[0]
                speed = settings_parts[1]
                size = settings_parts[2]
                gamemode = settings_parts[3]
                run_mode = settings_parts[4]
                
                category_info = f"{gamemode} • {apple_amount} • {speed} • {size} • {run_mode}"
                
                # Handle High Score mode display
                if run_mode == "High Score":
                    time_str = dm.get_run_time(record['run'])
                    # Check for both old format (0m 0s Xms) and new format (Xs Yms)
                    if time_str.startswith("0m 0s ") or (time_str.endswith("ms") and "m " not in time_str and "h " not in time_str):
                        # Extract the milliseconds part for High Score
                        if time_str.startswith("0m 0s "):
                            score = time_str.replace("0m 0s ", "").replace("ms", "")
                        else:
                            # New format: "Xs Yms" -> extract Y
                            score = time_str.split("s ")[1].replace("ms", "")
                        display_info = f"{score} apples"
                    else:
                        display_info = time_str
                else:
                    display_info = dm.get_run_time(record['run'])
                
                date = dm.get_run_date(record['run'])
                run_link = dm.get_run_link(record['run'])
                
                if run_link:
                    recent_text += f"{i}. **{category_info}**\n   {display_info} • {date} • [View Run]({run_link})\n\n"
                else:
                    recent_text += f"{i}. **{category_info}**\n   {display_info} • {date}\n\n"
            
            if not recent_text:
                recent_text = "No more runs to show."
            
            embed.add_field(
                name="🕒 Recent Activity",
                value=recent_text,
                inline=False
            )
        
        # Add footer with page info
        embed.set_footer(text=f"Data from FastSnakeStats • {player_data['date']} • Page {page + 1}/{self.total_pages}")
        
        return embed

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
                category_info = f"{settings_parts[3]} • {settings_parts[0]} • {settings_parts[1]} • {settings_parts[2]} • {run_mode}"
                
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

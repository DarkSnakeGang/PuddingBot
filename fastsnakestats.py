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
            world_records_held = 0
            
            # Search through all settings for this player
            for settings_key, runs in world_records.items():
                if not runs or len(runs) == 0:
                    continue
                
                # Check if player holds the world record (first run)
                best_run = runs[0]
                if dm.get_player_name(best_run).lower() == player_name_lower:
                    world_records_held += 1
                    player_records.append({
                        'run': best_run,
                        'settings': settings_key,
                        'rank': 1
                    })
            
            if not player_records:
                return None
            
            # Sort by date (most recent first)
            player_records.sort(key=lambda x: dm.get_run_date(x['run']), reverse=True)
            
            return {
                'player_name': player_name,
                'world_records_held': world_records_held,
                'recent_activity': player_records[:10],  # Last 10 runs
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
            
            # Count total world records
            total_world_records = 0
            player_records = {}
            
            # Count world records per player
            for settings_key, runs in world_records.items():
                if not runs or len(runs) == 0:
                    continue
                
                # Only count if there's a valid world record
                best_run = runs[0]
                if best_run and dm.get_player_name(best_run):
                    total_world_records += 1
                    player_name = dm.get_player_name(best_run)
                    
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
                'top_by_number': sorted_by_number[:10],  # Top 10 by number
                'top_by_percentage': sorted_by_percentage[:10],  # Top 10 by percentage
                'date': date or await github_cache_fetcher.get_most_recent_date()
            }
            
        except Exception as e:
            print(f"Error getting stats data: {e}")
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
    
    def create_player_embed(self, player_data: Dict) -> discord.Embed:
        """Create a rich embed for player display"""
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
        
        # Add recent activity
        if player_data['recent_activity']:
            recent_text = ""
            for i, record in enumerate(player_data['recent_activity'][:5], 1):  # Show last 5 runs
                settings_parts = record['settings'].split('|')
                mode_info = f"{settings_parts[3]} {settings_parts[4]}"  # gamemode + run_mode
                
                # Handle High Score mode display
                if settings_parts[4] == "High Score":
                    # Extract score from time field for High Score mode
                    time_str = dm.get_run_time(record['run'])
                    if time_str.startswith("0:00:"):
                        score = time_str.replace("0:00:", "")
                        display_info = f"{score} apples"
                    else:
                        display_info = time_str
                else:
                    display_info = dm.get_run_time(record['run'])
                
                date = dm.get_run_date(record['run'])
                recent_text += f"{i}. **{mode_info}** - {display_info} ({date})\n"
            
            embed.add_field(
                name="🕒 Recent Activity",
                value=recent_text or "No recent activity",
                inline=False
            )
        
        # Add footer
        embed.set_footer(text=f"Data from FastSnakeStats • {player_data['date']}")
        
        return embed
    
    def create_stats_embed(self, stats_data: Dict) -> discord.Embed:
        """Create a rich embed for stats display"""
        embed = discord.Embed(
            title="📊 Top Record Holders",
            color=0xff9900,  # Orange for statistics
            timestamp=datetime.now()
        )
        
        # Add total world records
        embed.add_field(
            name="📈 Total World Records",
            value=str(stats_data['total_world_records']),
            inline=False
        )
        
        # Add top by number
        top_by_number_text = ""
        for i, (player, count) in enumerate(stats_data['top_by_number'], 1):
            percentage = (count / stats_data['total_world_records']) * 100
            top_by_number_text += f"{i}. **{player}** - {count} records ({percentage:.1f}%)\n"
        
        embed.add_field(
            name="🥇 Most Records (by number)",
            value=top_by_number_text,
            inline=False
        )
        
        # Add top by percentage
        top_by_percentage_text = ""
        for i, (player, count) in enumerate(stats_data['top_by_percentage'], 1):
            percentage = (count / stats_data['total_world_records']) * 100
            top_by_percentage_text += f"{i}. **{player}** - {percentage:.1f}% ({count} records)\n"
        
        embed.add_field(
            name="📊 Most Records (by percentage)",
            value=top_by_percentage_text,
            inline=False
        )
        
        # Add footer
        embed.set_footer(text=f"Data from FastSnakeStats • {stats_data['date']}")
        
        return embed
    
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
            
            # Create embed
            embed = self.create_player_embed(player_data)
            
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
            
            # Create embed
            embed = self.create_stats_embed(stats_data)
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in stats command: {e}")
            await interaction.followup.send("❌ An error occurred while fetching statistics. Please try again.")

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(FastSnakeStats(bot))

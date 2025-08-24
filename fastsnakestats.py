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
    
    @app_commands.command(name="record", description="Get world record for specific settings")
    @app_commands.describe(
        game_mode="Game mode (Classic, Wall, Portal, etc.)",
        apple_amount="Number of apples",
        speed="Game speed",
        size="Game size",
        run_mode="Run mode (25 Apples, 50 Apples, etc.)",
        date="Historical date (YYYY-MM-DD) - optional"
    )
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
            # Validate date format if provided
            if date:
                try:
                    datetime.strptime(date, "%Y-%m-%d")
                except ValueError:
                    await interaction.followup.send("❌ Invalid date format. Please use YYYY-MM-DD format.")
                    return
            
            # Get record data
            record_data = await self.get_record_data(apple_amount, speed, size, game_mode, date, run_mode)
            
            if not record_data:
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

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(FastSnakeStats(bot))

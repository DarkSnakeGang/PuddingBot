from typing import Final, Optional, List
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from discord import Intents, Message, Object, NotFound, Forbidden, HTTPException
from discord.ext import commands
from responses import get_response, is_allowed_poi_message
import asyncio

# Load Token
load_dotenv()
TOKEN: Final[Optional[str]] = os.getenv('DISCORD_TOKEN')
GUILD_ID: Final[Optional[str]] = os.getenv('DISCORD_GUILD_ID')
POI_CHANNEL_NAME: Final[str] = os.getenv('POI_CHANNEL_NAME', 'poi-🐡')

if not TOKEN:
    raise SystemExit(
        "DISCORD_TOKEN is missing. Put it in .env and restart the container "
        "with --env-file .env (see run_docker.sh)."
    )

# Setup Bot with commands framework
intents: Intents = Intents.default()
intents.message_content = True
intents.messages = True  # Enable message intents
bot = commands.Bot(command_prefix='!', intents=intents)

# Message stuff
async def send_message(message: Message, user_message: str, user="Nobody") -> None:
    if not user_message:
        print('Empty message')
        return

    if is_private := user_message[0] == '?':
        user_message = user_message[1]

    try:
        response: str = get_response(user_message, user)
        if response:
            print("[PuddingBot]: " + response)
            await message.author.send(response) if is_private else await message.channel.send(response)
    except Exception as e:
        print(e)

# Startup for the bot
@bot.event
async def on_ready() -> None:
    print(f'{bot.user} is now running')

    # Sync slash commands (guild sync is instant; global sync can take up to an hour)
    try:
        if GUILD_ID:
            guild = Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced)} guild command(s) to guild {GUILD_ID}")
        else:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} global command(s)")
        print("Commands:", ", ".join(f"/{cmd.name}" for cmd in synced))
    except Exception as e:
        print(f"Error syncing commands: {e}")

@bot.event
async def on_message(message: Message) -> None:
    if message.author == bot.user:
        return

    username: str = str(message.author)
    user_message: str = message.content
    channel: str = str(message.channel)

    print(f'[{channel}] {username}: "{user_message}"')
    if channel == POI_CHANNEL_NAME:
        await purge_non_poi_messages(message.channel)
    elif channel == "Direct Message with Unknown User":
        return

    if not (user_message.lower()[:3] == 'gif' and channel == POI_CHANNEL_NAME):
        await send_message(message, user_message, message.author.id)

    await bot.process_commands(message)

def _is_bulk_deletable(message: Message) -> bool:
    """Discord only allows bulk delete for messages younger than 14 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    created = message.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created > cutoff

async def purge_non_poi_messages(channel, limit: int = 1000) -> None:
    """Delete everything in the poi channel that is not exactly the current poi emoji."""
    if channel is None:
        return

    messages_to_delete: List[Message] = []
    try:
        async for message in channel.history(limit=limit):
            allowed = is_allowed_poi_message(message.content) and not message.attachments
            if not allowed:
                messages_to_delete.append(message)
    except Forbidden:
        print(f"Missing permission to read history in #{channel}")
        return
    except Exception as e:
        print(f"Error reading #{channel} history: {e}")
        return

    if not messages_to_delete:
        print(f"No non-poi messages to delete in #{channel}")
        return

    recent = [m for m in messages_to_delete if _is_bulk_deletable(m)]
    old = [m for m in messages_to_delete if not _is_bulk_deletable(m)]
    deleted = 0

    # Bulk delete recent messages in chunks of 100
    for i in range(0, len(recent), 100):
        chunk = recent[i:i + 100]
        try:
            if len(chunk) == 1:
                await chunk[0].delete()
            else:
                await channel.delete_messages(chunk)
            deleted += len(chunk)
        except Forbidden:
            print(f"Missing Manage Messages permission in #{channel}")
            return
        except HTTPException as e:
            print(f"Bulk delete failed, falling back to single deletes: {e}")
            for msg in chunk:
                try:
                    await msg.delete()
                    deleted += 1
                except (NotFound, Forbidden, HTTPException) as err:
                    print(f"Could not delete message {msg.id}: {err}")

    # Older than 14 days must be deleted one-by-one
    for msg in old:
        try:
            await msg.delete()
            deleted += 1
            await asyncio.sleep(0.35)  # stay under rate limits
        except NotFound:
            continue
        except Forbidden:
            print(f"Missing Manage Messages permission in #{channel}")
            return
        except HTTPException as e:
            print(f"Could not delete message {msg.id}: {e}")

    print(f"Deleted {deleted} non-poi message(s) in #{channel}")

async def load_extensions():
    """Load all cogs"""
    for extension in ('admin', 'fastsnakestats'):
        try:
            await bot.load_extension(extension)
            print(f"Loaded {extension} cog successfully")
        except Exception as e:
            print(f"Error loading {extension} cog: {e}")

# Main entry point
async def main() -> None:
    async with bot:
        await load_extensions()
        await bot.start(token=TOKEN)

if __name__ == '__main__':
    asyncio.run(main())

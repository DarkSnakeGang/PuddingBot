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

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if value is None:
        return None
    # Docker --env-file keeps surrounding quotes; strip them
    return value.strip().strip('"').strip("'")

TOKEN: Final[Optional[str]] = _env('DISCORD_TOKEN')
GUILD_ID: Final[Optional[str]] = _env('DISCORD_GUILD_ID')
POI_CHANNEL_NAME: Final[str] = _env('POI_CHANNEL_NAME', 'poi-🐡') or 'poi-🐡'
POI_CHANNEL_ID: Final[Optional[str]] = _env('POI_CHANNEL_ID', '1284209751952986223')

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

_poi_purge_lock: Optional[asyncio.Lock] = None

def _get_poi_purge_lock() -> asyncio.Lock:
    global _poi_purge_lock
    if _poi_purge_lock is None:
        _poi_purge_lock = asyncio.Lock()
    return _poi_purge_lock

def is_poi_channel(channel) -> bool:
    if channel is None:
        return False
    if POI_CHANNEL_ID and str(getattr(channel, 'id', '')) == str(POI_CHANNEL_ID):
        return True
    return str(channel) == POI_CHANNEL_NAME

# Message stuff
async def send_message(message: Message, user_message: str, user="Nobody") -> None:
    if not user_message:
        print('Empty message')
        return

    if is_private := user_message[0] == '?':
        user_message = user_message[1]

    try:
        loop = asyncio.get_running_loop()
        target = message.author if is_private else message.channel

        def status_notify(text: str) -> None:
            asyncio.run_coroutine_threadsafe(target.send(text), loop)

        # Run sync AI / response logic off the event loop so status messages can send
        response: str = await asyncio.to_thread(
            get_response, user_message, user, status_notify
        )
        if response:
            print("[PuddingBot]: " + response)
            await target.send(response)
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
    in_poi = is_poi_channel(message.channel)

    print(f'[{channel}] {username}: "{user_message}"')
    if in_poi:
        # Reply first, purge in background so old-message cleanup doesn't block poi replies
        lock = _get_poi_purge_lock()
        if not lock.locked():
            asyncio.create_task(purge_non_poi_messages(message.channel))
    elif channel == "Direct Message with Unknown User":
        return

    if not (user_message.lower()[:3] == 'gif' and in_poi):
        await send_message(message, user_message, message.author.id)

    await bot.process_commands(message)

def _is_bulk_deletable(message: Message) -> bool:
    """Discord only allows bulk delete for messages younger than 14 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=13, hours=23)
    created = message.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created > cutoff

async def _delete_one(msg: Message) -> bool:
    try:
        await msg.delete()
        return True
    except NotFound:
        return False
    except Forbidden:
        raise
    except HTTPException as e:
        print(f"Could not delete message {msg.id}: {e}")
        return False

async def purge_non_poi_messages(channel) -> None:
    """
    Only for the poi channel: delete every message that is not exactly the
    current poi emoji. Messages older than 14 days are deleted one-by-one
    (Discord bulk-delete limit); newer ones are bulk-deleted.
    """
    if not is_poi_channel(channel):
        return

    async with _get_poi_purge_lock():
        messages_to_delete: List[Message] = []
        try:
            # limit=None scans the entire channel history
            async for message in channel.history(limit=None):
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

        print(f"Purging {len(messages_to_delete)} non-poi message(s) in #{channel}...")
        recent = [m for m in messages_to_delete if _is_bulk_deletable(m)]
        old = [m for m in messages_to_delete if not _is_bulk_deletable(m)]
        deleted = 0

        for i in range(0, len(recent), 100):
            chunk = recent[i:i + 100]
            try:
                if len(chunk) == 1:
                    if await _delete_one(chunk[0]):
                        deleted += 1
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
                        if await _delete_one(msg):
                            deleted += 1
                    except Forbidden:
                        print(f"Missing Manage Messages permission in #{channel}")
                        return

        for msg in old:
            try:
                if await _delete_one(msg):
                    deleted += 1
                await asyncio.sleep(0.4)
            except Forbidden:
                print(f"Missing Manage Messages permission in #{channel}")
                return

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

from typing import Final, Optional, List
import os
import random
import re
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import discord
from discord import Intents, Message, Object, NotFound, Forbidden, HTTPException, File
from discord.ext import commands
from responses import get_response, is_allowed_poi_message
import data_management as dm
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
SIXTY_SEVEN_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'sixty_seven.png')
END_CAREER_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'end_career.png')
WALL_ALL_TRIGGERS: Final[tuple] = (
    'wall all mainboard',
    'wall all normal size',
    'wall all large',
)
OFF_WORK_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'off_work.gif')
GOING_FOR_TRIGGERS: Final[tuple] = (
    'im going for classic 25',
    "i'm going for classic 25",
    'im going for wall 25',
    "i'm going for wall 25",
    'im going for classic 50',
    "i'm going for classic 50",
    'im going for borderless 50',
    "i'm going for borderless 50",
)
WAIT_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'wait.gif')
BAD_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'bad.gif')
SOKOBAN_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'sokoban.gif')
PATTERN_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'pattern.gif')
COUNT_COUNT_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'count_count.gif')
POISON_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'poison.png')
YIN_YANG_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'yin_yang.png')
TALLY_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'tally.gif')
SOFTLOCK_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'softlock.gif')
BAD_RNG_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'bad_rng.png')
# Always-fire phrase
BAD_RNG_ALWAYS_RE: Final[re.Pattern[str]] = re.compile(r"\bbs\s+rng\b", re.IGNORECASE)
# Complaints that RNG is bad (not bare "rng")
BAD_RNG_COMPLAINT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"\b(?:bad|awful|terrible|horrible|shit(?:ty)?|trash|garbage|bullshit|bs|cursed|rigged|unfair|worst|stupid|dumb|abysmal|dogshit)\s+rng\b"
    r"|\brng\s+(?:is\s+)?(?:bad|awful|terrible|horrible|shit(?:ty)?|trash|garbage|bullshit|bs|cursed|rigged|unfair|worst|stupid|dumb|ass|abysmal|dogshit|sucks?)\b"
    r"|\bbull\s*shit\s+rng\b"
    r")",
    re.IGNORECASE,
)

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

    # Sync slash/context commands.
    # Global sync publishes the public Commands list (like esmBot's profile).
    # Optional guild sync keeps the same set available instantly in the home server.
    try:
        synced_global = await bot.tree.sync()
        print(f"Synced {len(synced_global)} global command(s)")
        print(
            "Global commands:",
            ", ".join(
                f"/{cmd.name}" if cmd.type is discord.AppCommandType.chat_input else cmd.name
                for cmd in synced_global
            ),
        )

        if GUILD_ID:
            guild = Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced_guild = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced_guild)} guild command(s) to guild {GUILD_ID}")

            live_guild = bot.get_guild(int(GUILD_ID))
            if live_guild is not None:
                mapped = dm.refresh_emoji_map_from_guild(live_guild)
                print(f"Mapped {mapped} setting icon emoji(s) from guild {GUILD_ID}")
            else:
                print(f"Guild {GUILD_ID} not available yet for emoji mapping")
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

    # 1/67 easter egg when a message contains "67"
    if "67" in user_message and random.randint(1, 67) == 1 and os.path.isfile(SIXTY_SEVEN_ASSET):
        try:
            await message.channel.send(file=File(SIXTY_SEVEN_ASSET, filename="67.png"))
        except Exception as e:
            print(f"Failed to send 67 meme: {e}")

    # 1/16 easter egg for wall-all category mentions
    lowered_message = user_message.lower()
    if (
        any(trigger in lowered_message for trigger in WALL_ALL_TRIGGERS)
        and random.randint(1, 16) == 1
        and os.path.isfile(END_CAREER_ASSET)
    ):
        try:
            await message.channel.send(file=File(END_CAREER_ASSET, filename="end_career.png"))
        except Exception as e:
            print(f"Failed to send wall-all meme: {e}")

    # 1/4 easter egg for "im going for ..." grind announcements
    if (
        any(trigger in lowered_message for trigger in GOING_FOR_TRIGGERS)
        and random.randint(1, 4) == 1
        and os.path.isfile(OFF_WORK_ASSET)
    ):
        try:
            await message.channel.send(file=File(OFF_WORK_ASSET, filename="off_work.gif"))
        except Exception as e:
            print(f"Failed to send going-for meme: {e}")

    # 1/100 easter egg when someone says "wait"
    if (
        re.search(r"\bwait\b", lowered_message)
        and random.randint(1, 100) == 1
        and os.path.isfile(WAIT_ASSET)
    ):
        try:
            await message.channel.send(file=File(WAIT_ASSET, filename="wait.gif"))
        except Exception as e:
            print(f"Failed to send wait meme: {e}")

    # 1/100 easter egg when someone says "bad"
    if (
        re.search(r"\bbad\b", lowered_message)
        and random.randint(1, 100) == 1
        and os.path.isfile(BAD_ASSET)
    ):
        try:
            await message.channel.send(file=File(BAD_ASSET, filename="bad.gif"))
        except Exception as e:
            print(f"Failed to send bad meme: {e}")

    # 1/256 easter egg when sokoban is mentioned
    if (
        re.search(r"\bsokoban\b", lowered_message)
        and random.randint(1, 256) == 1
        and os.path.isfile(SOKOBAN_ASSET)
    ):
        try:
            await message.channel.send(file=File(SOKOBAN_ASSET, filename="sokoban.gif"))
        except Exception as e:
            print(f"Failed to send sokoban meme: {e}")

    # 1/16 easter egg when pattern is mentioned
    if (
        re.search(r"\bpattern\b", lowered_message)
        and random.randint(1, 16) == 1
        and os.path.isfile(PATTERN_ASSET)
    ):
        try:
            await message.channel.send(file=File(PATTERN_ASSET, filename="pattern.gif"))
        except Exception as e:
            print(f"Failed to send pattern meme: {e}")

    # 1/5 easter egg when someone says "count count"
    if (
        "count count" in lowered_message
        and random.randint(1, 5) == 1
        and os.path.isfile(COUNT_COUNT_ASSET)
    ):
        try:
            await message.channel.send(file=File(COUNT_COUNT_ASSET, filename="count_count.gif"))
        except Exception as e:
            print(f"Failed to send count count meme: {e}")

    # 1/6 easter egg when poison is mentioned
    if (
        re.search(r"\bpoison\b", lowered_message)
        and random.randint(1, 6) == 1
        and os.path.isfile(POISON_ASSET)
    ):
        try:
            await message.channel.send(file=File(POISON_ASSET, filename="poison.png"))
        except Exception as e:
            print(f"Failed to send poison meme: {e}")

    # 1/16 easter egg when yin yang is mentioned
    if (
        "yin yang" in lowered_message
        and random.randint(1, 16) == 1
        and os.path.isfile(YIN_YANG_ASSET)
    ):
        try:
            await message.channel.send(file=File(YIN_YANG_ASSET, filename="yin_yang.png"))
        except Exception as e:
            print(f"Failed to send yin yang meme: {e}")

    # 1/5 easter egg when tally is mentioned
    if (
        re.search(r"\btally\b", lowered_message)
        and random.randint(1, 5) == 1
        and os.path.isfile(TALLY_ASSET)
    ):
        try:
            await message.channel.send(file=File(TALLY_ASSET, filename="tally.gif"))
        except Exception as e:
            print(f"Failed to send tally meme: {e}")

    # 1/3 easter egg when softlock is mentioned
    if (
        re.search(r"\bsoftlock\b", lowered_message)
        and random.randint(1, 3) == 1
        and os.path.isfile(SOFTLOCK_ASSET)
    ):
        try:
            await message.channel.send(file=File(SOFTLOCK_ASSET, filename="softlock.gif"))
        except Exception as e:
            print(f"Failed to send softlock meme: {e}")

    # Bad-RNG complaints: always for "bs rng", else 1/3 for similar phrases
    if os.path.isfile(BAD_RNG_ASSET) and (
        BAD_RNG_ALWAYS_RE.search(lowered_message)
        or (
            BAD_RNG_COMPLAINT_RE.search(lowered_message)
            and random.randint(1, 3) == 1
        )
    ):
        try:
            await message.channel.send(file=File(BAD_RNG_ASSET, filename="bad_rng.png"))
        except Exception as e:
            print(f"Failed to send bad rng meme: {e}")

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
    for extension in ('admin', 'fastsnakestats', 'image_tools'):
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

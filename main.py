from typing import Final, Optional, List
import io
import os
import traceback
import random
import re
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import discord
from discord import Intents, Message, Object, NotFound, Forbidden, HTTPException, File
from discord.ext import commands
from chat import get_response, is_allowed_poi_message, mentions_67, parse_how_many_records_player, visible_text
import data_management as dm
import asyncio
import wall
import wall.stream as wall_stream
from wall import PatternResult
from cogs.dm_media import message_has_http_url

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
SIXTY_SEVEN_ASSET: Final[str] = next(
    (
        path
        for path in (
            os.path.join(os.path.dirname(__file__), 'assets', f'sixty_seven.{ext}')
            for ext in ('gif', 'png')
        )
        if os.path.isfile(path)
    ),
    '',
)
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
TALLY_LEARNING_ASSET: Final[str] = os.path.join(os.path.dirname(__file__), 'assets', 'tally_learning.png')
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
        "with --env-file .env (see scripts/run_docker.sh)."
    )

# Setup Bot with commands framework
intents: Intents = Intents.default()
intents.message_content = True
intents.messages = True  # Enable message intents
bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    allowed_mentions=discord.AllowedMentions.none(),
)
_commands_synced = False

_poi_purge_lock: Optional[asyncio.Lock] = None

def _get_poi_purge_lock() -> asyncio.Lock:
    global _poi_purge_lock
    if _poi_purge_lock is None:
        _poi_purge_lock = asyncio.Lock()
    return _poi_purge_lock

def is_poi_channel(channel) -> bool:
    if channel is None:
        return False
    if POI_CHANNEL_ID:
        return str(getattr(channel, 'id', '')) == str(POI_CHANNEL_ID)
    return str(channel) == POI_CHANNEL_NAME

# Message stuff
async def send_message(message: Message, user_message: str, user="Nobody") -> None:
    if not user_message:
        print('Empty message')
        return

    if is_private := user_message[0] == '?':
        user_message = user_message[1:].strip()
        if not user_message:
            return

    try:
        loop = asyncio.get_running_loop()
        target = message.author if is_private else message.channel

        def status_notify(text: str) -> None:
            asyncio.run_coroutine_threadsafe(target.send(text), loop)

        cleaned = wall.parse_pattern_input(user_message) if wall.is_pattern_message(user_message) else ""
        # "pattern" alone (or in a sentence) is chat, not a grid paste
        if len(cleaned) >= wall_stream.MIN_PATTERN_CELLS:
            problem = wall_stream.pattern_input_error(cleaned)
            if problem:
                await target.send(problem)
                return
            try:
                await wall_stream.stream_pattern_solve(
                    cleaned,
                    lambda result: wall_stream.send_pattern_message(target, result),
                    wall_stream.edit_pattern_message,
                )
            except wall_stream.SolverBusy:
                await target.send(wall_stream.BUSY_MESSAGE)
            except asyncio.TimeoutError:
                await target.send(wall_stream.TIMEOUT_MESSAGE)
            except Exception:
                traceback.print_exc()
                await target.send(wall_stream.FAILED_MESSAGE)
            return

        # "how many records does X have?" → /player profile embed
        queried_player = parse_how_many_records_player(user_message)
        if queried_player:
            await _send_player_records_lookup(message, target, queried_player)
            return

        # Run sync AI / response logic off the event loop so status messages can send
        response = await asyncio.to_thread(
            get_response, user_message, user, status_notify
        )
        if isinstance(response, PatternResult):
            print("[PuddingBot]: " + response.content)
            if response.png:
                await target.send(
                    response.content,
                    file=File(io.BytesIO(response.png), filename="wallall.png"),
                )
            elif response.content:
                await target.send(response.content)
        elif response:
            print("[PuddingBot]: " + response)
            await target.send(response)
    except Exception:
        traceback.print_exc()


async def _send_player_records_lookup(message: Message, target, queried_player: str) -> None:
    """Resolve a natural-language player WR count question to the /player embed."""
    from github_cache_fetcher import github_cache_fetcher
    from cogs.fastsnakestats import ListPaginationView

    cog = bot.get_cog("FastSnakeStats")
    if cog is None:
        await target.send("❌ Player lookup is unavailable right now.")
        return

    needle = queried_player.strip()
    matches = await github_cache_fetcher.search_player_names(needle, limit=10)
    resolved = None
    if matches:
        exact = next((n for n in matches if n.lower() == needle.lower()), None)
        starts = next((n for n in matches if n.lower().startswith(needle.lower())), None)
        resolved = exact or starts or matches[0]
    else:
        # Fall back to the typed name; get_player_data does case-insensitive match
        resolved = needle

    player_data = await cog.get_player_data(resolved)
    if not player_data:
        hint = ""
        if matches and matches[0].lower() != resolved.lower():
            hint = f" Did you mean **{matches[0]}**?"
        await target.send(f"❌ No data found for player: {queried_player}.{hint}")
        return

    embed = cog.create_player_embed(player_data, page=0)
    activity_len = len(player_data.get("recent_activity") or [])
    total_pages = max(1, (activity_len + 4) // 5)
    if total_pages > 1:
        view = ListPaginationView(
            message.author.id,
            total_pages,
            lambda page: cog.create_player_embed(player_data, page),
        )
        view.message = await target.send(embed=embed, view=view)
    else:
        await target.send(embed=embed)

# Startup for the bot
@bot.event
async def on_ready() -> None:
    global _commands_synced
    print(f'{bot.user} is now running')
    # on_ready fires again after reconnects; syncing every time hits rate limits
    if _commands_synced:
        return
    _commands_synced = True

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

    if POI_CHANNEL_ID:
        poi_channel = bot.get_channel(int(POI_CHANNEL_ID))
        if poi_channel is not None:
            asyncio.create_task(purge_non_poi_messages(poi_channel))

@bot.event
async def on_message(message: Message) -> None:
    if message.author == bot.user or message.author.bot:
        return

    username: str = str(message.author)
    user_message: str = message.content
    channel: str = str(message.channel)
    in_poi = is_poi_channel(message.channel)

    print(f'[{channel}] {username}: "{user_message}"')
    if in_poi and not (is_allowed_poi_message(user_message) and not message.attachments):
        # Full-history sweep runs once at startup; live messages are checked one by one
        asyncio.create_task(_delete_one_quietly(message))

    # 1/67 easter egg when someone actually writes 67
    if mentions_67(user_message) and random.randint(1, 67) == 1 and SIXTY_SEVEN_ASSET:
        try:
            filename = "67" + os.path.splitext(SIXTY_SEVEN_ASSET)[1]
            await message.channel.send(file=File(SIXTY_SEVEN_ASSET, filename=filename))
        except Exception as e:
            print(f"Failed to send 67 meme: {e}")

    # 1/16 easter egg for wall-all category mentions
    lowered_message = visible_text(user_message).lower()
    if (
        any(trigger in lowered_message for trigger in WALL_ALL_TRIGGERS)
        and random.randint(1, 16) == 1
        and os.path.isfile(END_CAREER_ASSET)
    ):
        try:
            await message.channel.send(file=File(END_CAREER_ASSET, filename="end_career.png"))
        except Exception as e:
            print(f"Failed to send wall-all meme: {e}")

    # 1/16 easter egg for "im going for ..." grind announcements
    if (
        any(trigger in lowered_message for trigger in GOING_FOR_TRIGGERS)
        and random.randint(1, 16) == 1
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

    # 1/16 easter egg when someone says "count count"
    if (
        "count count" in lowered_message
        and random.randint(1, 16) == 1
        and os.path.isfile(COUNT_COUNT_ASSET)
    ):
        try:
            await message.channel.send(file=File(COUNT_COUNT_ASSET, filename="count_count.gif"))
        except Exception as e:
            print(f"Failed to send count count meme: {e}")

    # 1/16 easter egg when poison is mentioned
    if (
        re.search(r"\bpoison\b", lowered_message)
        and random.randint(1, 16) == 1
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

    # 1/16 easter egg when tally is mentioned (50/50 between two memes)
    if (
        re.search(r"\btally\b", lowered_message)
        and random.randint(1, 16) == 1
    ):
        tally_choices = [
            (TALLY_ASSET, "tally.gif"),
            (TALLY_LEARNING_ASSET, "tally_learning.png"),
        ]
        available = [(path, name) for path, name in tally_choices if os.path.isfile(path)]
        if available:
            path, filename = random.choice(available)
            try:
                await message.channel.send(file=File(path, filename=filename))
            except Exception as e:
                print(f"Failed to send tally meme: {e}")

    # 1/16 easter egg when softlock is mentioned
    if (
        re.search(r"\bsoftlock\b", lowered_message)
        and random.randint(1, 16) == 1
        and os.path.isfile(SOFTLOCK_ASSET)
    ):
        try:
            await message.channel.send(file=File(SOFTLOCK_ASSET, filename="softlock.gif"))
        except Exception as e:
            print(f"Failed to send softlock meme: {e}")

    # 1/16 easter egg for bad-RNG complaints (including "bs rng")
    if (
        os.path.isfile(BAD_RNG_ASSET)
        and (
            BAD_RNG_ALWAYS_RE.search(lowered_message)
            or BAD_RNG_COMPLAINT_RE.search(lowered_message)
        )
        and random.randint(1, 16) == 1
    ):
        try:
            await message.channel.send(file=File(BAD_RNG_ASSET, filename="bad_rng.png"))
        except Exception as e:
            print(f"Failed to send bad rng meme: {e}")

    if not (user_message.lower()[:3] == 'gif' and in_poi):
        # DM links are handled by cogs.dm_media — skip AI chatter for those
        is_dm = message.guild is None
        if not (is_dm and message_has_http_url(user_message)):
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

async def _delete_one_quietly(msg: Message) -> None:
    try:
        await _delete_one(msg)
    except Forbidden:
        print(f"Missing Manage Messages permission in #{msg.channel}")


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
    for extension in (
        'cogs.admin',
        'cogs.dm_media',
        'cogs.fastsnakestats',
        'cogs.image_tools',
        'cogs.mkv_convert',
        'cogs.repo_watcher',
        'cogs.wall_commands',
    ):
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

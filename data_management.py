# Data Management & State Module
# Handles all application state, variables, and data structures

from __future__ import annotations

import json
import os
from typing import Dict, Optional

# Game settings data structures (from FastSnakeStats)
APPLE_AMOUNTS = {
    "1 Apple": {"visible": True, "icon": "https://i.ibb.co/rGZV12Ym/count-00-png.png", "id": "count_00"},
    "3 Apples": {"visible": True, "icon": "https://i.ibb.co/V0gcrCmM/count-01-png.png", "id": "count_01"},
    "5 Apples": {"visible": True, "icon": "https://i.ibb.co/SSc8jww/count-02-png.png", "id": "count_02"},
    "10 Apples": {"visible": True, "icon": "https://i.ibb.co/gbTbZvw8/count-03.png", "id": "count_03"},
    "Dice": {"visible": True, "icon": "https://i.ibb.co/8DzSj9hV/count-03-png.png", "id": "count_04"},
    "Bomb": {"visible": True, "icon": "https://i.ibb.co/kVXQJrVp/count-05.png", "id": "count_05"},
    "Tally": {
        "visible": True,
        "icon": os.path.join(os.path.dirname(__file__), "assets", "count_06.png"),
        "id": "count_06",
    },
}

SPEEDS = {
    "Normal": {"visible": True, "icon": "https://i.ibb.co/p6rmphY3/speed-00-png.png", "id": "speed_00"},
    "Slow": {"visible": True, "icon": "https://i.ibb.co/hJz9cv8B/speed-02-png.png", "id": "speed_01"},
    "Fast": {"visible": True, "icon": "https://i.ibb.co/fzSffpZX/speed-01-png.png", "id": "speed_02"}
}

SIZES = {
    "Standard": {"visible": True, "icon": "https://i.ibb.co/wTygmfr/size-00-png.png", "id": "size_00"},
    "Small": {"visible": True, "icon": "https://i.ibb.co/JRC52RRx/size-01-png.png", "id": "size_01"},
    "Large": {"visible": True, "icon": "https://i.ibb.co/TDXV3KYM/size-02-png.png", "id": "size_02"}
}

GAMEMODES = {
    "Classic": {"visible": True, "icon": "https://i.ibb.co/Q3Qh6BSy/trophy-00-png.png", "id": "trophy_01"},
    "Wall": {"visible": True, "icon": "https://i.ibb.co/zhR45VL2/trophy-01-png.png", "id": "trophy_02"},
    "Portal": {"visible": True, "icon": "https://i.ibb.co/whH1HMVg/trophy-02-png.png", "id": "trophy_03"},
    "Cheese": {"visible": True, "icon": "https://i.ibb.co/RGtHVbmX/trophy-03-png.png", "id": "trophy_04"},
    "Borderless": {"visible": True, "icon": "https://i.ibb.co/YBW6HG1W/trophy-04-png.png", "id": "trophy_5"},
    "Twin": {"visible": True, "icon": "https://i.ibb.co/spKfXDbs/trophy-05-png.png", "id": "trophy_06"},
    "Winged": {"visible": True, "icon": "https://i.ibb.co/ZRd57NCq/trophy-06-png.png", "id": "trophy_07"},
    "Yin Yang": {"visible": True, "icon": "https://i.ibb.co/DgLr48GP/trophy-07-png.png", "id": "trophy_08"},
    "Key": {"visible": True, "icon": "https://i.ibb.co/ccfJ067j/trophy-08-png.png", "id": "trophy_09"},
    "Sokoban": {"visible": True, "icon": "https://i.ibb.co/GQSbLCPK/trophy-09-png.png", "id": "trophy_10"},
    "Poison": {"visible": True, "icon": "https://i.ibb.co/B5MFy3M2/trophy-10-png.png", "id": "trophy_11"},
    "Dimension": {"visible": True, "icon": "https://i.ibb.co/NgC8Rzrq/trophy-11-png.png", "id": "trophy_12"},
    "Minesweeper": {"visible": True, "icon": "https://i.ibb.co/r2b26trd/trophy-12-png.png", "id": "trophy_13"},
    "Statue": {"visible": True, "icon": "https://i.ibb.co/tTQyhWmV/trophy-13-png.png", "id": "trophy_14"},
    "Light": {"visible": True, "icon": "https://i.ibb.co/Mkk60W48/trophy-14-png.png", "id": "trophy_15"},
    "Shield": {"visible": True, "icon": "https://i.ibb.co/W4ZdB20L/trophy-15-png.png", "id": "trophy_16"},
    "Arrow": {"visible": True, "icon": "https://i.ibb.co/rGBxD1Jg/trophy-16-png.png", "id": "trophy_17"},
    "Hotdog": {"visible": True, "icon": "https://i.ibb.co/FF4hdbz/trophy-17-png.png", "id": "trophy_18"},
    "Magnet": {"visible": True, "icon": "https://i.ibb.co/nMbMjjfL/trophy-18-png.png", "id": "trophy_19"},
    "Gate": {"visible": True, "icon": "https://i.ibb.co/1tp8JqBM/trophy-19-png.png", "id": "trophy_20"},
    "Bridge": {"visible": True, "icon": "https://i.ibb.co/Kj7tYtM7/trophy-20.png", "id": "trophy_22"},
    "Peaceful": {"visible": True, "icon": "https://i.ibb.co/jvrCYD8r/trophy-17-png.png", "id": "trophy_21"}
}

RUN_MODES = {
    "25 Apples": {"visible": True, "icon": None, "text": "25 Apples", "id": "mode_00"},
    "50 Apples": {"visible": True, "icon": None, "text": "50 Apples", "id": "mode_01"},
    "100 Apples": {"visible": True, "icon": None, "text": "100 Apples", "id": "mode_02"},
    "All Apples": {"visible": True, "icon": None, "text": "All Apples", "id": "mode_03"},
    "High Score": {"visible": True, "icon": None, "text": "High Score", "id": "mode_04"}
}

EMOJI_MAP_PATH = os.path.join(os.path.dirname(__file__), "emoji_map.json")
_emoji_map_cache: Optional[Dict[str, str]] = None

# Guild custom emoji names already on the Snake Discord (from server emoji list)
SETTING_EMOJI_NAMES: Dict[str, str] = {
    # Apple counts
    "1 Apple": "1_apple_count",
    "3 Apples": "3_apples_count",
    "5 Apples": "5_apples_count",
    "10 Apples": "10_apples_count",
    "Dice": "dice_apple_count",
    "Bomb": "bomb_apple_count",
    "Tally": "tally",
    # Speeds
    "Normal": "normal_speed",
    "Fast": "fast_speed",
    "Slow": "speed_02",  # turtle emoji on server
    # Sizes
    "Standard": "standard_board_size",
    "Small": "small_board_size",
    "Large": "large_board_size",
    # Modes
    "Classic": "classic_mode",
    "Wall": "wall_mode",
    "Portal": "portal_mode",
    "Cheese": "cheese_mode",
    "Borderless": "borderless_mode",
    "Twin": "twin_mode",
    "Winged": "winged_mode",
    "Yin Yang": "yin_yang_mode",
    "Key": "key_mode",
    "Sokoban": "sokoban_mode",
    "Poison": "poison_mode",
    "Dimension": "dimension_mode",
    "Minesweeper": "minesweeper_mode",
    "Statue": "statue_mode",
    "Light": "light_mode",
    "Shield": "shield_mode",
    "Arrow": "arrow_mode",
    "Hotdog": "hotdog_mode",
    "Magnet": "magnet_mode",
    "Gate": "gate_mode",
    "Bridge": "bridge_mode",
    "Peaceful": "peaceful_mode",
}

# Alternate emoji names to try if the primary is missing
SETTING_EMOJI_NAME_ALIASES: Dict[str, tuple] = {
    "Yin Yang": ("yin_yang_mode", "yinyang_mode", "yin_yang", "yy_mode"),
    "Slow": ("speed_02", "slow_speed"),
}


def load_emoji_map(force: bool = False) -> Dict[str, str]:
    """In-memory emoji map: setting_id -> <:name:id> (filled from guild on startup)."""
    global _emoji_map_cache
    if _emoji_map_cache is not None and not force:
        return _emoji_map_cache
    # Optional leftover file from older versions
    if os.path.isfile(EMOJI_MAP_PATH):
        try:
            with open(EMOJI_MAP_PATH, encoding="utf-8") as handle:
                data = json.load(handle)
            _emoji_map_cache = data if isinstance(data, dict) else {}
            return _emoji_map_cache
        except Exception as e:
            print(f"Error loading emoji map: {e}")
    _emoji_map_cache = {}
    return _emoji_map_cache


def save_emoji_map(mapping: Dict[str, str]) -> None:
    global _emoji_map_cache
    _emoji_map_cache = mapping
    # Persist so a restart before guild cache is ready still has icons briefly
    try:
        with open(EMOJI_MAP_PATH, "w", encoding="utf-8") as handle:
            json.dump(mapping, handle, indent=2, sort_keys=True)
    except Exception as e:
        print(f"Could not write emoji map: {e}")


def emoji_names_for_setting(setting_name: str) -> list:
    """Candidate guild emoji names for a setting label."""
    names = []
    primary = SETTING_EMOJI_NAMES.get(setting_name)
    if primary:
        names.append(primary)
    for alt in SETTING_EMOJI_NAME_ALIASES.get(setting_name, ()):
        if alt not in names:
            names.append(alt)
    return names


def refresh_emoji_map_from_guild(guild) -> int:
    """
    Resolve setting icons from emojis already on the guild.
    Returns how many settings were mapped. No uploads.
    """
    if guild is None:
        return 0
    by_name = {e.name: e for e in guild.emojis}
    mapping: Dict[str, str] = {}
    for family in (APPLE_AMOUNTS, SPEEDS, SIZES, GAMEMODES):
        for setting_name, meta in family.items():
            setting_id = meta.get("id")
            if not setting_id:
                continue
            for emoji_name in emoji_names_for_setting(setting_name):
                emoji = by_name.get(emoji_name)
                if emoji is not None:
                    mapping[setting_id] = str(emoji)
                    break
    save_emoji_map(mapping)
    return len(mapping)


def get_setting_icon_markup(setting_name: str, family: dict) -> str:
    """Return custom emoji markup for a setting, or the plain name."""
    meta = family.get(setting_name) or {}
    setting_id = meta.get("id")
    if setting_id:
        emoji = load_emoji_map().get(setting_id)
        if emoji:
            return emoji
    return setting_name


def format_setting_with_icon(setting_name: str, family: dict) -> str:
    """Icon (if mapped) plus label, e.g. '<:tally:123> Tally'."""
    meta = family.get(setting_name) or {}
    setting_id = meta.get("id")
    emoji = load_emoji_map().get(setting_id) if setting_id else None
    if emoji:
        return f"{emoji} {setting_name}"
    return setting_name


def get_settings_key(apple_amount: str, speed: str, size: str, gamemode: str, run_mode: str = "25 Apples") -> str:
    """Generate a settings key for looking up records"""
    return f"{apple_amount}|{speed}|{size}|{gamemode}|{run_mode}"


def format_category_key(settings_key: str, with_icons: bool = True) -> str:
    """Format a settings key as readable category text (optionally with Discord emojis)."""
    parts = settings_key.split('|')
    if len(parts) != 5:
        return settings_key
    apple_amount, speed, size, gamemode, run_mode = parts
    if with_icons:
        return (
            f"{format_setting_with_icon(gamemode, GAMEMODES)} • "
            f"{format_setting_with_icon(apple_amount, APPLE_AMOUNTS)} • "
            f"{format_setting_with_icon(speed, SPEEDS)} • "
            f"{format_setting_with_icon(size, SIZES)} • "
            f"{run_mode}"
        )
    return f"{gamemode} • {apple_amount} • {speed} • {size} • {run_mode}"

def parse_time(time_str: str) -> str:
    """Parse time from ISO 8601 duration format to readable format with hours support"""
    if not time_str or not isinstance(time_str, str):
        return "N/A"
    
    # Handle ISO 8601 duration format (PT1H2M3.456S)
    if time_str.startswith('PT'):
        time_str = time_str[2:]  # Remove 'PT'
        
        hours = 0
        minutes = 0
        seconds = 0
        
        # Extract hours
        if 'H' in time_str:
            parts = time_str.split('H')
            hours = int(parts[0])
            time_str = parts[1]
        
        # Extract minutes
        if 'M' in time_str:
            parts = time_str.split('M')
            minutes = int(parts[0])
            time_str = parts[1]
        
        # Extract seconds
        if 'S' in time_str:
            seconds = float(time_str.replace('S', ''))
        
        # Format as (hours)h (minutes)m (seconds)s (milliseconds)ms
        total_seconds = hours * 3600 + minutes * 60 + seconds
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        
        # Format with hours only if > 0
        if hours > 0:
            # Split seconds into whole seconds and milliseconds
            whole_seconds = int(seconds)
            milliseconds = int(round((seconds - whole_seconds) * 1000))
            return f"{hours}h {minutes}m {whole_seconds}s {milliseconds}ms"
        elif minutes > 0:
            # Split seconds into whole seconds and milliseconds
            whole_seconds = int(seconds)
            milliseconds = int(round((seconds - whole_seconds) * 1000))
            return f"{minutes}m {whole_seconds}s {milliseconds}ms"
        else:
            # Only seconds, no minutes or hours
            whole_seconds = int(seconds)
            milliseconds = int(round((seconds - whole_seconds) * 1000))
            return f"{whole_seconds}s {milliseconds}ms"
    
    return time_str

def get_player_name(run_data: dict) -> str:
    """Extract player name from run data"""
    try:
        if (run_data.get('players') and
            run_data['players'].get('data') and
            isinstance(run_data['players']['data'], list) and
            len(run_data['players']['data']) > 0):

            player_data = run_data['players']['data'][0]
            if player_data.get('names') and player_data['names'].get('international'):
                return player_data['names']['international']
            # Guest players from runs-derived timelines use top-level name
            if player_data.get('name'):
                return player_data['name']
    except Exception as e:
        print(f"Error extracting player name: {e}")

    return "Unknown Player"

def get_run_time(run_data: dict) -> str:
    """Extract and format run time from run data"""
    try:
        if run_data.get('times') and run_data['times'].get('primary'):
            return parse_time(run_data['times']['primary'])
    except Exception as e:
        print(f"Error extracting run time: {e}")
    
    return "N/A"

def get_run_date(run_data: dict) -> str:
    """Extract run date from run data"""
    try:
        if run_data.get('date'):
            return run_data['date']
    except Exception as e:
        print(f"Error extracting run date: {e}")
    
    return "N/A"

def get_run_link(run_data: dict) -> str:
    """Extract run link from run data"""
    try:
        if run_data.get('weblink'):
            return run_data['weblink']
    except Exception as e:
        print(f"Error extracting run link: {e}")
    
    return ""

def validate_settings(apple_amount: str, speed: str, size: str, gamemode: str) -> bool:
    """Validate that all settings are valid"""
    return (apple_amount in APPLE_AMOUNTS and 
            speed in SPEEDS and 
            size in SIZES and 
            gamemode in GAMEMODES)

def get_ordered_apple_amounts() -> list:
    """Get ordered list of apple amounts"""
    return ["1 Apple", "3 Apples", "5 Apples", "10 Apples", "Dice", "Bomb", "Tally"]

def get_ordered_speeds() -> list:
    """Get ordered list of speeds"""
    return ["Normal", "Slow", "Fast"]

def get_ordered_sizes() -> list:
    """Get ordered list of sizes"""
    return ["Standard", "Small", "Large"]

def get_ordered_gamemodes() -> list:
    """Get ordered list of gamemodes"""
    return list(GAMEMODES.keys())

def get_ordered_run_modes() -> list:
    """Get ordered list of run modes"""
    return ["25 Apples", "50 Apples", "100 Apples", "All Apples", "High Score"]


# Modes that have a High Score leaderboard on main snake_game
HIGHSCORE_MODES = frozenset({
    "Wall", "Portal", "Key", "Sokoban", "Poison", "Minesweeper",
    "Statue", "Shield", "Hotdog", "Gate", "Bridge",
})

# Modes whose Tally High Score lives on snake_game_ce (FastSnakeStats tally-boards.js)
TALLY_CE_HIGHSCORE_MODES = frozenset({
    "Classic", "Cheese", "Borderless", "Twin", "Winged", "Yin Yang",
    "Dimension", "Light", "Arrow", "Magnet",
})

DIFFICULTY_TIERS = [
    "Free", "Warmup", "Easy", "Medium", "Hard", "Mythic", "Lottery", "Inhuman",
]

MODE_BASE_TIER = {
    "Peaceful": "Free",
    "Classic": "Warmup",
    "Cheese": "Warmup",
    "Borderless": "Warmup",
    "Winged": "Warmup",
    "Yin Yang": "Warmup",
    "Magnet": "Warmup",
    "Dimension": "Easy",
    "Statue": "Easy",
    "Arrow": "Easy",
    "Light": "Easy",
    "Wall": "Medium",
    "Portal": "Medium",
    "Twin": "Medium",
    "Key": "Medium",
    "Poison": "Medium",
    "Minesweeper": "Medium",
    "Shield": "Medium",
    "Hotdog": "Medium",
    "Sokoban": "Hard",
    "Gate": "Hard",
    "Bridge": "Medium",
}

_COUNT_MORE_EASIER = ["Bomb", "10 Apples", "5 Apples", "Dice", "3 Apples", "1 Apple", "Tally"]
_COUNT_LESS_EASIER = ["Tally", "1 Apple", "3 Apples", "Dice", "5 Apples", "10 Apples", "Bomb"]
_COUNT_POISON = ["Tally", "1 Apple", "Dice", "3 Apples", "5 Apples", "10 Apples", "Bomb"]
_COUNT_LESS_EASIER_MODES = frozenset({
    "Portal", "Key", "Sokoban", "Minesweeper", "Shield", "Hotdog",
})
_APPLE_RUNS = ["25 Apples", "50 Apples", "100 Apples", "All Apples"]


def is_high_score_mode(gamemode: str) -> bool:
    """True if this mode has High Score on the main snake_game boards."""
    return gamemode in HIGHSCORE_MODES


def is_tally_ce_highscore_mode(gamemode: str) -> bool:
    """True if Tally High Score for this mode is on Category Extensions."""
    return gamemode in TALLY_CE_HIGHSCORE_MODES


def allows_high_score(apple_amount: str, gamemode: str) -> bool:
    """Whether High Score exists for this count+mode (FSS shouldShowHighScoreColumn)."""
    if is_high_score_mode(gamemode):
        return True
    return apple_amount == "Tally" and is_tally_ce_highscore_mode(gamemode)


def is_valid_category(
    apple_amount: str,
    speed: str,
    size: str,
    gamemode: str,
    run_mode: str,
) -> bool:
    """True for combinations that exist in FastSnakeStats / SRC boards."""
    if apple_amount not in APPLE_AMOUNTS:
        return False
    if speed not in SPEEDS or size not in SIZES or gamemode not in GAMEMODES:
        return False
    if run_mode not in RUN_MODES:
        return False
    # 100 Apples is not played on Small
    if run_mode == "100 Apples" and size == "Small":
        return False
    # Yin Yang 50 on Small does not exist
    if gamemode == "Yin Yang" and run_mode == "50 Apples" and size == "Small":
        return False
    # High Score only where FSS shows an HS column
    if run_mode == "High Score" and not allows_high_score(apple_amount, gamemode):
        return False
    return True


def parse_category_parts(settings_key: str) -> dict:
    parts = (settings_key or "").split("|")
    return {
        "apple_amount": parts[0] if len(parts) > 0 else "",
        "speed": parts[1] if len(parts) > 1 else "",
        "size": parts[2] if len(parts) > 2 else "",
        "game_mode": parts[3] if len(parts) > 3 else "",
        "run_mode": parts[4] if len(parts) > 4 else "",
    }


def tier_index(name: str) -> int:
    try:
        return DIFFICULTY_TIERS.index(name)
    except ValueError:
        return 0


def _effective_mode_tier(mode: str, size: str, speed: str, run: str, apple: str) -> str:
    if mode == "Peaceful":
        return "Free"

    # Tally starts at Medium before other overrides (FSS analyzer)
    tier = "Medium" if apple == "Tally" else MODE_BASE_TIER.get(mode, "Medium")

    if mode == "Wall" and run == "All Apples":
        if size in ("Standard", "Large") and speed == "Fast":
            tier = "Inhuman"
        elif size in ("Standard", "Large"):
            tier = "Lottery"
        elif size == "Small" and speed == "Normal":
            tier = "Hard"
        elif size == "Small" and speed == "Slow":
            tier = "Hard"
        elif size == "Small" and speed == "Fast":
            tier = "Mythic"
    elif mode == "Cheese" and run == "50 Apples" and size == "Small":
        tier = "Warmup" if apple in ("10 Apples", "Bomb") else "Lottery"
    elif mode == "Statue" and apple == "1 Apple" and run == "50 Apples" and size == "Small":
        tier = "Lottery"
    elif mode == "Statue" and run == "100 Apples" and size == "Standard" and apple == "1 Apple":
        tier = "Mythic"
    elif mode == "Portal" and apple == "Bomb":
        tier = "Inhuman" if speed == "Fast" else "Mythic"
    elif mode == "Poison" and apple == "Bomb":
        tier = "Inhuman" if speed == "Fast" else "Mythic"
    elif (
        mode not in ("Borderless", "Classic", "Cheese", "Magnet", "Light", "Yin Yang")
        and not (mode == "Statue" and apple in ("10 Apples", "Bomb"))
        and not (mode == "Arrow" and apple == "Bomb")
        and not (mode == "Portal" and apple == "Bomb")
        and not (mode == "Poison" and apple == "Bomb")
        and speed == "Fast"
        and size == "Large"
        and run == "All Apples"
    ):
        tier = "Mythic"
    elif mode == "Portal" and speed == "Fast" and size in ("Standard", "Large"):
        tier = "Hard"
    elif mode == "Winged" and speed == "Fast":
        tier = "Easy"

    if speed == "Fast" and size in ("Standard", "Large"):
        if tier_index(tier) < tier_index("Medium"):
            tier = "Medium"

    if size == "Large" and run == "All Apples":
        if tier_index(tier) < tier_index("Hard"):
            tier = "Hard"

    if speed == "Slow" and tier == "Mythic":
        keep = (mode == "Portal" and apple == "Bomb") or (mode == "Poison" and apple == "Bomb")
        if not keep:
            tier = "Hard"

    slow_small_exception = (
        (mode == "Wall" and run == "All Apples")
        or (mode == "Cheese" and run == "50 Apples" and size == "Small")
        or (mode == "Statue" and apple == "1 Apple" and run == "50 Apples" and size == "Small")
        or (mode == "Portal" and apple == "Bomb")
        or (mode == "Poison" and apple == "Bomb")
    )
    if speed == "Slow" and size == "Small" and not slow_small_exception:
        if tier_index(tier) > tier_index("Medium"):
            tier = "Medium"

    return tier


def _count_weight(mode: str, apple: str) -> int:
    if mode == "Twin":
        return 0
    if mode == "Poison":
        order = _COUNT_POISON
    elif mode in _COUNT_LESS_EASIER_MODES:
        order = _COUNT_LESS_EASIER
    else:
        order = _COUNT_MORE_EASIER
    try:
        return order.index(apple)
    except ValueError:
        return 0


def _size_weight(size: str) -> int:
    return {"Small": 0, "Standard": 1, "Large": 2}.get(size, 1)


def _speed_weight(speed: str) -> int:
    return {"Slow": 0, "Normal": 1, "Fast": 2}.get(speed, 1)


def _run_weight(run: str) -> float:
    return {
        "25 Apples": 0,
        "50 Apples": 1,
        "100 Apples": 2,
        "High Score": 3,
        "All Apples": 3.2,
    }.get(run, 0)


def score_category(settings_key: str) -> dict:
    """Difficulty score/tier matching FastSnakeStats unheld scoring."""
    parts = parse_category_parts(settings_key)
    apple, speed, size = parts["apple_amount"], parts["speed"], parts["size"]
    mode, run = parts["game_mode"], parts["run_mode"]
    tier = _effective_mode_tier(mode, size, speed, run, apple)
    score = (
        tier_index(tier) * 100
        + _size_weight(size) * 10
        + _speed_weight(speed) * 10
        + _count_weight(mode, apple) * 1
        + _run_weight(run) * 1
    )
    return {
        "score": round(score * 10) / 10,
        "tier": tier,
        **parts,
    }


def enumerate_valid_categories() -> list:
    """All valid category keys (same rules as FastSnakeStats expected set)."""
    keys = []
    for apple in get_ordered_apple_amounts():
        for speed in get_ordered_speeds():
            for size in get_ordered_sizes():
                for mode in get_ordered_gamemodes():
                    for run in _APPLE_RUNS:
                        if is_valid_category(apple, speed, size, mode, run):
                            keys.append(get_settings_key(apple, speed, size, mode, run))
                    if is_valid_category(apple, speed, size, mode, "High Score"):
                        keys.append(
                            get_settings_key(apple, speed, size, mode, "High Score")
                        )
    return keys


def filter_valid_categories(
    game_mode: str = None,
    apple_amount: str = None,
    speed: str = None,
    size: str = None,
    run_mode: str = None,
    tier: str = None,
) -> list:
    """Valid categories matching optional filters."""
    # Impossible combo — never produce a pool for it
    if run_mode == "100 Apples" and size == "Small":
        return []

    out = []
    for key in enumerate_valid_categories():
        parts = parse_category_parts(key)
        if parts["run_mode"] == "100 Apples" and parts["size"] == "Small":
            continue
        if game_mode and parts["game_mode"] != game_mode:
            continue
        if apple_amount and parts["apple_amount"] != apple_amount:
            continue
        if speed and parts["speed"] != speed:
            continue
        if size and parts["size"] != size:
            continue
        if run_mode and parts["run_mode"] != run_mode:
            continue
        if tier:
            scored = score_category(key)
            if scored["tier"] != tier:
                continue
        out.append(key)
    return out

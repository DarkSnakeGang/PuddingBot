# Data Management & State Module
# Handles all application state, variables, and data structures

# Game settings data structures (from FastSnakeStats)
APPLE_AMOUNTS = {
    "1 Apple": {"visible": True, "icon": "https://i.ibb.co/rGZV12Ym/count-00-png.png", "id": "count_00"},
    "3 Apples": {"visible": True, "icon": "https://i.ibb.co/V0gcrCmM/count-01-png.png", "id": "count_01"},
    "5 Apples": {"visible": True, "icon": "https://i.ibb.co/SSc8jww/count-02-png.png", "id": "count_02"},
    "Dice": {"visible": True, "icon": "https://i.ibb.co/8DzSj9hV/count-03-png.png", "id": "count_03"}
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
    "Peaceful": {"visible": True, "icon": "https://i.ibb.co/jvrCYD8r/trophy-17-png.png", "id": "trophy_21"}
}

RUN_MODES = {
    "25 Apples": {"visible": True, "icon": None, "text": "25 Apples", "id": "mode_00"},
    "50 Apples": {"visible": True, "icon": None, "text": "50 Apples", "id": "mode_01"},
    "100 Apples": {"visible": True, "icon": None, "text": "100 Apples", "id": "mode_02"},
    "All Apples": {"visible": True, "icon": None, "text": "All Apples", "id": "mode_03"},
    "High Score": {"visible": True, "icon": None, "text": "High Score", "id": "mode_04"}
}

def get_settings_key(apple_amount: str, speed: str, size: str, gamemode: str, run_mode: str = "25 Apples") -> str:
    """Generate a settings key for looking up records"""
    return f"{apple_amount}|{speed}|{size}|{gamemode}|{run_mode}"

def parse_time(time_str: str) -> str:
    """Parse time from ISO 8601 duration format to readable format"""
    if not time_str or not isinstance(time_str, str):
        return "N/A"
    
    # Handle ISO 8601 duration format (PT1M23.456S)
    if time_str.startswith('PT'):
        time_str = time_str[2:]  # Remove 'PT'
        
        minutes = 0
        seconds = 0
        
        # Extract minutes
        if 'M' in time_str:
            parts = time_str.split('M')
            minutes = int(parts[0])
            time_str = parts[1]
        
        # Extract seconds
        if 'S' in time_str:
            seconds = float(time_str.replace('S', ''))
        
        # Format as MM:SS.mmm
        total_seconds = minutes * 60 + seconds
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        
        return f"{minutes}:{seconds:06.3f}".replace('.', ':')
    
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
    return ["1 Apple", "3 Apples", "5 Apples", "Dice"]

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

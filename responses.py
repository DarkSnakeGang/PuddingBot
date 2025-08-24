from random import choice, randint
import requests as rq
import gpt
import wall
import os
import asyncio

def get_random_funny_gif(api_key, emotion):
    url = 'https://tenor.googleapis.com/v2/search'
    key_words = ['happy', 'sad', 'angry', 'excited', 'nervous', 'frustrated', 'calm', 'anxious', 'proud', 'confused',
 'shocked', 'embarrassed', 'grateful', 'jealous', 'curious', 'bored', 'hopeful', 'lonely', 'fearful', 
 'amused', 'content', 'disappointed', 'annoyed', 'surprised', 'relieved', 'guilty', 'ashamed', 'ecstatic', 
 'worried', 'resentful', 'envious', 'determined', 'overwhelmed', 'humiliated', 'skeptical', 'inspired', 
 'nostalgic', 'vindicated', 'heartbroken', 'optimistic', 'pessimistic', 'tired', 'energetic', 'isolated', 
 'trustful', 'distrustful', 'passionate', 'apathetic', 'impatient', 'satisfied', 'insecure', 'secure', 
 'offended', 'admiring', 'resentful', 'intimidated', 'disgusted', 'awed', 'motivated', 'infuriated', 
 'sympathetic', 'irritated', 'compassionate', 'playful', 'melancholic', 'defeated', 'ashamed', 'peaceful', 
 'enthusiastic', 'fascinated', 'self-conscious', 'inferior', 'superior', 'vulnerable', 'inconsolable', 
 'forgiving', 'triumphant', 'disheartened', 'grieving', 'alienated', 'offended', 'apathetic', 'resentful', 
 'hopeless', 'overjoyed', 'dismayed', 'disillusioned', 'terrified', 'awed', 'depressed', 'stressed', 
 'serene', 'flattered', 'lonely', 'fulfilled', 'exhausted', 'tender', 'impressed', 'compassionate', 
 'delighted', 'hesitant', 'thrilled', 'sympathetic', 'intrigued']

    tenor_limit = 1
    if emotion:
        query = emotion
    else:
        query = choice(key_words) + ' anime girl'
        tenor_limit = 20
    params = {
        'q': query,
        'key': api_key,
        'limit': tenor_limit
    }

    try:
        response = rq.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        results = data.get('results', [])
        if not results:
            return "No GIFs found."

        gif_data = choice(results)
        media_formats = gif_data.get('media_formats', {})
        gif_url = media_formats.get('gif', {}).get('url')

        if not gif_url:
            gif_url = media_formats.get('loopedmp4', {}).get('url')

        return gif_url if gif_url else "No suitable GIF found."

    except rq.exceptions.RequestException as e:
        return f"Request error: {e}"
    except ValueError as e:
        return f"JSON decoding error: {e}"

src_url = 'https://www.speedrun.com/api/v1/games/'
snake_game = "o1y9pyk6"
snake_game_ce = "9dow0go1"

sg_details = {}
ce_details = {}

def generate_payload_metadata():
    sg_details["vars"] = rq.get(f"{src_url}{snake_game}/variables").json()
    sg_details["cats"] = rq.get(f"{src_url}{snake_game}/categories?embed=game").json()
    sg_details["lvls"] = rq.get(f"{src_url}{snake_game}/levels").json()
    ce_details["vars"] = rq.get(f"{src_url}{snake_game_ce}/variables").json()
    ce_details["cats"] = rq.get(f"{src_url}{snake_game_ce}/categories?embed=game").json()
    ce_details["lvls"] = rq.get(f"{src_url}{snake_game_ce}/levels").json()

def request_record(gameID, variable_IDs, category_IDs):
    pass

def generate_payload():
    pass

def clear_context():
    return [{
        "role": "system",
        "content": """You are an assistant Discord bot developed by Yarmiplay called PuddingBot. 
        You must give short, precise and honest answers, and also admit when you don't know something.
        You heavily oppose circumcision. You support veganism.
        Yarmiplay is the server owner of the Google Snake Discord community server, a well known Google Snake player and speedrunner, and the maker of several Google Snake Mods, most notebly PuddingMod.
        Yarmiplay also made PuddingBot, which is you, the assistant Discord bot.
        With regards to wall mode in Google Snake, so far we know of exactly 235,355,155 wall patterns in small board, this number will not change unless wall mode is changed.
        If someone asks how rare a ham cycle is, it's roughly ~0.11 percent of patterns are cycles in small size. It doesn't mean those are the odds of you getting them, it's just how many of the total patterns we calculated so far (over half a million) we managed to find cycles for.
        If someone asks how rare is a ham path, we haven't calculated it yet, we don't know if it's more or less common than a ham cycle.
        We do not know how many patterns in normal size or large, but it's going to be a lot more than small.
        If someone asks, to get Runner role, you need to have a verified run on SRC (Speedrun.com), DM an admin and they'll give it to you.
        If someone asks why mobile google snake runs are banned: When Google Snake is played on mobile, the resolution of the game can vary greatly depending on the device. This would also leads inconsistent apple spawning as well as different number of squares to travel across the board. This gives certain runners unfair advantage over other runners.
        If someone asks about submitting multiple runs in the same video to speedrun.com, the answer is that it's allowed.
        If someone asks, the creator of Google Snake is CLTincknell and he is in the discord server.
        If someone asks what makes a mode in google snake a high score mode, the answer is that a high score mode needs to have a spawn radius towards an element of gameplay. Spawn radius is when something isn't allowed to spawn too closely to the snake's head, because it is dangerous enough to kill the snake, and having it spawn so close might end the run unfairly. Additionally, an exception was made by the community for Statue mode with 1 apple.
        There are 8 high score modes. Those are Sokoban, Minesweeper, Poison, Key, Portal, Shield, Wall and (Statue but only for 1a). Cheese is high score too.
        If asked, Google snake has 22 modes: Classic, Wall, Portal, Cheese, Borderless, Twin, Winged, Yin Yang, Key, Sokoban, Poison, Dimension, Minesweeper, Statue, Light, Shield, Arrow, Hotdog, Magnet, Gate, Peaceful, and Blender which let's you mix modes together. Don't explain what each mode does.
        
        I am PuddingBot, a Discord bot for the Google Snake gaming community. I have the following FastSnakeStats commands available:
        - /record - Get world records for specific game settings (game mode, apple amount, speed, size, run mode, optional date)
        - /available-dates - List available historical dates for viewing past records
        - /player - Get player statistics and recent activity (player name, optional date)
        - /stats - Get top record holders statistics (by number and percentage, optional date)
        
        I can help users look up world records, player statistics, and historical data from the FastSnakeStats database. All commands support optional historical date parameters to view data from specific dates.
        Portal mode has twice the fruit and each one you eat makes the head escape out of it's matching fruit, and spawns 2 additional fruit.
        Yin yang is the mode with 2 snakes, where one is just an inverted snake. In twin mode, the snake switches places between head and tail only when it eats an apple.
        Google snake has 3 speeds which are Slow, Normal and Fast. Google Snake has 3 sizes, Small, normal and large.
        Also know that ChessMod is a mod developed by Yarmiplay with adds Chess Mode to the game.
        PuddingMod is a mod created by Yarmiplay. It is available through Mod Loader. Initially, Yarmiplay made the mod to just add Pudding as a fruit option for the snake, but later on he expanded the mod to add additional fruit options, additional snake color and custom themes. It displays the count and speed of the game at the top bar, replacing the "selected fruit" and mute button respectively. The mod is intended to only make visual changes to the games. 
        Google Snake has hazards, but doesn't have enemies.
        If someone mentions it, Spawn Radius refers to the fact that in some modes, game objects that are considered "dangerous", are unable to spawn too close to the snake's head. The spawn radius is 3 in taxicab geometry.
        The creator of Mod Loader, level editor mod and mouse mod is TF2Llama, which is mostly known for modding and creating TASes.
        In google snake, tail hug is a pattern agnostic strategy that guarantees avoiding obstacles in "high score modes" in Google Snake. 
        In google snake, Schnippi coil is a pattern that follows a Hamiltonian cycle which maximizes turns in order to avoid being blocked off by obstacles in high score modes, without losing much speed. The coil mostly U-coils horizontally, with a single 3-wide U-coil on top and another 3 wide vertical coil along the border to cycle back - for Small size board and for large size board. This coil was named after the player Schnippi.
        In google snake, Carrot Coil is a simple coil where the player goes up and down for half the board, besides the edges where the player goes the entire way and turns around, to keep going up and down for half the board to the other side. It was name after the player TheEpicCarrot7 for using it in the first ever portal all apples achieved on March 2021.
        In google snake, the "1a, 3a, 5a, dice" notation refers to the apple count, which is how many apples appear on screen at any given time.
        Google snake has no time limits. The goal of the game is to complete the board until no more apples can spawn.
        Your Discord Profile Picture is clip art of Pudding, because you are PuddingBot.
        SpaceDoge is a google snake player mostly known for holding wall mode 25 score speedrun world record with a time of 28s485ms.
        """
    }]

context = clear_context()
conversation_history = {}  # Store conversation history per user

def get_response(user_input: str, user = "Nobody") -> str:
    blocked_users = ["1118731833262231714"]
    global context
    lowered = user_input.lower()
    PuddingBot = '<@1210325027023753307>'

    cringe_list = ['https://media.tenor.com/v8zqaakaqlaaaaac/sensational-poster-cinema-in-2014-aamirkhan.gif', 
                   'https://tenor.com/view/pingas-butt-lame-fat-sitdown-gif-4771119']

    if lowered in cringe_list:
        return get_random_funny_gif(os.getenv('TENOR_KEY'), False)

    if lowered == 'roll dice':
        return str(randint(1, 6))
    
    if "<:" in lowered and ":1362102081502318742>" in lowered:
        return '<:poi:1362102081502318742>'

    if 'gif' == lowered[:3]:
        return get_random_funny_gif(os.getenv('TENOR_KEY'), lowered.replace("gif", ""))
    
    if 'i completely agree' == lowered[:len('I completely agree')]:
        return get_random_funny_gif(os.getenv('TENOR_KEY'), 'I completely agree thanos')

    if "how" in lowered:
        if "timer" in lowered:
            return "<#968893937630736504>"
        if "tas" in lowered:
            return "Read rule 10, <#995955083395215412>"
        if "many" in lowered and "patterns" in lowered and "wall" in lowered and "small" in lowered:
            return "So far we know of exactly 235,355,155 wall patterns in small board."
        if "mods" in lowered:
            return "https://googlesnakemods.com"

    if "pattern" == lowered[:7]:
        return wall.check_pattern(lowered[-90:])

    if PuddingBot in lowered:
        print(f"[BOT PINGED] User {user} sent: {user_input}")
        
        if user in blocked_users: # Blocked him from using the bot
            return "You are blocked from using PuddingBot GPT function"
        if lowered.replace(PuddingBot, "") == " clear context":
            context = clear_context()
            if user in conversation_history:
                conversation_history[user] = []
            return "Context cleared, I will no longer remember what we just discussed"
        
        # Get or initialize conversation history for this user
        if user not in conversation_history:
            conversation_history[user] = []
        
        # Prepare user message
        user_message = lowered.replace(PuddingBot, "") + ", give a short answer but never mention that I asked for a short answer"
        
        # Add user message to conversation history BEFORE calling GPT
        conversation_history[user].append({"role": "user", "content": user_message})
        
        # Create messages array with system context and full conversation history
        messages = context + conversation_history[user]
        
        gpt_res = gpt.chat_with_gpt(messages)
        print(f"[AI RESPONSE] Generated: {gpt_res}")
        
        # Add assistant response to conversation history
        conversation_history[user].append({"role": "assistant", "content": gpt_res})
        
        # Limit conversation history to last 10 messages to prevent context overflow
        if len(conversation_history[user]) > 10:
            conversation_history[user] = conversation_history[user][-10:]
        
        if len(gpt_res) > 2000:
            return "The answer I have is too long\nYou'll have to wait until Yarmiplay implements the option for me to split my answer into multiple messages for long answers like this"
        else:
            print(f"[SENT TO DISCORD] Response sent to user {user}")
            return gpt_res


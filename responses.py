from random import choice, randint
import requests as rq
import gpt
import wall

src_url = 'https://www.speedrun.com/api/v1/games/'
snake_game = "o1y9pyk6"
snake_game_ce = "9dow0go1"

sg_details = {}
ce_details = {}

def generate_payload_metadata():
    sg_details["vars"] = rq.get(src_url + snake_game + "/variables").json()
    sg_details["cats"] = rq.get(src_url + snake_game + "/categories?embed=game").json()
    sg_details["lvls"] = rq.get(src_url + snake_game + "/levels").json()
    ce_details["vars"] = rq.get(src_url + snake_game_ce + "/variables").json()
    ce_details["cats"] = rq.get(src_url + snake_game_ce + "/categories?embed=game").json()
    ce_details["lvls"] = rq.get(src_url + snake_game_ce + "/levels").json()

# Info that matters
# mode count speed size

def request_record(gameID, variable_IDs, category_IDs):

    var = 0
    

    while var < len(variable_IDs["data"]):
        

        var += 1

    pass

def generate_payload():
    

    pass

def clear_context():
    context = [{"role": "system", 
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
As of 14.12.2023, there are 8 high score modes. Those are Sokoban, Minesweeper, Poison, Key, Portal, Shield, Wall and (Statue but only for 1a). Cheese is not a high score mode despite it being possible to end with different scores.
            If asked, Google snake has 18 modes, not including Blender which let's you mix modes together. Don't explain what each mode does.
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
            """}]
    return context

context = clear_context()

def get_response(user_input: str) -> str:
    global context
    lowered: str = user_input.lower()
    PuddingBot = '<@1210325027023753307>'

    if lowered == 'roll dice':
        return str(randint(1, 6))
    
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
        return wall.check_pattern(lowered.split(" ")[1])

    if PuddingBot in lowered:
        if lowered.replace(PuddingBot, "") == " clear context":
            context = clear_context()
            return "Context cleared, I will no longer remember what we just discussed"
        gpt_res = gpt.chat_with_gpt(lowered.replace(PuddingBot, "") + ", give a short answer but never mention that I asked for a short answer", context)
        if len(gpt_res) > 2000:
            return "The answer I have is too long\nYou'll have to wait until Yarmiplay implements the option for me to split my answer into multiple messages for long answers like this"
        else:
            return gpt_res


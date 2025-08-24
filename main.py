from typing import Final
import os 
from dotenv import load_dotenv
from discord import Intents, Message, utils
from discord.ext import commands
from responses import get_response
import asyncio

# Load Token
load_dotenv()
TOKEN: Final[str] = os.getenv('DISCORD_TOKEN')

# Setup Bot with commands framework
intents: Intents = Intents.default()
intents.message_content = True 
intents.messages = True  # Enable message intents
bot = commands.Bot(command_prefix='!', intents=intents)

# Message stuff
async def send_message(message: Message, user_message: str, user = "Nobody") -> None:
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
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@bot.event
async def on_message(message: Message) -> None:
    if message.author == bot.user:
        return
    
    username: str = str(message.author)
    user_message: str = message.content
    channel: str = str(message.channel)
    target_channel_name = "poi-🐡"
    
    # Check if the message is in the target channel
    print(f'[{channel}] {username}: "{user_message}"')
    if str(message.channel) == target_channel_name:
        # Check if the message is not the emoji :poi:
        await read_channel_history(message.channel)
    else:
        if channel == "Direct Message with Unknown User":
            return
    
    if not ('gif' == user_message.lower()[:3] and channel == target_channel_name):
        await send_message(message, user_message, message.author.id)
    
    # Process commands
    await bot.process_commands(message)

async def read_channel_history(channel, limit: int = 1000):
    # Find the channel by name
    # channel = utils.get(bot.get_all_channels(), name=channel_name)
    messages_to_delete = []

    if channel is not None:
        # Fetch the message history
        async for message in channel.history(limit=limit):
            # print(f'{message.author}: {message.content}')
            if not (
                message.content.startswith("<:") and
                message.content.endswith(":1362102081502318742>") and
                "<" not in message.content[2:-len(":1362102081502318742>")] and
                ":" not in message.content[2:-len(":1362102081502318742>")]
            ) or message.attachments:
                messages_to_delete.append(message)  # Store the message for potential processing

        if messages_to_delete:
            await channel.delete_messages(messages_to_delete)
            print(f"Deleted {len(messages_to_delete)} messages.")    
        else:
            print(f'Channel "{channel}" not found.')

# Load FastSnakeStats cog
async def load_extensions():
    """Load all cogs"""
    try:
        await bot.load_extension('fastsnakestats')
        print("✅ FastSnakeStats cog loaded successfully")
    except Exception as e:
        print(f"❌ Error loading FastSnakeStats cog: {e}")

# Main entry point
async def main() -> None:
    async with bot:
        await load_extensions()
        await bot.start(token=TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
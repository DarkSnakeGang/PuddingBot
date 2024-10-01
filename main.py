from typing import Final
import os 
from dotenv import load_dotenv
from discord import Intents, Client, Message, utils
from responses import get_response
import time

# Load Token
load_dotenv()
TOKEN: Final[str] = os.getenv('DISCORD_TOKEN')

# Setup Bot
intents: Intents = Intents.default()
intents.message_content = True 
client: Client = Client(intents=intents)

# Message stuff
async def send_message(message: Message, user_message: str) -> None:
    if not user_message:
        print('Empty message')
        return
    
    if is_private := user_message[0] == '?':
        user_message = user_message[1]

    try:
        response: str = get_response(user_message)
        await message.author.send(response) if is_private else await message.channel.send(response)
    except Exception as e:
        print(e)
    
# Startup for the bot
@client.event
async def on_ready() -> None:
    print(f'{client.user} is now running')

@client.event
async def on_message(message: Message) -> None:
    if message.author == client.user:
        return
    
    username: str = str(message.author)
    user_message: str = message.content
    channel: str = str(message.channel)
    target_channel_name = "poi-🐡"
    # Check if the message is in the target channel
    print(f'[{channel}] {username}: "{user_message}"')
    await read_channel_history(target_channel_name)
    if str(message.channel) == target_channel_name:
        # Check if the message is not the emoji :poi:
        if message.content != "<:poi:1284209602711392337>":
            print("Deleteing non-poi message in poi channel")
            await message.delete()  # Delete the message
            return
    if channel == "Direct Message with Unknown User":
        return
    if username == "q7lin": # Blocked him from using the bot
        return
    await send_message(message, user_message)

async def read_channel_history(channel_name: str, limit: int = 100):
    # Find the channel by name
    channel = utils.get(client.get_all_channels(), name=channel_name)
    
    if channel is not None:
        # Fetch the message history
        async for message in channel.history(limit=limit):
            # print(f'{message.author}: {message.content}')
            if message.content != "<:poi:1284209602711392337>":
                await message.delete()  # Delete the message
    else:
        print(f'Channel "{channel_name}" not found.')

# Main entry point
def main() -> None:
    client.run(token=TOKEN)

if __name__ == '__main__':
    main()
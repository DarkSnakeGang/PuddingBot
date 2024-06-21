import openai
from typing import Final
import os 

API_KEY: Final[str] = os.getenv('API_KEY')

openai.api_key = API_KEY
openai.base_url = "https://api.pawan.krd/v1/"

def chat_with_gpt(prompt, context):

    context.append({"role": "user", "content": prompt})
    
    try:
        response = openai.chat.completions.create(
        model="pai-001",
        messages=context
        )
        context.append({"role": "assistant", "content": response})
    except openai.RateLimitError:
        return "Sorry, ChatGPT usage is rate limited by OpenAI"

    return response.choices[0].message.content.strip()

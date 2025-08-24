import requests
import json
from typing import Final
import os 

OLLAMA_URL = "http://localhost:11434/api/generate"

def chat_with_gpt(prompt, context):
    """
    Send a request to Ollama for AI response
    """
    # Prepare the full conversation context
    messages = []
    
    # Add system message from context
    if context and len(context) > 0:
        messages.append(context[0])  # System message
    
    # Add user message
    messages.append({"role": "user", "content": prompt})
    
    # Prepare the request payload for Ollama
    payload = {
        "model": "llama3.2:3b",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 1000
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        # Extract the response text
        if 'response' in result:
            return result['response'].strip()
        else:
            return "Sorry, I couldn't generate a response at the moment."
            
    except requests.exceptions.RequestException as e:
        return f"Sorry, there was an error connecting to the AI service: {str(e)}"
    except json.JSONDecodeError:
        return "Sorry, there was an error processing the AI response."
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

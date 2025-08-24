import requests
import json
from typing import Final
import os 

OLLAMA_URL = "http://localhost:11434/api/generate"

def chat_with_gpt(messages):
    """
    Send a request to Ollama for AI response with full conversation context
    """
    # Build the full context by combining all messages
    full_context = ""
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            full_context += f"System: {content}\n\n"
        elif role == "user":
            full_context += f"User: {content}\n\n"
        elif role == "assistant":
            full_context += f"Assistant: {content}\n\n"
    
    # Debug: Print what we're sending to Ollama
    print(f"[DEBUG] Full context being sent: {full_context}")
    
    # Prepare the request payload for Ollama with full context
    payload = {
        "model": "llama3.2:3b",
        "prompt": full_context,  # Include the full conversation context
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "num_predict": 2048
        }
    }
    
    # Retry up to 3 times if model is still loading
    for attempt in range(3):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # Debug: Print the actual response structure
            print(f"[DEBUG] Ollama response: {result}")
            
            # Check if model is still loading
            if result.get('done_reason') == 'load':
                print(f"[DEBUG] Model still loading, attempt {attempt + 1}/3")
                if attempt < 2:  # Don't sleep on last attempt
                    import time
                    time.sleep(2)
                    continue
                else:
                    return "Sorry, the AI model is still loading. Please try again in a moment."
            
            # Extract the response text
            if 'response' in result and result['response'].strip():
                return result['response'].strip()
            else:
                print(f"[DEBUG] No 'response' field found or empty response. Available keys: {list(result.keys())}")
                return "Sorry, I couldn't generate a response at the moment."
                
        except requests.exceptions.RequestException as e:
            return f"Sorry, there was an error connecting to the AI service: {str(e)}"
        except json.JSONDecodeError:
            return "Sorry, there was an error processing the AI response."
        except Exception as e:
            return f"An unexpected error occurred: {str(e)}"
    
    return "Sorry, the AI model is not ready yet. Please try again."

#!/usr/bin/env python3
"""
Test script to verify Ollama integration
"""
import requests
import json
import time

def test_ollama_connection():
    """Test if Ollama is running and responding"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            print("✅ Ollama is running and responding")
            return True
        else:
            print(f"❌ Ollama responded with status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to Ollama: {e}")
        return False

def test_ollama_generation():
    """Test if Ollama can generate responses"""
    try:
        payload = {
            "model": "llama3.2:3b",
            "prompt": "Hello! Can you respond with a simple greeting?",
            "stream": False,
            "options": {
                "temperature": 0.7,
                "max_tokens": 100
            }
        }
        
        response = requests.post("http://localhost:11434/api/generate", 
                               json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        if 'response' in result:
            print("✅ Ollama generated a response successfully")
            print(f"Response: {result['response'][:100]}...")
            return True
        else:
            print("❌ Ollama response did not contain 'response' field")
            return False
            
    except Exception as e:
        print(f"❌ Error testing Ollama generation: {e}")
        return False

def main():
    print("Testing Ollama integration...")
    print("=" * 40)
    
    # Test connection
    if not test_ollama_connection():
        print("\n❌ Ollama connection test failed. Make sure Ollama is running.")
        return False
    
    # Test generation
    if not test_ollama_generation():
        print("\n❌ Ollama generation test failed.")
        return False
    
    print("\n✅ All tests passed! Ollama integration is working correctly.")
    return True

if __name__ == "__main__":
    main()

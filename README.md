# PuddingBot with Ollama Integration

PuddingBot is a Discord bot designed for the Google Snake gaming community, now featuring local AI processing using Ollama instead of external APIs.

## Features

- **Discord Integration**: Full Discord bot functionality with message handling
- **Local AI Processing**: Uses Ollama for AI responses (no external API dependencies)
- **Google Snake Expertise**: Extensive knowledge about Google Snake mechanics, speedrunning, and community
- **Wall Pattern Solver**: Advanced algorithm to solve wall patterns in Google Snake
- **GIF Responses**: Tenor API integration for animated responses
- **Channel Management**: Special handling for specific Discord channels

## Prerequisites

- Docker installed on your system
- Discord bot token (set in environment variables)

## Quick Start

1. **Set up environment variables**:
   Create a `.env` file in the project root:
   ```
   DISCORD_TOKEN=your_discord_bot_token_here
   TENOR_KEY=your_tenor_api_key_here
   ```

2. **Build and run with Docker**:
   ```bash
   # Build the Docker image
   docker build -t puddingbot .
   
   # Run in background
   docker run -d --name puddingbot-container puddingbot
   
   # Or run in foreground to see logs
   docker run --name puddingbot-container puddingbot
   ```

3. **Check logs**:
   ```bash
   docker logs puddingbot-container
   ```

## Docker Setup

The Docker container includes:
- **Ubuntu 22.04** base image
- **Ollama** for local AI processing
- **Python 3** with all required dependencies
- **llama3.2:3b** model (automatically downloaded during build)

## AI Integration

The bot now uses Ollama for AI responses instead of external APIs:
- **Model**: llama3.2:3b (good balance of performance and resource usage)
- **Local Processing**: All AI responses are generated locally
- **No External Dependencies**: No need for OpenAI API keys or external services

## Commands

- `@PuddingBot <message>` - Get AI response
- `@PuddingBot clear context` - Clear conversation context
- `gif <emotion>` - Get a random GIF
- `roll dice` - Roll a 6-sided die
- `pattern <pattern_string>` - Solve a wall pattern

## File Structure

- `main.py` - Main Discord bot logic
- `responses.py` - Response generation and command handling
- `gpt.py` - Ollama AI integration
- `wall.py` - Wall pattern solving algorithm
- `Dockerfile` - Docker configuration with Ollama
- `requirements.txt` - Python dependencies

## Troubleshooting

1. **Ollama not starting**: Check Docker logs for Ollama startup issues
2. **Model not found**: The build process should automatically download the model
3. **Discord connection issues**: Verify your Discord token is correct
4. **Memory issues**: The llama3.2:3b model requires ~2GB RAM

## Development

To test the Ollama integration locally:
```bash
python3 test_ollama.py
```

## Notes

- The bot will automatically start Ollama and wait for it to be ready before starting the Discord bot
- All AI responses are generated locally, so no internet connection is required for AI functionality
- The container includes proper error handling and graceful shutdown

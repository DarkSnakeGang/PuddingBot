# PuddingBot with Ollama Integration

PuddingBot is a Discord bot designed for the Google Snake gaming community, now featuring local AI processing using Ollama instead of external APIs.

## Features

- **Discord Integration**: Full Discord bot functionality with message handling
- **Local AI Processing**: Uses Ollama for AI responses (no external API dependencies)
- **Google Snake Expertise**: Extensive knowledge about Google Snake mechanics, speedrunning, and community
- **Wall Pattern Solver**: Advanced algorithm to solve wall patterns in Google Snake
- **GIF Responses**: KLIPY API integration for animated responses
- **Channel Management**: Special handling for specific Discord channels

## Prerequisites

- Docker installed on your system
- Discord bot token (set in environment variables)

## Quick Start

1. **Set up environment variables**:
   Create a `.env` file in the project root:
   ```
   DISCORD_TOKEN=your_discord_bot_token_here
   BOT_OWNER_ID=your_discord_user_id
   KLIPY_KEY=your_klipy_api_key_here
   ```
   `BOT_OWNER_ID` is the only user allowed to run `/update`. See
   [Configuration](#configuration) for optional settings.

2. **Build and run with Docker**:
   ```bash
   # From repo root (or use the helper scripts)
   ./scripts/run_docker.sh
   # Windows: scripts\run_docker.bat

   # Or manually:
   docker build -t puddingbot .
   docker run -d --name puddingbot-container --restart unless-stopped \
     --env-file .env -v ollama_models:/root/.ollama \
     -v "$(pwd)/.env:/app/.env:ro" puddingbot
   ```
   The `ollama_models` volume keeps the downloaded model across rebuilds.
   `.env` is excluded from the image (`.dockerignore`) and mounted at runtime.

3. **Check logs**:
   ```bash
   docker logs puddingbot-container
   ```

## Docker Setup

The Docker container includes:
- **Ubuntu 22.04** base image
- **Ollama** for local AI processing
- **Python 3** with all required dependencies
- **qwen3:0.6b** model (automatically downloaded on start; override with `OLLAMA_MODEL`)

## Configuration

Optional `.env` settings (defaults in parentheses):

| Variable | Purpose |
| --- | --- |
| `POI_CHANNEL_ID` | Channel where only poi emoji are allowed |
| `OLLAMA_MODEL` | Chat model (`qwen3:0.6b`) |
| `WALL_SOLVE_SECONDS` | Hard time cap for one wall solve (`180`) |
| `WALL_MAX_SOLVES` | Concurrent wall solves before replying "busy" (`2`) |
| `AUTO_UPDATE_ENABLED` / `AUTO_UPDATE_MINUTES` | Poll GitHub and self-update (`1` / `30`) |
| `REPO_WATCH_ENABLED` / `REPO_WATCH_MINUTES` | Mod repo update digest (`1` / `720`) |
| `DM_UPLOAD_LIMIT_BYTES` | Largest file the DM media grabber downloads (10 MiB) |
| `MKV_UPLOAD_LIMIT_BYTES` | Override the server upload limit for MKV→MP4 |

## AI Integration

The bot now uses Ollama for AI responses instead of external APIs:
- **Model**: qwen3:0.6b (fastest current tools-capable Qwen3; thinking disabled for latency)
- **Local Processing**: All AI responses are generated locally
- **No External Dependencies**: No need for OpenAI API keys or external services

## Commands

- `@PuddingBot <message>` - Get AI response
- `@PuddingBot clear context` - Clear conversation context
- `gif <emotion>` - Get a random GIF
- `roll dice` - Roll a 6-sided die
- `pattern <90-cell grid>` - Solve a wall pattern (pudding clipboard paste works as-is)
- `/wallall` - Same Wall All solver via slash command

## File Structure

```text
/
  main.py, start.sh, Dockerfile, requirements.txt
  data_management.py, github_cache_fetcher.py
  chat/          Message replies and Ollama AI
  cogs/          Discord slash/context command extensions
  wall/          Wall All solver, renderer, Discord stream updates
  native/        C Warnsdorff DFS extension (warnsdorff_c)
  tests/         Local smoke tests
  scripts/       Docker helper scripts
  assets/        Memes, fonts, GIFs
```

Wall All path search uses the native C DFS when `warnsdorff_c` is installed
(built in Docker; falls back to pure Python otherwise). Force Python with
`HAMPATH_DFS=python`.

## Troubleshooting

1. **Ollama not starting**: Check Docker logs for Ollama startup issues
2. **Model not found**: The build process should automatically download the model
3. **Discord connection issues**: Verify your Discord token is correct
4. **Memory issues**: The qwen3:0.6b model needs roughly ~1GB RAM

## Development

Offline unit tests (no network or Discord needed):
```bash
pip install pytest
python3 -m pytest tests/unit
```

Live smoke tests (need network; the Ollama one needs a running Ollama):
```bash
python3 tests/test_fastsnakestats.py
python3 tests/test_ollama.py
```

## Notes

- The bot will automatically start Ollama and wait for it to be ready before starting the Discord bot
- AI responses are generated locally; the bot adds live web search results to each prompt
- The container includes proper error handling and graceful shutdown

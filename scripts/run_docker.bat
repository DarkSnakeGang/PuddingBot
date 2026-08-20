@echo off
cd /d "%~dp0.."

if exist .env\ (
  echo ERROR: .env is a directory. Delete it and create a real .env file first.
  exit /b 1
)
if not exist .env (
  echo ERROR: .env file not found in %cd%
  echo Create a .env file with DISCORD_TOKEN, BOT_OWNER_ID, and KLIPY_KEY
  exit /b 1
)

echo Building Docker image...
docker build -t puddingbot .

echo Stopping and removing existing container...
docker rm -f puddingbot-container 2>nul

echo Running PuddingBot with persistent Ollama models and .env...
docker run -d --name puddingbot-container --restart unless-stopped --env-file "%cd%\.env" -v ollama_models:/root/.ollama -v "%cd%\.env:/app/.env:ro" puddingbot

echo Container started! Check logs with: docker logs puddingbot-container
docker logs puddingbot-container

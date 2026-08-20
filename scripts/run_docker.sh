#!/bin/bash
set -e

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  if [ -d .env ]; then
    echo "ERROR: .env is a directory (Docker created it because the file was missing)."
    echo "Fix with:  docker rm -f puddingbot-container; rm -rf .env"
    echo "Then create a real .env file and run this script again."
    exit 1
  fi
  echo "ERROR: .env file not found in $(pwd)"
  echo "Create .env with DISCORD_TOKEN, BOT_OWNER_ID, KLIPY_KEY first."
  exit 1
fi

if ! grep -q '^DISCORD_TOKEN=' .env; then
  echo "ERROR: DISCORD_TOKEN is missing from .env"
  exit 1
fi

echo "Building Docker image..."
docker build -t puddingbot .

echo "Stopping and removing existing container..."
docker rm -f puddingbot-container 2>/dev/null || true

echo "Running PuddingBot with persistent Ollama models and .env..."
docker run -d \
  --name puddingbot-container \
  --restart unless-stopped \
  --env-file "$(pwd)/.env" \
  -v ollama_models:/root/.ollama \
  -v "$(pwd)/.env:/app/.env:ro" \
  puddingbot

echo "Container started! Check logs with: docker logs puddingbot-container"
docker logs puddingbot-container

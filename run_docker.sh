#!/bin/bash
set -e

echo "Building Docker image..."
docker build -t puddingbot .

echo "Stopping and removing existing container..."
docker rm -f puddingbot-container 2>/dev/null || true

echo "Running PuddingBot with persistent Ollama models and mounted .env..."
docker run -d \
  --name puddingbot-container \
  --restart unless-stopped \
  -v ollama_models:/root/.ollama \
  -v "$(pwd)/.env:/app/.env" \
  puddingbot

echo "Container started! Check logs with: docker logs puddingbot-container"
docker logs puddingbot-container

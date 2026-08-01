#!/bin/bash
set -e

REPO_URL="${GIT_REPO_URL:-https://github.com/DarkSnakeGang/PuddingBot.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
RESTART_EXIT_CODE=42

# Allow git operations when running as root inside Docker
git config --global --add safe.directory /app

# First run: connect /app to the remote repo so /update can git pull later
if [ ! -d /app/.git ]; then
    echo "First run: initializing git repository in /app..."
    cd /app
    git init
    git remote add origin "$REPO_URL"
    git fetch origin "$GIT_BRANCH"
    git checkout -B "$GIT_BRANCH" "origin/$GIT_BRANCH"
    echo "Repository initialized at $(git rev-parse --short HEAD)"
fi

echo "Starting Ollama..."
ollama serve &
OLLAMA_PID=$!

echo "Waiting for Ollama to be ready..."
sleep 10

for i in {1..30}; do
    if curl -s http://localhost:11434/api/tags > /dev/null; then
        echo "Ollama is ready!"
        break
    fi
    echo "Waiting for Ollama... (attempt $i/30)"
    sleep 2
done

if ollama list | grep -q "llama3.2:3b"; then
    echo "Model llama3.2:3b already exists, skipping download!"
else
    echo "Downloading llama3.2:3b model..."
    ollama pull llama3.2:3b
    echo "Model downloaded successfully!"
fi

echo "Starting Discord bot (update restart loop enabled)..."
BOT_EXIT_CODE=0
while true; do
    python3 -u main.py
    BOT_EXIT_CODE=$?
    if [ "$BOT_EXIT_CODE" -eq "$RESTART_EXIT_CODE" ]; then
        echo "Update restart requested, reloading bot..."
        continue
    fi
    break
done

echo "Discord bot stopped with code $BOT_EXIT_CODE. Shutting down Ollama..."
kill "$OLLAMA_PID"
wait "$OLLAMA_PID"
echo "Shutdown complete."
exit "$BOT_EXIT_CODE"

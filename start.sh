#!/bin/bash
set -e

REPO_URL="${GIT_REPO_URL:-https://github.com/DarkSnakeGang/PuddingBot.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
RESTART_EXIT_CODE=42
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:8b}"

# Allow git operations when running as root inside Docker
git config --global --add safe.directory /app

# First run: connect /app to the remote repo so /update can sync later
if [ ! -d /app/.git ]; then
    echo "First run: initializing git repository in /app..."
    cd /app
    git init
    git remote add origin "$REPO_URL"
    git fetch origin "$GIT_BRANCH"
    # Force match remote even if Docker COPY left untracked files in /app
    git checkout -f -B "$GIT_BRANCH" "origin/$GIT_BRANCH"
    git clean -fd -e .env -e '.env.*'
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

if ollama list | grep -q "${OLLAMA_MODEL}"; then
    echo "Model ${OLLAMA_MODEL} already exists, skipping download!"
else
    echo "Downloading ${OLLAMA_MODEL} model (this can take a while)..."
    ollama pull "${OLLAMA_MODEL}"
    echo "Model downloaded successfully!"
fi

echo "Starting Discord bot (update restart loop enabled)..."
BOT_EXIT_CODE=0
while true; do
    # Ensure configured model exists (covers /update model changes without full container rebuild)
    if ! ollama list 2>/dev/null | grep -q "${OLLAMA_MODEL}"; then
        echo "Ollama model ${OLLAMA_MODEL} missing — pulling before starting bot..."
        ollama pull "${OLLAMA_MODEL}" || echo "Warning: failed to pull ${OLLAMA_MODEL}"
    fi

    python3 -u main.py
    BOT_EXIT_CODE=$?
    if [ "$BOT_EXIT_CODE" -eq "$RESTART_EXIT_CODE" ]; then
        echo "Update restart requested, reloading bot..."
        continue
    fi
    echo "Discord bot stopped with code $BOT_EXIT_CODE. Retrying in 5s..."
    sleep 5
done

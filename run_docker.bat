@echo off
echo Stopping and removing existing container...
docker rm -f puddingbot-container 2>nul

echo Building Docker image...
docker build -t puddingbot .

echo Running PuddingBot with persistent Ollama models...
docker run -d --name puddingbot-container -v ollama_models:/root/.ollama puddingbot

echo Container started! Check logs with: docker logs puddingbot-container
pause

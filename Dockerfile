# Use Ubuntu as base image for Ollama installation
FROM ubuntu:22.04

# Set environment variables to avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV OLLAMA_DEBUG=0

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.ai/install.sh | sh

# Set the working directory inside the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Create a startup script with better error handling and model persistence
RUN echo '#!/bin/bash\n\
set -e\n\
echo "Starting Ollama..."\n\
ollama serve &\n\
OLLAMA_PID=$!\n\
\n\
echo "Waiting for Ollama to be ready..."\n\
sleep 10\n\
\n\
# Test if Ollama is responding\n\
for i in {1..30}; do\n\
    if curl -s http://localhost:11434/api/tags > /dev/null; then\n\
        echo "Ollama is ready!"\n\
        break\n\
    fi\n\
    echo "Waiting for Ollama... (attempt $i/30)"\n\
    sleep 2\n\
done\n\
\n\
# Check if model already exists\n\
if ollama list | grep -q "llama3.2:3b"; then\n\
    echo "Model llama3.2:3b already exists, skipping download!"\n\
else\n\
    echo "Downloading llama3.2:3b model..."\n\
    ollama pull llama3.2:3b\n\
    echo "Model downloaded successfully!"\n\
fi\n\
\n\
echo "Starting Discord bot..."\n\
python3 -u main.py\n\
\n\
# If we get here, the bot has stopped\n\
echo "Discord bot stopped. Shutting down Ollama..."\n\
kill $OLLAMA_PID\n\
wait $OLLAMA_PID\n\
echo "Shutdown complete."' > /app/start.sh && chmod +x /app/start.sh

# Create volume for Ollama models
VOLUME ["/root/.ollama"]

# Make port 8080 available to the world outside this container (if needed)
EXPOSE 8080

# Run the startup script when the container launches
CMD ["/app/start.sh"]

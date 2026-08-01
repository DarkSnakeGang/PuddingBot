# Use Ubuntu as base image for Ollama installation
FROM ubuntu:22.04

# Set environment variables to avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV OLLAMA_DEBUG=0
ENV GIT_REPO_URL=https://github.com/DarkSnakeGang/PuddingBot.git
ENV GIT_BRANCH=main
ENV APP_DIR=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    zstd \
    ca-certificates \
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

# Startup script handles git init, Ollama, and bot restart loop
RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

# Create volume for Ollama models
VOLUME ["/root/.ollama"]

# Make port 8080 available to the world outside this container (if needed)
EXPOSE 8080

# Run the startup script when the container launches
CMD ["/app/start.sh"]

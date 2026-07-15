#!/bin/bash
set -e

# Start Ollama server in background
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done
echo "Ollama is ready."

# Pull required models
echo "Pulling embedding model: nomic-embed-text..."
ollama pull nomic-embed-text

echo "Pulling LLM model: qwen2.5:3b..."
ollama pull qwen2.5:3b

echo "Pulling vision model: llava-phi3:3.8b..."
ollama pull llava-phi3:3.8b

echo "All models loaded. Ollama is running."

# Keep container running
wait $OLLAMA_PID

FROM ollama/ollama:latest

# Pull the model during build
RUN ollama serve & sleep 5 && ollama pull llama3:8b-instruct-q4_0

EXPOSE 11434

CMD ["ollama", "serve"]
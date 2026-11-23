FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[ui]"
EXPOSE 8080
# Point OLLAMA_URL at your Ollama host, e.g. http://host.docker.internal:11434
CMD ["qa-copilot", "ui", "--port", "8080"]

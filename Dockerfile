# Multi-arch base image for Linux amd64 (CPU-only, no GPU required)
FROM --platform=linux/amd64 python:3.11-slim

# Set environment variables for performance and clean execution
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and essential configurations
COPY src/ /app/src/
COPY pyproject.toml README.md /app/

# Entrypoint directly invokes the main module
ENTRYPOINT ["python", "-m", "src.main"]

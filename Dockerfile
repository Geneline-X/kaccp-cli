# Python worker Dockerfile
FROM python:3.11-slim

# Install system deps: ffmpeg, yt-dlp
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Optional: install latest yt-dlp via pip (binary also ok)
RUN pip install --no-cache-dir yt-dlp==2025.1.26

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Expose worker API port
EXPOSE 8081

# Default command runs the API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]

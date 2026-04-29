FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates git \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
# Explicit install ensures yt-dlp and feedparser are present on VPS even if
# requirements.txt cache is stale (belt-and-suspenders for InterviewCollector)
RUN pip install --no-cache-dir "yt-dlp>=2024.10" "feedparser>=6.0"
RUN python -m playwright install --with-deps chromium

COPY src/ ./src/
COPY storytelling_bot.py ./

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

ENTRYPOINT ["python", "-m", "storytelling_bot"]
CMD ["--help"]

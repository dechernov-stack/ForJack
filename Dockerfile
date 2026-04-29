FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates git \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "yt-dlp>=2024.10" "feedparser>=6.0"
RUN python -m playwright install --with-deps chromium

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["storyteller"]
CMD ["--help"]

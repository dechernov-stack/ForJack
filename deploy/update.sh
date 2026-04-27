#!/usr/bin/env bash
# Runs on the VPS after every push to main.
# Called by GitHub Actions via SSH.
set -euo pipefail

INSTALL_DIR="/opt/storytelling-bot"
cd "$INSTALL_DIR"

echo "[deploy] pulling $(git rev-parse --short HEAD)..."
git pull --ff-only

echo "[deploy] updating python package..."
.venv/bin/pip install -q -e .

echo "[deploy] restarting docker services..."
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --no-build

# Reload systemd only if unit files changed
if git diff HEAD@{1} HEAD --name-only 2>/dev/null | grep -q "deploy/storyteller"; then
    echo "[deploy] reloading systemd units..."
    cp deploy/storyteller.service /etc/systemd/system/
    cp deploy/storyteller.timer   /etc/systemd/system/
    systemctl daemon-reload
    systemctl restart storyteller.timer
fi

echo "[deploy] done: $(git rev-parse --short HEAD)"

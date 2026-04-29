#!/usr/bin/env bash
# One-shot VPS setup for storytelling-bot.
# Run as root on a fresh Ubuntu 24.04 machine.
set -euo pipefail

REPO_URL="git@github.com:dechernov-stack/ForJack.git"
INSTALL_DIR="/opt/storytelling-bot"
APP_USER="storyteller"

# ── 1. System packages ────────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y -qq \
    docker.io docker-compose-v2 \
    python3-pip python3-venv \
    git apache2-utils \
    ffmpeg          # required by yt-dlp / faster-whisper

systemctl enable --now docker

# ── 2. App user ───────────────────────────────────────────────────────────────
id -u "$APP_USER" &>/dev/null || useradd -r -s /bin/bash -d "$INSTALL_DIR" "$APP_USER"
usermod -aG docker "$APP_USER"

# ── 3. Clone repo ─────────────────────────────────────────────────────────────
git clone "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || \
    git -C "$INSTALL_DIR" pull --ff-only

chown -R "$APP_USER:$APP_USER" "$INSTALL_DIR"

# ── 4. .env ───────────────────────────────────────────────────────────────────
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ""
    echo "⚠️  Fill in $INSTALL_DIR/.env before continuing (API keys, WATCHLIST_ENTITIES, etc.)"
    echo "   nano $INSTALL_DIR/.env"
    exit 0
fi

# ── 5. Python package ─────────────────────────────────────────────────────────
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install -q -e "$INSTALL_DIR[dev]"

# Add venv bin to PATH for storyteller CLI
ln -sf "$INSTALL_DIR/.venv/bin/storyteller" /usr/local/bin/storyteller

# ── 6. nginx basic auth password ──────────────────────────────────────────────
HTPASSWD_FILE="$INSTALL_DIR/deploy/.htpasswd"
if [[ ! -f "$HTPASSWD_FILE" ]]; then
    echo ""
    read -rp "Set nginx username [admin]: " NGINX_USER
    NGINX_USER="${NGINX_USER:-admin}"
    htpasswd -c "$HTPASSWD_FILE" "$NGINX_USER"
fi

# ── 7. Docker Compose (infra + nginx) ─────────────────────────────────────────
cd "$INSTALL_DIR"
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d

# ── 8. systemd units ──────────────────────────────────────────────────────────
cp deploy/storyteller.service /etc/systemd/system/
cp deploy/storyteller.timer   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now storyteller.timer

echo ""
echo "✅ Done."
echo "   Langfuse → http://$(curl -s ifconfig.me):8080"
echo "   MinIO    → http://$(curl -s ifconfig.me):8081"
echo "   Logs     → journalctl -u storyteller -f"
echo "   Run now  → systemctl start storyteller"

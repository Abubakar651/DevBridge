#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Abubakar651/DevBridge.git}"
APP_DIR="${APP_DIR:-/opt/devbridge}"
APP_USER="${SUDO_USER:-ubuntu}"

sudo apt-get update
sudo apt-get install -y python3-venv python3-pip git caddy

sudo mkdir -p "$APP_DIR"
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only origin main
else
  git clone "$REPO_URL" "$APP_DIR"
fi

if [ ! -d "$APP_DIR/.venv" ]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi

sudo cp "$APP_DIR/deploy/devbridge.service" /etc/systemd/system/devbridge.service
sudo systemctl daemon-reload

cat <<EOF

DevBridge setup finished in $APP_DIR.

Next steps on this EC2 instance:
1. Edit secrets and ALLOWED_HOSTS in $APP_DIR/.env:
   - GEMINI_API_KEY, GROQ_API_KEY (and optional GROQ_API_KEY2, OPENROUTER_API_KEY)
   - ALLOWED_HOSTS=your-domain.example.com
   - RATE_LIMIT_PER_MINUTE=30
   - Optional shared-demo token: DEMO_ACCESS_TOKEN=...
2. Copy deploy/Caddyfile to /etc/caddy/Caddyfile and replace devbridge.example.com with your domain:
   sudo cp $APP_DIR/deploy/Caddyfile /etc/caddy/Caddyfile && sudo nano /etc/caddy/Caddyfile
3. Start DevBridge and reload Caddy:
   sudo systemctl enable --now devbridge
   sudo systemctl reload caddy
EOF

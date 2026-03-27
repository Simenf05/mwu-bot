#!/usr/bin/env bash
set -euo pipefail

# Simple cross-distro installer for systemd-based systems.
# Installs the bot into /opt/mwu-bot and sets up a service.

APP_DIR=/opt/mwu-bot
SERVICE_NAME=mwu-bot.service
SERVICE_SRC=packaging/mwu-bot.service
PYTHON_BIN=${PYTHON_BIN:-python3}
USER_NAME=${USER_NAME:-mwu}
GROUP_NAME=${GROUP_NAME:-$USER_NAME}

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo $0) or (doas $0)" >&2
  exit 1
fi

run_as_user() {
  local user=$1
  shift

  if command -v runuser >/dev/null 2>&1; then
    runuser -u "$user" -- "$@"
    return $?
  fi

  if command -v sudo >/dev/null 2>&1; then
    sudo -u "$user" -- "$@"
    return $?
  fi

  # Last resort. Requires a valid shell for the user.
  su -s /bin/sh -c "$(printf "%q " "$@")" "$user"
}

echo "[*] Ensuring user '$USER_NAME' exists..."
if ! id "$USER_NAME" &>/dev/null; then
  useradd -r -s /usr/sbin/nologin "$USER_NAME" || useradd -r -s /bin/false "$USER_NAME"
fi

echo "[*] Creating app directory at $APP_DIR..."
mkdir -p "$APP_DIR"
chown -R "$USER_NAME":"$GROUP_NAME" "$APP_DIR"

echo "[*] Copying project files into $APP_DIR..."
rsync -a --delete \
  bot scripts main.py implementation_plan.md requirements.txt README.md \
  "$APP_DIR"/

echo "[*] Creating virtualenv and installing dependencies..."
cd "$APP_DIR"
run_as_user "$USER_NAME" "$PYTHON_BIN" -m venv .venv
run_as_user "$USER_NAME" .venv/bin/pip install --upgrade pip
run_as_user "$USER_NAME" .venv/bin/pip install -r requirements.txt

if [[ ! -f "$APP_DIR/.env" ]]; then
  cat > "$APP_DIR/.env" << 'EOF'
# Fill in your real keys/secrets:
POLYGON_API_KEY=CHANGE_ME
ALPACA_KEY_ID=CHANGE_ME
ALPACA_SECRET_KEY=CHANGE_ME
ALPACA_PAPER=true
EOF
  chown "$USER_NAME":"$GROUP_NAME" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "[*] Created skeleton $APP_DIR/.env – edit it with your API keys."
fi

echo "[*] Installing systemd unit..."
cp "$SERVICE_SRC" "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

echo "[*] Installation complete."
echo "  - Edit $APP_DIR/.env with your real keys."
echo "  - Check logs with: journalctl -u $SERVICE_NAME -f"


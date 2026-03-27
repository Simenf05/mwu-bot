#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/mwu-bot
SERVICE_NAME=mwu-bot.service
SERVICE_PATH=/etc/systemd/system/$SERVICE_NAME
USER_NAME=${USER_NAME:-mwu}
GROUP_NAME=${GROUP_NAME:-$USER_NAME}

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo $0) or (doas $0)" >&2
  exit 1
fi

echo "[*] Stopping and disabling systemd unit (if present)..."
if systemctl list-unit-files | grep -q "^$SERVICE_NAME"; then
  systemctl stop "$SERVICE_NAME" || true
  systemctl disable "$SERVICE_NAME" || true
fi

echo "[*] Removing systemd unit file (if present)..."
if [[ -f "$SERVICE_PATH" ]]; then
  rm -f "$SERVICE_PATH"
  systemctl daemon-reload
fi

echo "[*] Removing application directory at $APP_DIR (if present)..."
if [[ -d "$APP_DIR" ]]; then
  rm -rf "$APP_DIR"
fi

echo "[*] Optionally removing dedicated user '$USER_NAME' (if unused)..."
if id "$USER_NAME" &>/dev/null; then
  if [[ -z "$(id -nG "$USER_NAME" | tr ' ' '\n' | grep -v "^$GROUP_NAME$")" ]]; then
    userdel "$USER_NAME" || true
  else
    echo "  - Skipping userdel for '$USER_NAME' because it belongs to other groups."
  fi
fi

echo "[*] Uninstall complete."


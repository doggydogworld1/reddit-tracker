#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/code/reddit-tracker}"
SERVICE_DIR="$REPO_DIR/dd-tracker"
SYSTEMD_USER_DIR="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"

cd "$SERVICE_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created $SERVICE_DIR/.env; add Reddit and market-data credentials to enable jobs."
fi

mkdir -p "$SYSTEMD_USER_DIR"
cp deploy/reddit-dd-tracker.service "$SYSTEMD_USER_DIR/"
systemctl --user daemon-reload
systemctl --user enable reddit-dd-tracker.service
systemctl --user restart reddit-dd-tracker.service

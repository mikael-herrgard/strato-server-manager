#!/bin/bash
# Server Manager - Quick Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/USER/server-manager/main/bootstrap/install.sh | bash
set -e

REPO_URL="${REPO_URL:-https://github.com/USER/server-manager}"
BRANCH="${BRANCH:-main}"
BOOTSTRAP_URL="https://raw.githubusercontent.com/USER/server-manager/${BRANCH}/bootstrap/bootstrap.sh"

echo "==> Downloading Server Manager bootstrap script..."
curl -fsSL "$BOOTSTRAP_URL" -o /tmp/sm-bootstrap.sh || {
    echo "ERROR: Failed to download bootstrap script"
    exit 1
}

chmod +x /tmp/sm-bootstrap.sh
echo "==> Executing bootstrap script..."
exec /tmp/sm-bootstrap.sh "$@"

#!/bin/bash
# wine_fix.sh — Upgrade Wine at runtime for MT5 IPC support.
#
# Must run AFTER MT5 is connected via VNC auto-login on Wine 7.0.
# The runtime upgrade + wineserver -k gives a clean IPC handshake
# that doesn't work when Wine is upgraded at build time.
#
set -e

CURRENT=$(wine --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+' | head -1)
MAJOR=${CURRENT%%.*}

if [ "$MAJOR" -ge 10 ] 2>/dev/null; then
    echo "wine_fix: Wine $CURRENT already >= 10.0, skipping upgrade."
    exit 0
fi

echo "wine_fix: Wine $CURRENT detected — upgrading to Wine 10.0..."

# The base image already has the WineHQ repo configured.
# Remove any conflicting sources we may have added previously.
rm -f /etc/apt/sources.list.d/winehq.list

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --allow-downgrades winehq-stable

apt-get clean && rm -rf /var/lib/apt/lists/*

echo "wine_fix: Upgrade complete — $(wine --version 2>/dev/null)"

# Kill the old wineserver — all Wine processes restart with new Wine.
# This gives a clean IPC handshake when mt5.initialize() runs next.
wineserver -k 2>/dev/null || true
sleep 2

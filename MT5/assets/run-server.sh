#!/bin/sh

export WINEPREFIX="${WINEPREFIX:-/opt/wineprefix}"
export DISPLAY="${DISPLAY:-:0}"

# The MT5 Python IPC is reliable only after the terminal GUI auto-login
# sequence has dismissed blocking dialogs and created this marker.
LOGIN_MARKER="/tmp/login_complete"
echo "Waiting for MT5 auto-login marker..."
while [ ! -f "$LOGIN_MARKER" ]; do
    sleep 2
done
echo "MT5 auto-login marker found. Starting FastAPI Server..."
cd $HOME/api
exec wine python -m app

#!/bin/sh

# Wait for auto-login to complete (VNC login done, MT5 connected)
LOGIN_MARKER="/tmp/login_complete"

echo "Waiting for auto-login to complete..."
while [ ! -f "$LOGIN_MARKER" ]; do
    sleep 2
done
echo "Auto-login marker found."

# Start the server
echo "Starting FastAPI Server..."
cd $HOME/api
wine python -m app

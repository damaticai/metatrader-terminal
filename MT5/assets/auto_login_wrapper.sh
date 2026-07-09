#!/bin/bash
# Wrapper: runs VNC auto-login under Wine, then creates the marker
# file for the API server. No wineserver kill needed — the connector
# passes credentials to mt5.initialize() directly.

LOG=/tmp/auto_login.log

# Wait for VNC to be ready
echo "Waiting for VNC server..."
for i in $(seq 1 30); do
    if bash -c "echo > /dev/tcp/localhost/5900" 2>/dev/null; then
        echo "VNC ready after ${i}s"
        break
    fi
    sleep 1
done

# Run auto-login in background, capture output.
# wine python hangs after script completes (wineserver keeps it alive),
# so we watch the log for the completion message.
wine python /root/auto_login.py > $LOG 2>&1 &
WINE_PID=$!

# Wait for completion message or timeout (180s)
# Login takes ~20s + 30s LiveUpdate wait = ~50s minimum
echo "Waiting for auto-login to complete..."
for i in $(seq 1 90); do
    if grep -q "Auto-login sequence completed" $LOG 2>/dev/null; then
        echo "Auto-login succeeded."
        echo "1" > /tmp/login_complete
        echo "Marker created."
        exit 0
    fi
    if grep -q "An error occurred" $LOG 2>/dev/null; then
        echo "Auto-login failed:"
        cat $LOG
        exit 1
    fi
    sleep 2
done

echo "Auto-login timed out after 180s"
cat $LOG
exit 1

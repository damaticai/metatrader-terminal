#!/bin/bash

# 0. Clean up stale state from previous runs (e.g. docker restart)
#    - login marker: forces auto-login to re-run and dismiss LiveUpdate popup
#    - X11 lock/socket: prevents VNC from failing with "display already in use"
rm -f /tmp/login_complete /tmp/.X0-lock
rm -f /tmp/.X11-unix/X0 2>/dev/null

# Ensure algo trading is enabled in the MT5 config.
# The terminal disables it on account changes and persists Enabled=0.
# This re-enables it before the terminal starts.
MT5_COMMON="${WINEPREFIX:-/opt/wineprefix}/drive_c/Metatrader-5/Config/common.ini"
if [ -f "$MT5_COMMON" ]; then
    python3 -c "
import sys
data = open('$MT5_COMMON', 'rb').read()
patched = data.replace(b'E\x00n\x00a\x00b\x00l\x00e\x00d\x00=\x000\x00', b'E\x00n\x00a\x00b\x00l\x00e\x00d\x00=\x001\x00', 1)
if patched != data:
    open('$MT5_COMMON', 'wb').write(patched)
    print('==> Algo trading re-enabled in common.ini')
"
fi

# 1. Initialize Authentication (Must happen BEFORE Nginx starts)
if [ -f /root/vnc-auth.sh ]; then
    chmod +x /root/vnc-auth.sh
    /root/vnc-auth.sh
else
    echo "==> WARNING: /root/vnc-auth.sh not found. skipping auth initialization."
fi

# 2. Start supervisord using exec to ensure it is PID 1
echo "==> Starting services via supervisor..."
exec /usr/bin/supervisord -c /etc/supervisord.conf

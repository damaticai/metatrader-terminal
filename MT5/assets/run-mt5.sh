#!/bin/bash

# Only install if not already present
if [ ! -f "/opt/wineprefix/drive_c/Metatrader-5/terminal64.exe" ]; then
    echo "MetaTrader 5 not found. Starting installation..."

    # MetaTrader download url
    URL="https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"
    # WebView2 Runtime download url
    URL_WEBVIEW="https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/c1336fd6-a2eb-4669-9b03-949fc70ace0e/MicrosoftEdgeWebview2Setup.exe"

    # Download
    wget -q $URL
    wget -q $URL_WEBVIEW

    # Set environment to Windows 10
    winecfg -v=win11

    # Install WebView2
    wine MicrosoftEdgeWebview2Setup.exe /silent /install
    wineserver -w

    # Install MT5
    wine mt5setup.exe /auto /path:"C:\Metatrader-5"
    wineserver -w

    # Disable LiveUpdate immediately after install (before any launch)
    # to prevent terminal from auto-updating to a build newer than
    # the MetaTrader5 Python library (5.0.5640 on PyPI).
    MT5_CFG_DIR="/opt/wineprefix/drive_c/Metatrader-5/Config"
    mkdir -p "$MT5_CFG_DIR"
    { printf '\xFF\xFE'; printf '[LiveUpdate]\r\nLiveUpdateMode=2\r\n' | iconv -f UTF-8 -t UTF-16LE; } > "$MT5_CFG_DIR/terminal.ini"
    { printf '\xFF\xFE'; printf '[Experts]\r\nEnabled=1\r\n' | iconv -f UTF-8 -t UTF-16LE; } > "$MT5_CFG_DIR/common.ini"
    echo "LiveUpdate disabled and algo trading enabled."

    # Clean up
    rm mt5setup.exe MicrosoftEdgeWebview2Setup.exe
else
    echo "MetaTrader 5 already installed."
fi

# Run MT5 (Skip if in BUILD_MODE)
if [ "$BUILD_MODE" = "1" ]; then
    echo "Metatrader 5 installed successfully (Build Mode). Skipping launch."
    exit 0
fi

# Keep MT5 alive — restart it whenever it exits so the VNC auto-login
# script has time to type credentials into the GUI. On Wine 10.0, MT5
# exits immediately if no server is configured; the auto-login process
# needs the terminal open to enter login details via VNC.
LOGIN_MARKER="/tmp/login_complete"

while true; do
    echo "Launching MetaTrader 5..."
    wine /opt/wineprefix/drive_c/Metatrader-5/terminal64.exe /portable
    EXIT_CODE=$?

    # If auto-login has completed and MT5 exits, it's a real crash — still restart
    if [ -f "$LOGIN_MARKER" ]; then
        echo "MT5 exited (code $EXIT_CODE) after login — restarting in 5s..."
        sleep 5
    else
        echo "MT5 exited (code $EXIT_CODE) before login — restarting in 2s..."
        sleep 2
    fi
done
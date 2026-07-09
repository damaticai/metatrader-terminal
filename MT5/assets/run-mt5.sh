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

    # Set environment to Windows 11
    winecfg -v=win11

    # Install WebView2
    wine MicrosoftEdgeWebview2Setup.exe /silent /install
    wineserver -w

    # Install MT5
    wine mt5setup.exe /auto /path:"C:\Metatrader-5"
    wineserver -w

    # Disable LiveUpdate immediately after install (before any launch).
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

export WINEPREFIX="${WINEPREFIX:-/opt/wineprefix}"
export DISPLAY="${DISPLAY:-:0}"

# Keep MT5 alive and shut Wine down cleanly when supervisor stops this script.
LOGIN_MARKER="/tmp/login_complete"
child_pid=""

cleanup() {
    echo "Stopping MetaTrader 5..."
    if [ -n "$child_pid" ]; then
        kill "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
    fi
    wineserver -k 2>/dev/null || true
    exit 0
}

trap cleanup TERM INT

while true; do
    echo "Launching MetaTrader 5..."
    wine /opt/wineprefix/drive_c/Metatrader-5/terminal64.exe /portable &
    child_pid=$!
    wait "$child_pid"
    EXIT_CODE=$?
    child_pid=""

    # If auto-login has completed and MT5 exits, it is a real crash; still restart.
    if [ -f "$LOGIN_MARKER" ]; then
        echo "MT5 exited (code $EXIT_CODE) after login; restarting in 5s..."
        sleep 5
    else
        echo "MT5 exited (code $EXIT_CODE) before login; restarting in 2s..."
        sleep 2
    fi
done

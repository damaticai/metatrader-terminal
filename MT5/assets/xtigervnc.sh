#!/bin/sh

/usr/bin/Xtigervnc -desktop "$VNC_DESKTOP_NAME" -geometry "$VNC_GEOMETRY" -listen tcp -ac -rfbport 5900 -rfbauth /root/.vnc/passwd -AlwaysShared -AcceptKeyEvents -AcceptPointerEvents -AcceptSetDesktopSize -SendCutText -AcceptCutText :0

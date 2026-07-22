# Build stage for easy-novnc
FROM golang:1.14-buster AS novnc-build
WORKDIR /src
RUN go mod init build && \
    go get github.com/geek1011/easy-novnc@v1.1.0 && \
    go build -o /bin/easy-novnc github.com/geek1011/easy-novnc

# Immutable, known-good MT5 build 5836.  Do not replace this with the moving
# download.mql5.com installer: that URL currently installs build 6034, whose
# terminal64.exe times out when the Linux Wine Python API opens MT5 IPC.
FROM ghcr.io/damaticai/metatrader-terminal@sha256:4a10bcc649bd448425ec31fd8c80baf5f4c02d7d7ff0e1267c78c79a2b261f9e AS mt5-build-5836

# Final stage
FROM docker.io/tobix/pywine:3.9

# ----------------------------------------------------------------------------------------------
LABEL org.opencontainers.image.source=https://github.com/damaticai/metatrader-terminal
LABEL org.opencontainers.image.description="MetaTrader 5 loopback Raw TCP Socket service"
LABEL org.opencontainers.image.mt5-build="5836"
LABEL org.opencontainers.image.mt5-terminal-sha256="e87e8b77fa415fc91e9acbe692826e76b7907fb53db4244aed36618f9af30b9e"
# ----------------------------------------------------------------------------------------------

# Environment Configurations
ENV HOME=/root \
    DISPLAY=:0 \
    MT5_SOCKET_HOST=127.0.0.1 \
    MT5_SOCKET_PORT=18812 \
    VNC_DESKTOP_NAME="MetaTrader 5" \
    VNC_GEOMETRY=1280x800 \
    DRIVE_C=${WINEPREFIX}/drive_c \
    STOPSIGNAL=SIGRTMIN+3

# MT5 Account Details (Provide at runtime)
ENV MT5_LOGIN=0 \
    MT5_SERVER='' \
    VNC_USER=mt5_user \
    VNC_PASSWORD=password

# Install system dependencies and clean up in a single layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    openbox \
    tigervnc-standalone-server \
    supervisor \
    gosu \
    lxterminal \
    nano \
    openssh-client \
    rsync \
    xdg-utils \
    htop \
    tar \
    xzip \
    gzip \
    bzip2 \
    zip \
    unzip \
    wget \
    xvfb \
    libnss3 \
    nginx-light \
    apache2-utils && \
    mkdir -p /usr/share/desktop-directories && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy easy-novnc binary from build stage
COPY --from=novnc-build /bin/easy-novnc /usr/local/bin/

# Copy configuration files
COPY assets/menu.xml /etc/xdg/openbox/

WORKDIR ${HOME}

# Layer 1: Restore the complete, known-good Wine prefix containing MT5 build
# 5836, then fail the image build if terminal64.exe ever differs.
COPY --from=mt5-build-5836 /opt/wineprefix /opt/wineprefix
ARG MT5_TERMINAL_SHA256=e87e8b77fa415fc91e9acbe692826e76b7907fb53db4244aed36618f9af30b9e
RUN actual_sha256="$(sha256sum /opt/wineprefix/drive_c/Metatrader-5/terminal64.exe | awk '{print $1}')" && \
    test "${actual_sha256}" = "${MT5_TERMINAL_SHA256}" && \
    echo "Pinned terminal64.exe SHA256=${actual_sha256} (MT5 build 5836)"

# Layer 2: Upgrade Wine 7.0 to 10.0 (MT5 build 5727+ needs Wine 10.0 for IPC)
# The base image has the WineHQ repo pre-configured.
RUN rm -f /etc/apt/sources.list.d/winehq.list && \
    apt-get update -qq && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --allow-downgrades winehq-stable && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    winecfg -v=win11 && \
    wineserver -k 2>/dev/null || true

# Layer 3: Install Python dependencies under Wine 10.0
COPY assets/requirements.txt /tmp/requirements.txt
COPY api/requirements.txt /tmp/api-requirements.txt
RUN wine pip install --no-cache-dir wheel && \
    wine pip install --no-cache-dir -r /tmp/requirements.txt && \
    wine pip install --no-cache-dir -r /tmp/api-requirements.txt && \
    wine pip install --no-cache-dir "cryptography<41"

# Layer 4: Copy everything else (changes frequently, but rebuild is instant)
COPY assets .
COPY api /root/api
COPY assets/supervisord.conf /etc/supervisord.conf
RUN mkdir -p ${HOME}/Desktop && \
    cp metatrader.desktop ${HOME}/Desktop/ && \
    cp metatrader.desktop /usr/share/applications/ && \
    chmod +x run-server.sh xtigervnc.sh easy-novnc.sh run-mt5.sh vnc-auth.sh entrypoint.sh auto_login_wrapper.sh

# EXPOSE 5900
EXPOSE 6901 18812

HEALTHCHECK --interval=10s --timeout=5s --start-period=90s --retries=12 \
    CMD wine python -c "import json,socket,struct; p=json.dumps({'id':'health','operation':'health','payload':{}}).encode(); s=socket.create_connection(('127.0.0.1',18812),3); s.sendall(struct.pack('>I',len(p))+p); f=s.makefile('rb'); n=struct.unpack('>I',f.read(4))[0]; r=json.loads(f.read(n)); s.close(); raise SystemExit(0 if r.get('ok') else 1)" || exit 1

CMD ["/root/entrypoint.sh"]

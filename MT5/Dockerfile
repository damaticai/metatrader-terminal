# Build stage for easy-novnc
FROM golang:1.14-buster AS novnc-build
WORKDIR /src
RUN go mod init build && \
    go get github.com/geek1011/easy-novnc@v1.1.0 && \
    go build -o /bin/easy-novnc github.com/geek1011/easy-novnc

# Final stage
FROM docker.io/tobix/pywine:3.9

# ----------------------------------------------------------------------------------------------
LABEL org.opencontainers.image.source=https://github.com/damaticai/metatrader-terminal
LABEL org.opencontainers.image.description="Custom MetaTrader 5 Terminal API"
# ----------------------------------------------------------------------------------------------

# Environment Configurations
ENV HOME=/root \
    DISPLAY=:0 \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=18812 \
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

# Layer 1: Install MT5 terminal under Wine 7.0
COPY assets/run-mt5.sh /tmp/run-mt5.sh
RUN chmod +x /tmp/run-mt5.sh && BUILD_MODE=1 xvfb-run /tmp/run-mt5.sh

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
EXPOSE 6901 8000

CMD ["/root/entrypoint.sh"]

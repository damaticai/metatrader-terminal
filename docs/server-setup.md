# Server Setup Guide: MT5 Terminal

This guide outlines the steps to set up the MetaTrader 5 terminal and its API on a Linux server using Docker and Nginx.

## Prerequisites

- A Linux server (Ubuntu 22.04+ recommended).
- Docker and Docker Compose installed.
- A domain name with A records pointing to your server's IP.

## 1. Clone the Repository

```bash
git clone https://github.com/nodalytics/metatrader-terminal.git
cd metatrader-terminal
```

## 2. Environment Configuration

Create a `.env` file from the example and fill in your MT5 credentials:

```bash
cp MT5/.env.example .env
```

At minimum, set the following for auto-login:

```env
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=YourBroker-Demo
```

When all three are set, the container will automatically log in to your MT5 account on startup via VNC automation and verify the connection before starting the API.

## 3. Deployment

### With Docker Compose

```bash
docker compose -f MT5/docker-compose.yml --env-file .env up -d
```

### With Docker (standalone)

```bash
docker run -d \
  --name mt5-terminal \
  -p 6901:6901 \
  -p 8000:8000 \
  -e MT5_LOGIN=12345678 \
  -e MT5_PASSWORD=your_password \
  -e MT5_SERVER=YourBroker-Demo \
  -e VNC_PASSWORD=password \
  ghcr.io/nodalytics/mt5-terminal:latest
```

This will start the MT5 terminal (VNC), auto-login to your account, and launch the FastAPI server.

> **Note**: The full startup takes approximately **2 minutes**. Most of this time is the MT5 terminal connecting to your broker's server. The API will not be available until login is verified. You can monitor progress via the VNC interface at `http://localhost:6901`.

## 4. Build Architecture

If building the image from source, the Dockerfile uses cached layers ordered by change frequency:

| Layer | What it does | Rebuilds when... |
| :--- | :--- | :--- |
| System deps | Installs VNC, nginx, supervisor | Base image or apt list changes |
| MT5 install | Downloads and installs MT5 under Wine 7.0 | `run-mt5.sh` changes |
| Wine upgrade | Upgrades Wine 7.0 → 10.0 for IPC compatibility | `wine_fix.sh` changes |
| Python deps | `pip install` under Wine 10.0 | `requirements.txt` changes |
| App code | Copies auto-login, API, configs | **Any code change (instant)** |

MT5 is installed under Wine 7.0 (fast), then Wine is upgraded to 10.0. Python packages are installed after the upgrade so they run under the correct Wine version. This keeps install times down while ensuring runtime IPC compatibility with MT5 build 5727+.

```bash
# Build from source
cd MT5
docker build -t mt5-terminal .
```

## 5. Nginx Configuration

1.  **Copy snippets**:
    ```bash
    sudo cp nginx/snippets/proxy_params.conf /etc/nginx/snippets/
    ```
2.  **Copy site config**:
    ```bash
    sudo cp nginx/sites-available/mt5 /etc/nginx/sites-available/
    ```
3.  **Edit site config**:
    Update the `server_name` in `/etc/nginx/sites-available/mt5` with your actual subdomains.
4.  **Enable the site**:
    ```bash
    sudo ln -s /etc/nginx/sites-available/mt5 /etc/nginx/sites-enabled/
    ```
5.  **Test and Reload**:
    ```bash
    sudo nginx -t
    sudo systemctl reload nginx
    ```

## 6. SSL with Certbot (Optional but Recommended)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d vnc.yourdomain.com -d api.yourdomain.com
```

## 7. Accessing the Services

- **MT5 VNC**: `https://vnc.yourdomain.com`
- **MT5 API**: `https://api.yourdomain.com`

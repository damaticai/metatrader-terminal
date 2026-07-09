# GitHub Actions Deployment Pipeline

This guide explains how to set up a GitHub Actions workflow to automatically deploy updates to your server.

## 1. Server Preparation

Ensure your server is accessible via SSH and that the deployment user has the necessary permissions to run Docker commands.

### SSH Key Setup
1.  Generate an SSH key pair on your local machine (if you don't have one).
2.  Add the public key to `~/.ssh/authorized_keys` on the server.
3.  Store the private key as a GitHub Secret.

## 2. GitHub Secrets

Go to your repository's **Settings > Secrets and variables > Actions** and add the following secrets:

- `SSH_HOST`: Your server's public IP address or hostname.
- `SSH_USER`: The username to SSH into (e.g., `ubuntu`).
- `SSH_KEY`: The content of your private SSH key.
- `DEPLOY_PATH`: The absolute path where the project should be deployed on the server.
- `GHCR_PAT`: A GitHub Personal Access Token with `read:packages` scope to pull images from GHCR.
- `SSL_ENABLED`: Set to `"true"` to enable automated SSL provisioning via Certbot.
- `SSL_DOMAIN`: Your base domain (e.g., `nodalytics.xyz`). The workflow will provision `mt5.${DOMAIN}` and `mt5-api.${DOMAIN}`.
- `SSL_EMAIL`: Email address for Certbot registration.

## 3. Workflow Configuration

The deployment workflow is defined in `.github/workflows/deploy.yml`. It is triggered automatically when the **"Docker Build & Test"** workflow completes successfully on the `main` branch.

### Deployment Process:
1.  **SCP File Transfer**: Copies `docker-compose.yml`, `.env.example`, and the `nginx/` directory to the server.
2.  **SSH Execution**:
    - **Refresh Env**: Refreshes `.env` from `.env.example` templates.
    - **Container Update**: Pulls latest images from `ghcr.io` and restarts services.
    - **Nginx Sync**: Compares local Nginx configurations with the server and reloads Nginx if changes are detected.
    - **SSL Provisioning**: Automatically provisions or renews SSL certificates using Certbot for the specified subdomains.
    - **System Maintenance**: Triggers a Docker system prune to reclaim disk space.

> [!NOTE]
> The workflow assumes that the Docker images are already built and pushed to GHCR by the prerequisite "Docker Build & Test" workflow.

> [!IMPORTANT]
> If this is a first-time setup, you may need to manually configure the `.env` file on the server after the first deployment to include sensitive production credentials.

#!/bin/bash

# Create .htpasswd for Nginx Basic Auth (DISABLED as per user request)
# if [ -n "$VNC_USER" ] && [ -n "$VNC_PASSWORD" ]; then
#     # Strip literal quotes that might be passed from environment files
#     VNC_USER=$(echo "$VNC_USER" | sed 's/^"//;s/"$//;s/'\''//g')
#     VNC_PASSWORD=$(echo "$VNC_PASSWORD" | sed 's/^"//;s/"$//;s/'\''//g')
#     
#     echo "==> Setting up Nginx Basic Auth for user: $VNC_USER"
#     # Create directory if it doesn't exist
#     mkdir -p /etc/nginx
#     # Use -B for bcrypt (recommended for modern nginx)
#     if htpasswd -bcB /etc/nginx/.htpasswd "$VNC_USER" "$VNC_PASSWORD"; then
#         echo "    ✅ .htpasswd created successfully at /etc/nginx/.htpasswd"
#         chmod 644 /etc/nginx/.htpasswd
#     else
#         echo "    ❌ ERROR: Failed to create .htpasswd"
#         exit 1
#     fi
# else
#     echo "==> WARNING: VNC_USER or VNC_PASSWORD not set. Authentication will likely fail."
# fi

# Create VNC password file for Xtigervnc
if [ -n "$VNC_PASSWORD" ]; then
    echo "==> Setting up VNC password..."
    mkdir -p /root/.vnc
    if echo "$VNC_PASSWORD" | vncpasswd -f > /root/.vnc/passwd; then
        echo "    ✅ VNC password file created at /root/.vnc/passwd"
        chmod 600 /root/.vnc/passwd
    else
        echo "    ❌ ERROR: Failed to set VNC password"
    fi
else
    echo "==> WARNING: VNC_PASSWORD not set. Direct VNC will not be secure."
fi

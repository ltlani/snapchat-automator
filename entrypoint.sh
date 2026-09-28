#!/bin/bash
set -euo pipefail

cd /home/container
mkdir -p scripts assets/fonts assets/outputs
cp /opt/snapchat-automator/{main.py,snapchat_web.py,image.py,requirements.txt,README.md} /home/container/
cp /opt/snapchat-automator/scripts/manual-send.py scripts/
cp /opt/snapchat-automator/assets/fonts/* assets/fonts/
if [ ! -f settings.py ]; then
    cp /opt/snapchat-automator/settings.example.py settings.py
    echo "Created settings.py. Add your friends in the file manager, then start the server again."
    exit 0
fi

if [ ! -f assets/outputs/streak.jpg ]; then
    if [ -f /opt/snapchat-automator/assets/outputs/streak.jpg ]; then
        cp /opt/snapchat-automator/assets/outputs/streak.jpg assets/outputs/streak.jpg
    else
        python image.py
    fi
fi

export DISPLAY=:99
Xvfb :99 -screen 0 1440x1000x24 -nolisten tcp >/dev/null 2>&1 &
xvfb_pid=$!
sleep 1
if ! kill -0 "$xvfb_pid" 2>/dev/null; then
    echo "Virtual display failed to start." >&2
    exit 1
fi
openbox >/dev/null 2>&1 &

if [ -n "${SERVER_PORT:-}" ]; then
    case "$SERVER_PORT" in
        *[!0-9]*|'') echo "SERVER_PORT must be a number." >&2; exit 1 ;;
    esac
    export BROWSER_VIEW_URL="$(python -c 'from snapchat_web import browser_view_url; print(browser_view_url())')"
    if [ -n "${BROWSER_PUBLIC_URL:-}" ] && [ -z "$BROWSER_VIEW_URL" ]; then
        echo "BROWSER_PUBLIC_URL must be an HTTPS origin, such as https://snapchat.example.com." >&2
        exit 1
    fi

    umask 077
    vnc_dir="$(mktemp -d)"
    vnc_password="$(python -c 'import secrets, string; print("".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8)))')"
    vnc_port="$(python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
    x11vnc -storepasswd "$vnc_password" "$vnc_dir/password" >/dev/null 2>&1
    tls_options=()
    if [ -z "${BROWSER_PUBLIC_URL:-}" ]; then
        openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
            -subj "/CN=Snapchat Browser" \
            -keyout "$vnc_dir/key.pem" -out "$vnc_dir/cert.pem" >/dev/null 2>&1
        tls_options=(--ssl-only --cert="$vnc_dir/cert.pem" --key="$vnc_dir/key.pem")
    fi

    x11vnc -display "$DISPLAY" -localhost -forever -shared -noxdamage \
        -rfbauth "$vnc_dir/password" -rfbport "$vnc_port" >/dev/null 2>&1 &
    vnc_pid=$!
    websockify "${tls_options[@]}" \
        --web=/usr/share/novnc "0.0.0.0:$SERVER_PORT" "127.0.0.1:$vnc_port" >/dev/null 2>&1 &
    web_pid=$!
    sleep 1
    if ! kill -0 "$vnc_pid" 2>/dev/null || ! kill -0 "$web_pid" 2>/dev/null; then
        echo "Browser viewer failed to start. Check that the server port is free." >&2
        exit 1
    fi

    export BROWSER_VIEW_PASSWORD="$vnc_password"
    if [ -n "$BROWSER_VIEW_URL" ]; then
        echo "Browser view: $BROWSER_VIEW_URL"
    else
        echo "Could not detect the public IP. Open https://YOUR_NODE_IP:$SERVER_PORT/vnc.html."
    fi
    echo "Browser password for this startup: $vnc_password"
    if [ -n "${BROWSER_PUBLIC_URL:-}" ]; then
        echo "HTTPS is handled by the reverse proxy. Keep the backend allocation private."
    else
        echo "The HTTPS certificate is self-signed. Keep this allocation private."
    fi
fi

read -r -a startup <<< "${STARTUP:-python -u main.py run}"
echo "Starting: ${startup[*]}"
exec "${startup[@]}"

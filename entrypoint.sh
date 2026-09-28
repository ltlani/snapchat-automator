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
    python image.py
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

    umask 077
    vnc_dir="$(mktemp -d)"
    vnc_password="$(python -c 'import secrets, string; print("".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8)))')"
    vnc_port="$(python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
    x11vnc -storepasswd "$vnc_password" "$vnc_dir/password" >/dev/null 2>&1
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -subj "/CN=Snapchat Browser" \
        -keyout "$vnc_dir/key.pem" -out "$vnc_dir/cert.pem" >/dev/null 2>&1

    x11vnc -display "$DISPLAY" -localhost -forever -shared -noxdamage \
        -disablefiletransfer -rfbauth "$vnc_dir/password" -rfbport "$vnc_port" >/dev/null 2>&1 &
    vnc_pid=$!
    websockify --ssl-only --cert="$vnc_dir/cert.pem" --key="$vnc_dir/key.pem" \
        --web=/usr/share/novnc "0.0.0.0:$SERVER_PORT" "127.0.0.1:$vnc_port" >/dev/null 2>&1 &
    web_pid=$!
    sleep 1
    if ! kill -0 "$vnc_pid" 2>/dev/null || ! kill -0 "$web_pid" 2>/dev/null; then
        echo "Browser viewer failed to start. Check that the server port is free." >&2
        exit 1
    fi

    echo "Browser view: https://<your-server-allocation>:$SERVER_PORT/vnc.html"
    echo "Browser password for this startup: $vnc_password"
    echo "The HTTPS certificate is self-signed. Keep this allocation private."
fi

read -r -a startup <<< "${STARTUP:-python -u main.py run}"
echo "Starting: ${startup[*]}"
exec "${startup[@]}"

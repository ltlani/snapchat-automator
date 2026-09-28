# Snapchat streak sender

Creates a simple camera Snap and sends it to your chosen Snapchat Web conversations. The long-running process checks every five minutes and sends each friend when their `HOURS` interval has elapsed. Your PC does not need to stay on.

## Pterodactyl setup

1. Build this `Dockerfile` with `docker build -t snapchat-automator:latest .` on the same Docker host as Pterodactyl Wings, or push the image to a registry the node can pull. Select that image for your server. A generic Python image does not include the required Chrome and browser-view tools.
2. Set the egg startup command to `python -u main.py run`, stop command to `^C`, and ready text to `Snapchat sender ready`. Assign one TCP allocation. The browser view uses its `SERVER_PORT`.
3. Start once. The container creates `settings.py` and exits. In the Pterodactyl file manager, add friends as `("Exact display name", "conversation ID")` entries in `FRIENDS`. Find each ID after `/web/` in that friend's Snapchat Web URL. Set `HOURS`, `HEADLESS`, and `IMAGE` if needed, then start again.

   For example: `FRIENDS = [("Alice", "conversation-id-from-url")]`. Replace both example values with the real ones.
4. The console prints a browser-view URL and a new password each startup. Open the HTTPS URL, accept its self-signed certificate, and type `login` in the Pterodactyl console. Sign in to Snapchat in that browser view. The Linux login is saved under `.runtime/chrome-profile`.
5. Type `preview "Exact display name"` to check the Snap without sending, then open `.runtime/last-preview.png` in the file manager. The next automatic check runs within five minutes; friends with no saved send time are immediately due. Leave the server running and restart it after changing `settings.py`.

Console commands: `status`, `preview "Friend Name"`, `manual-send`, `resolve "Friend Name" sent|not-sent`, `help`, and `stop`. `manual-send` ignores the timer and sends to everyone now, but it will not repeat a send whose outcome is uncertain. `python scripts/manual-send.py` does the same thing from a shell inside the container.

If your egg does not forward console input, temporarily use `python -u main.py login` or `python -u scripts/manual-send.py` as its startup command for that action, then switch back to `python -u main.py run`.

`HEADLESS = True` hides Chrome during previews and sends; `False` shows it in the browser view. Login is always visible. Keep the browser-view allocation restricted to your IP or Tailscale and keep `/home/container` private and persistent. `.runtime` contains the login and last-send times. `settings.py`, `.runtime`, and generated Snap images are excluded from Git and Docker builds; image updates refresh the code on restart but preserve those server-side files. The bundled Inter font carries its license in `assets/fonts/LICENSE.txt`.

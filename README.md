# Snapchat streak sender

Creates a simple camera Snap and sends it to your chosen Snapchat Web conversations. The long-running process checks every five minutes and sends each friend when their `HOURS` interval has elapsed. Your PC does not need to stay on.

## Pterodactyl setup

1. Build this `Dockerfile` with `docker build -t snapchat-automator:latest .` on the same Docker host as Pterodactyl Wings, or push the image to a registry the node can pull. Select that image for your server. A generic Python image does not include the required Chrome and browser-view tools.
2. Set the egg startup command to `python -u main.py run`, stop command to `^C`, and ready text to `Snapchat sender ready`. Assign one TCP allocation. The browser view uses its `SERVER_PORT`.
3. Start once. The container creates `settings.py` and exits. In the Pterodactyl file manager, add friends as `("Exact display name", "conversation ID")` entries in `FRIENDS`. Find each ID after `/web/` in that friend's Snapchat Web URL. Set `HOURS`, `HEADLESS`, and `IMAGE` if needed, then start again.

   For example: `FRIENDS = [("Alice", "conversation-id-from-url")]`. Replace both example values with the real ones.
4. Type `login` in the Pterodactyl console. It prints a direct login-view link and password. Open the link on your own device, verify it is your server, and sign in to Snapchat there. The console confirms when the login is saved under `.runtime/chrome-profile`; you can then close the tab. The link uses `SERVER_IP` automatically, or detects the node's public IP through `api.ipify.org` if the allocation is a wildcard/private address. If the viewer is private, set the egg's optional `BROWSER_VIEW_HOST` startup variable to the node's Tailscale IP (connect your device to Tailscale first). The HTTPS certificate is self-signed and the viewer password changes each startup. Snapchat Web still needs this browser sign-in; Snapchat's Login Kit does not grant access to chats or Snaps.
5. Type `preview "Exact display name"` to check the Snap without sending, then open `.runtime/last-preview.png` in the file manager. The next automatic check runs within five minutes; friends with no saved send time are immediately due. Leave the server running and restart it after changing `settings.py`.

Console commands: `status`, `preview "Friend Name"`, `manual-send`, `resolve "Friend Name" sent|not-sent`, `help`, and `stop`. `manual-send` ignores the timer and sends to everyone now, but it will not repeat a send whose outcome is uncertain. `python scripts/manual-send.py` does the same thing from a shell inside the container.

`preview "Friend Name"` captures a preview in `.runtime/last-preview.png` without sending anything. Use `resolve "Friend Name" sent` only after checking that an uncertain Snap was delivered; it records the send time. Use `not-sent` after confirming it was not delivered; it clears the pause so the next due check can try again. Neither `resolve` option sends a Snap itself.

If your egg does not forward console input, temporarily use `python -u main.py login` or `python -u scripts/manual-send.py` as its startup command for that action, then switch back to `python -u main.py run`.

`HEADLESS = True` hides Chrome during previews and sends; `False` shows it in the browser view. Login is always visible. Keep the browser-view allocation restricted to your IP or Tailscale and keep `/home/container` private and persistent. `.runtime` contains the login and last-send times. `settings.py` and `.runtime` are excluded from Git and Docker builds. The default image in `assets/outputs/streak.jpg` is included and copied into a fresh server; an image already on the server is preserved on restart. The bundled Inter font carries its license in `assets/fonts/LICENSE.txt`.

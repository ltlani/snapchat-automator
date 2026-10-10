# Snapchat streak sender

Sends a plain black Snap to your active 🔥 Streak chats every 22 hours. It checks the chat list every 10 minutes, so you don't have to add friends yourself.

Start the server and type `login` in the console to sign in to Snapchat. Your login is saved between restarts. If Snapchat signs you out later, type `login` again.

Useful console commands:

- `streaks` — see who it found.
- `status` — see when each Snap is due.
- `preview "Friend Name"` — check the Snap without sending.
- `manual-send` — send to all current Streak chats now.
- `manual-send "Friend Name"` — send to one chat, even without a Streak.
- `verify` — check sends that weren't confirmed.

You can change the 22-hour timing in `settings.py`. The `deploy/example.conf` file is a sample; keep your real server config private.

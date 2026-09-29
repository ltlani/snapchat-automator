# Snapchat streak sender

Sends a black Snap with your text to your chosen friends every 22 hours.

1. Add your friends in `settings.py`.
2. Start the server and type `login` in the console. Open the browser link it gives you and sign in to Snapchat.
3. Leave the server running and it'll handle the sends.

A few handy console commands:

- `status` — see when the next sends are due.
- `preview "Friend Name"` — check the Snap without sending it.
- `manual-send` — send to everyone now.
- `manual-send "Friend Name"` — send to just that friend.
- `verify` — check any sends that weren't confirmed.

You can change the timing in `settings.py`. Restart after changing it.

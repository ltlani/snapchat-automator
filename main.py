import sys
import shlex
import time
import logging
from datetime import datetime
from queue import Empty, Queue
from threading import Thread

from settings import FRIENDS, HEADLESS, HOURS, IMAGE
from snapchat_web import RUNTIME, SenderError, load_json, run_browser, run_lock, save_json, seconds_until_due


def note(message):
    print(message)
    with (RUNTIME / "sender.log").open("a", encoding="utf-8") as log:
        log.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")


def error_detail(error):
    lines = str(error).splitlines()
    return lines[0] if lines else "No further details."


def file_for(friend_id):
    return RUNTIME / f"state-{friend_id}.json"


def friend_config(name, friend_id):
    return {
        "recipient": name,
        "conversation_id": friend_id,
        "image": IMAGE,
        "headless": HEADLESS,
        "interval_hours": HOURS,
        "state_file": file_for(friend_id),
    }


def find_friend(text):
    for name, friend_id in FRIENDS:
        if text == name or text == friend_id:
            return name, friend_id
    raise SenderError(f"Friend not found: {text}")


def show_status():
    for name, friend_id in FRIENDS:
        state = load_json(file_for(friend_id))
        if state.get("pending_send"):
            message = "needs checking before another send"
        else:
            hours = seconds_until_due(state, HOURS) / 3600
            message = "due now" if hours == 0 else f"due in {hours:.1f} hours"
        print(f"{name}: {message}")


def verify_deliveries():
    name, friend_id = FRIENDS[0]
    config = friend_config(name, friend_id)
    config["friends"] = FRIENDS
    receipts = run_browser(config, "verify", {})
    failed = False
    for (name, friend_id), receipt in zip(FRIENDS, receipts):
        state = load_json(file_for(friend_id))
        pending = state.get("pending_send")
        if not pending:
            continue
        timestamp = receipt.get("timestamp")
        delivered = (receipt.get("id") == friend_id and receipt.get("name") == name
                     and any(status in (receipt.get("status") or "") for status in ("Delivered", "Opened")))
        if delivered and timestamp:
            sent = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            started = datetime.fromisoformat(pending["started_at"])
            delivered = sent.timestamp() >= started.timestamp() - 5
        else:
            delivered = False
        if delivered:
            state.pop("pending_send")
            state["last_sent_at"] = pending["started_at"]
            save_json(file_for(friend_id), state)
            note(f"Verified sent to {name}")
        else:
            note(f"{name}: delivery not confirmed; retries remain paused")
            failed = True
    return 1 if failed else 0


def send_all(manual=False):
    failed = False
    for name, friend_id in FRIENDS:
        state = load_json(file_for(friend_id))
        if state.get("pending_send"):
            note(f"{name}: previous result is uncertain; check Snapchat first")
            failed = True
            continue
        if not manual and seconds_until_due(state, HOURS) > 0:
            continue
        note(f"Sending to {name}...")
        try:
            run_browser(friend_config(name, friend_id), "send", state)
            note(f"Sent to {name}")
        except SenderError as error:
            note(f"{name}: {error}")
            failed = True
            if "session unavailable" in str(error).lower():
                break
        except Exception as error:
            note(f"{name}: browser error ({type(error).__name__}): {error_detail(error)}")
            failed = True
            break
    return 1 if failed else 0


def run_command(command, args):
    with run_lock():
        if command == "login":
            name, friend_id = FRIENDS[0]
            run_browser(friend_config(name, friend_id), "login", {})
        elif command == "preview":
            name, friend_id = find_friend(args[0] if args else FRIENDS[0][0])
            run_browser(friend_config(name, friend_id), "preview", {})
            print("Preview saved in .runtime/last-preview.png. Nothing was sent.")
        elif command == "send":
            return send_all()
        elif command == "manual-send":
            return send_all(manual=True)
        elif command == "status":
            show_status()
        elif command == "verify":
            return verify_deliveries()
        elif command == "resolve":
            if len(args) != 2:
                raise SenderError('Use: resolve "Friend Name" sent|not-sent')
            name, friend_id = find_friend(args[0])
            choice = args[1]
            state = load_json(file_for(friend_id))
            pending = state.pop("pending_send", None)
            if not pending or choice not in ("sent", "not-sent"):
                raise SenderError('Use: resolve "Friend Name" sent|not-sent')
            if choice == "sent":
                state["last_sent_at"] = pending["started_at"]
            save_json(file_for(friend_id), state)
            print(f"Updated {name}")
        else:
            raise SenderError("Use: login, preview, send, manual-send, status, verify, or resolve")
    return 0


def read_console(commands):
    for line in sys.stdin:
        commands.put(line.strip())


def run_forever():
    commands = Queue()
    Thread(target=read_console, args=(commands,), daemon=True).start()
    note(f"Snapchat sender ready. Checking every 5 minutes; each friend is due every {HOURS} hours.")
    print('Console commands: login, status, preview "Friend Name", manual-send, verify, resolve "Friend Name" sent|not-sent, stop', flush=True)
    next_check = time.monotonic() + 300

    while True:
        try:
            line = commands.get(timeout=max(0, next_check - time.monotonic()))
        except Empty:
            try:
                run_command("send", [])
            except SenderError as error:
                note(f"Check skipped: {error}")
            except Exception as error:
                note(f"Check failed ({type(error).__name__}): {error_detail(error)}")
            next_check = time.monotonic() + 300
            continue

        if not line:
            continue
        try:
            parts = shlex.split(line)
            if not parts:
                continue
            if parts[0] == "stop":
                note("Stopped from the console.")
                return
            if parts[0] == "help":
                print('Commands: login, status, preview "Friend Name", manual-send, verify, resolve "Friend Name" sent|not-sent, stop', flush=True)
                continue
            result = run_command(parts[0], parts[1:])
            if result:
                note("Command finished with errors. Check the messages above.")
        except ValueError as error:
            note(f"Invalid command: {error}")
        except SenderError as error:
            note(str(error))
        except Exception as error:
            note(f"Command failed ({type(error).__name__}): {error_detail(error)}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    RUNTIME.mkdir(exist_ok=True)
    if not isinstance(HOURS, (int, float)) or HOURS <= 0:
        raise SenderError("HOURS in settings.py must be greater than zero.")
    if not isinstance(HEADLESS, bool):
        raise SenderError("HEADLESS in settings.py must be True or False.")
    if not FRIENDS:
        raise SenderError("Add your friends to settings.py before starting the sender.")

    if command == "run":
        run_forever()
        return 0

    return run_command(command, sys.argv[2:])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit("Stopped.") from None
    except SenderError as error:
        raise SystemExit(str(error)) from None
    except Exception as error:
        raise SystemExit(f"Browser problem ({type(error).__name__}): {error_detail(error)}") from None

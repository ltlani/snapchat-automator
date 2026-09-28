from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
import json
import ipaddress
import logging
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import urlopen

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime"
LOG = logging.getLogger("snapchat")


class SenderError(RuntimeError):
    pass


def browser_view_url():
    port = os.environ.get("SERVER_PORT", "")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        return ""
    try:
        address = ipaddress.ip_address(os.environ.get("SERVER_IP") or "0.0.0.0")
        if not address.is_global:
            with urlopen("https://api.ipify.org", timeout=5) as response:
                address = ipaddress.ip_address(response.read(64).decode().strip())
            if not address.is_global:
                return ""
    except (OSError, ValueError):
        return ""
    host = f"[{address}]" if address.version == 6 else str(address)
    return f"https://{host}:{port}/vnc.html?autoconnect=1&resize=scale"


def show_login_instructions():
    url = os.environ.get("BROWSER_VIEW_URL")
    if url:
        print(f"Open this login link in your own browser: {url}", flush=True)
        print(f"Browser password: {os.environ['BROWSER_VIEW_PASSWORD']}", flush=True)
        print("Sign in to Snapchat there. This console will confirm when the login is saved.", flush=True)
    else:
        print("Sign in to Snapchat in the Chrome window. Waiting for login...", flush=True)


def load_json(path, default=None):
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise SenderError(f"Cannot read {path.name}.") from exc


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(path)


def seconds_until_due(state, hours, now=None):
    if not state.get("last_sent_at"):
        return 0
    sent = datetime.fromisoformat(state["last_sent_at"])
    if sent.tzinfo is None:
        raise SenderError("last_sent_at must include a timezone.")
    now = now or datetime.now(timezone.utc)
    return max(0, (sent.timestamp() + hours * 3600) - now.timestamp())


@contextmanager
def run_lock():
    RUNTIME.mkdir(exist_ok=True)
    with (RUNTIME / "run.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SenderError("Another sender is already running.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def image_data(config):
    image_path = ROOT / config.get("image", "assets/outputs/streak.jpg")
    if not image_path.is_file():
        raise SenderError(f"Image missing: {image_path}. Run image.py first.")
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        if config.get("mirror_camera_input", True):
            image = ImageOps.mirror(image)
        encoded = BytesIO()
        image.save(encoded, format="PNG")
    return "data:image/png;base64," + base64.b64encode(encoded.getvalue()).decode()


def camera_script(data_url):
    return """(() => {
      if (location.origin !== 'https://www.snapchat.com') return;
      const image = new Image();
      const ready = new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = () => reject(new Error('Streak image failed to load'));
      });
      image.src = DATA_URL;
      const streams = new Set();
      window.__streakCamera = { calls: 0, ready: false };
      ready.then(() => { window.__streakCamera.ready = true; });
      navigator.mediaDevices.getUserMedia = async constraints => {
        if (!constraints || !constraints.video)
          throw new DOMException('Only generated video is available', 'NotAllowedError');
        await ready;
        const canvas = document.createElement('canvas');
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        const ctx = canvas.getContext('2d');
        const draw = () => ctx.drawImage(image, 0, 0);
        draw();
        const stream = canvas.captureStream(10);
        const track = stream.getVideoTracks()[0];
        const timer = setInterval(draw, 100);
        const originalStop = track.stop.bind(track);
        track.stop = () => { clearInterval(timer); streams.delete(stream); originalStop(); };
        streams.add(stream);
        window.__streakCamera.calls += 1;
        return stream;
      };
      window.addEventListener('pagehide', () => {
        for (const stream of streams) stream.getTracks().forEach(t => t.stop());
      });
    })();""".replace("DATA_URL", json.dumps(data_url))


def network_summary(response):
    request = response.request
    url = urlsplit(response.url)
    if request.method not in ("POST", "PUT"):
        return None
    if url.hostname not in ("web.snapchat.com", "bolt-gcdn.sc-cdn.net"):
        return None
    if any(part in url.path for part in ("metrics", "graphene", "blizzard")):
        return None
    path = "/x/[media]" if url.hostname == "bolt-gcdn.sc-cdn.net" else url.path
    return {"host": url.hostname, "path": path, "method": request.method,
            "http_status": response.status,
            "grpc_status": response.headers.get("grpc-status")}


def grpc_web_status(body):
    offset = 0
    while offset + 5 <= len(body):
        flags = body[offset]
        size = int.from_bytes(body[offset + 1:offset + 5], "big")
        start = offset + 5
        end = start + size
        if end > len(body):
            raise SenderError("Incomplete gRPC-Web response.")
        if flags == 0x80:
            for line in body[start:end].decode("ascii", errors="replace").split("\r\n"):
                name, separator, value = line.partition(":")
                if separator and name.strip().lower() == "grpc-status":
                    return value.strip()
        offset = end
    return None


def prepare_snap(page, config):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    conversation_id = config["conversation_id"]
    LOG.info("Opening the configured Snapchat conversation.")
    page.goto(f"https://www.snapchat.com/web/{conversation_id}", wait_until="domcontentloaded")
    try:
        page.get_by_role("button", name="Close Chat", exact=True).wait_for(timeout=60000)
    except PlaywrightTimeout as exc:
        raise SenderError("Snapchat session unavailable. Run: python main.py login") from exc
    name = page.locator(f'[id="title-{conversation_id}"]')
    name.wait_for()
    if name.inner_text().strip() != config["recipient"]:
        raise SenderError("The conversation name does not match. No Snap was sent.")
    LOG.info("Capturing the generated image as a camera Snap.")
    page.locator("button.cDumY").click()
    page.wait_for_function("""() => {
      const video = document.querySelector('#local-video');
      return window.__streakCamera?.calls > 0 && video?.videoWidth > 0
             && video.readyState >= 2;
    }""")
    page.locator("button.fE2D5").click()
    page.get_by_role("button", name="Send", exact=True).wait_for()
    selected = page.locator(".Ecdhx li").all_text_contents()
    if selected != [config["recipient"]]:
        raise SenderError(f"Unexpected recipient selection: {selected!r}; no Snap sent.")
    preview = page.locator("img.VcjuA")
    preview.wait_for()
    preview.screenshot(path=str(RUNTIME / "last-preview.png"))


def chrome_user_agent(playwright):
    args = ["--disable-dev-shm-usage"] if sys.platform.startswith("linux") else []
    browser = playwright.chromium.launch(channel="chrome", headless=True, args=args)
    try:
        page = browser.new_page()
        return page.evaluate("navigator.userAgent").replace("HeadlessChrome/", "Chrome/")
    finally:
        browser.close()


def run_browser(config, command, state):
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    if command == "login":
        show_login_instructions()
    profile = RUNTIME / "chrome-profile"
    with sync_playwright() as playwright:
        headless = command != "login" and config.get("headless", True)
        user_agent = config.get("user_agent") or (chrome_user_agent(playwright) if headless else None)
        browser_args = ["--use-fake-device-for-media-stream"]
        if sys.platform.startswith("linux"):
            browser_args.append("--disable-dev-shm-usage")
        context = playwright.chromium.launch_persistent_context(
            str(profile), channel="chrome", headless=headless,
            viewport={"width": 1440, "height": 1000}, locale="en-US",
            user_agent=user_agent,
            args=browser_args,
        )
        try:
            context.grant_permissions(["camera"], origin="https://www.snapchat.com")
            if command != "login":
                context.add_init_script(camera_script(image_data(config)))
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30000)
            if command == "login":
                page.goto("https://www.snapchat.com/web", wait_until="domcontentloaded")
                page.get_by_role("button", name="New Chat", exact=True).wait_for(timeout=1200000)
                print("Snapchat login saved. You can close the browser tab; automatic checks will resume.", flush=True)
                LOG.info("Chrome session saved.")
                return
            events = []
            def record(response):
                summary = network_summary(response)
                if summary:
                    events.append(summary)
            page.on("response", record)
            prepare_snap(page, config)
            if command == "preview":
                LOG.info("Preview saved to .runtime/last-preview.png. Nothing sent.")
                return
            state["pending_send"] = {"started_at": datetime.now(timezone.utc).isoformat()}
            save_json(config["state_file"], state)
            events.clear()
            try:
                with page.expect_response(lambda r: urlsplit(r.url).path ==
                        "/messagingcoreservice.MessagingCoreService/CreateContentMessage"
                        and r.request.method == "POST", timeout=60000) as publish:
                    page.get_by_role("button", name="Send", exact=True).click()
                response = publish.value
                grpc_status = response.headers.get("grpc-status") or grpc_web_status(response.body())
                for event in events:
                    if event["path"].endswith("/CreateContentMessage"):
                        event["grpc_status"] = grpc_status
                if response.status != 200 or grpc_status != "0":
                    raise SenderError("Snapchat did not confirm the message RPC.")
                page.get_by_role("button", name="Close snap preview and return to camera.",
                                 exact=True).wait_for(state="hidden", timeout=60000)
                page.wait_for_function("""({id, started}) => {
                  const title = document.getElementById('title-' + id);
                  const row = title?.closest('[role="button"]');
                  const status = document.getElementById('status-' + id)?.textContent;
                  const timestamp = row?.querySelector('time')?.getAttribute('datetime');
                  return /Delivered|Opened/.test(status || '') && timestamp &&
                         Date.parse(timestamp) >= started - 5000;
                }""", arg={"id": config["conversation_id"], "started":
                           datetime.fromisoformat(state["pending_send"]["started_at"]).timestamp() * 1000}, timeout=90000)
                page.wait_for_timeout(500)
                if not any(x["method"] == "PUT" and 200 <= x["http_status"] < 300 for x in events):
                    raise SenderError("No successful media upload was observed.")
            except (PlaywrightTimeout, SenderError) as exc:
                save_json(RUNTIME / "last-network.json", events)
                raise SenderError("Send outcome uncertain. Check the chat and run resolve; automatic retries are paused.") from exc
            state.pop("pending_send", None)
            state["last_sent_at"] = datetime.now(timezone.utc).isoformat()
            save_json(config["state_file"], state)
            save_json(RUNTIME / "last-network.json", events)
            page.locator(f'[id="title-{config["conversation_id"]}"]').screenshot(
                path=str(RUNTIME / "last-delivery.png"))
            LOG.info("Snap sent to %s. Next send is due in %s hours.", config["recipient"], config["interval_hours"])
        except Exception:
            if context.pages:
                try:
                    page = context.pages[0]
                    (RUNTIME / "last-error.txt").write_text(page.title(), encoding="utf-8")
                except Exception:
                    pass
            raise
        finally:
            context.close()

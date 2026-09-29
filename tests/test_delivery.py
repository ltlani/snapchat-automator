import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright

import snapchat_web


class DeliveryTests(unittest.TestCase):
    def test_delayed_worker_upload_is_confirmed(self):
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as playwright:
            launch = playwright.chromium.launch_persistent_context

            def start_browser(*args, **kwargs):
                context = launch(*args, **kwargs)

                def serve(route):
                    url = route.request.url
                    headers = {"Access-Control-Allow-Origin": "*",
                               "Access-Control-Allow-Methods": "PUT, POST, OPTIONS"}
                    if url.endswith("/test-worker.js"):
                        route.fulfill(content_type="application/javascript", body="""
                          self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
                          self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
                          self.addEventListener('message', event => event.waitUntil(
                            new Promise(resolve => setTimeout(resolve, 1800)).then(() =>
                              fetch('https://storage.example.test/upload/private?token=example',
                                    {method: 'PUT', body: 'generated-media'}))));
                        """)
                    elif url.endswith("/CreateContentMessage"):
                        route.fulfill(headers=dict(headers, **{"grpc-status": "0"}), body="")
                    elif "storage.example.test" in url:
                        route.fulfill(headers=headers, body="")
                    else:
                        route.fulfill(content_type="text/html", body="""
                          <div role="button"><span id="title-test">Test Friend</span>
                            <span id="status-test">Received</span><time datetime="2020-01-01T00:00:00Z"></time>
                          </div>
                          <button id="close" title="Close snap preview and return to camera."></button>
                          <button onclick="sendSnap()">Send</button>
                          <script>
                            navigator.serviceWorker.register('/test-worker.js');
                            async function sendSnap() {
                              const worker = await navigator.serviceWorker.ready;
                              worker.active.postMessage('upload');
                              await fetch('https://web.snapchat.com/messagingcoreservice.MessagingCoreService/CreateContentMessage',
                                          {method: 'POST'});
                              document.getElementById('close').hidden = true;
                              document.getElementById('status-test').textContent = 'Delivered';
                              document.querySelector('time').dateTime = new Date().toISOString();
                            }
                          </script>
                        """)

                context.route("**/*", serve)
                return context

            state = {}
            config = {"recipient": "Test Friend", "conversation_id": "test", "headless": True,
                      "interval_hours": 22, "state_file": Path(temporary) / "state.json",
                      "user_agent": "Chrome camera regression test"}
            with patch.object(snapchat_web, "RUNTIME", Path(temporary)), patch(
                    "playwright.sync_api.sync_playwright", return_value=nullcontext(playwright)), patch.object(
                    playwright.chromium, "launch_persistent_context", side_effect=start_browser), patch.object(
                    snapchat_web, "prepare_snap", side_effect=lambda page, config:
                    page.goto("https://www.snapchat.com/web/test")):
                snapchat_web.run_browser(config, "send", state)
            self.assertIn("last_sent_at", state)
            self.assertNotIn("pending_send", state)
            events = json.loads((Path(temporary) / "last-network.json").read_text())
            upload = next(event for event in events if event.get("media_upload"))
            self.assertEqual(upload["http_status"], 200)
            self.assertEqual(upload["path"], "/x/[media]")
            self.assertNotIn("private", json.dumps(events))

    def check_verification(self, name="Test Friend", timestamp="2026-09-29T09:00:01Z", confirmed=True):
        settings = types.ModuleType("settings")
        settings.FRIENDS = [("Test Friend", "test")]
        settings.HEADLESS, settings.HOURS, settings.IMAGE = True, 22, "assets/outputs/streak.jpg"
        spec = importlib.util.spec_from_file_location("sender_verification_test", snapchat_web.ROOT / "main.py")
        main = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"settings": settings}):
            spec.loader.exec_module(main)
        with tempfile.TemporaryDirectory() as temporary, patch.object(main, "RUNTIME", Path(temporary)):
            started = "2026-09-29T09:00:00+00:00"
            snapchat_web.save_json(main.file_for("test"), {"pending_send": {"started_at": started}})
            receipt = {"id": "test", "name": name, "timestamp": timestamp, "status": "Delivered"}
            with patch.object(main, "run_browser", return_value=[receipt]), redirect_stdout(io.StringIO()):
                self.assertEqual(main.verify_deliveries(), 0 if confirmed else 1)
            state = snapchat_web.load_json(main.file_for("test"))
            if confirmed:
                self.assertEqual(state["last_sent_at"], started)
                self.assertNotIn("pending_send", state)
            else:
                self.assertIn("pending_send", state)
                self.assertNotIn("last_sent_at", state)

    def test_fresh_matching_delivery_clears_pending_without_resending(self):
        self.check_verification()

    def test_old_delivery_does_not_clear_pending(self):
        self.check_verification(timestamp="2026-09-28T09:00:00Z", confirmed=False)

    def test_other_recipient_does_not_clear_pending(self):
        self.check_verification(name="Other Friend", confirmed=False)


if __name__ == "__main__":
    unittest.main()

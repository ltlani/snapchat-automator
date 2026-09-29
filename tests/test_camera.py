import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import Error, sync_playwright

import snapchat_web


class CameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(channel="chrome", headless=True)
        except Error as error:
            cls.playwright.stop()
            raise unittest.SkipTest("Install Chrome to run the camera checks.") from error

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def check_camera(self, stop_track=False, capture_marker=True):
        config = {"recipient": "Test Friend", "conversation_id": "test-conversation"}
        with tempfile.TemporaryDirectory() as temporary:
            image_url = snapchat_web.image_data({})
            context = self.browser.new_context()
            self.addCleanup(context.close)
            context.add_init_script(snapchat_web.camera_script(image_url))
            context.route("https://www.snapchat.com/**", lambda route: route.fulfill(
                content_type="text/html", body="""
                <button title="Close Chat">Close Chat</button>
                <span id="title-test-conversation">Test Friend</span>
                <button class="changed-camera-class" onclick="openCamera()">
                  <svg viewBox="0 0 70 70"></svg>
                </button>
                <video autoplay muted playsinline></video>
                CAPTURE_BUTTON
                <div id="preview" hidden>
                  <ul class="Ecdhx"><li>Test Friend</li></ul>
                  <img class="VcjuA" width="100">
                  <button onclick="window.sent = true">Send</button>
                </div>
                <script>
                  window.sent = false;
                  window.captured = false;
                  async function openCamera() {
                    const generated = await navigator.mediaDevices.getUserMedia({video: true});
                    const cloned = generated.clone();
                    const video = document.querySelector('video');
                    video.srcObject = cloned;
                    await video.play();
                    if (STOP_TRACK) cloned.getTracks().forEach(track => track.stop());
                  }
                  function capture() {
                    window.captured = true;
                    const video = document.querySelector('video');
                    const canvas = document.createElement('canvas');
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    canvas.getContext('2d').drawImage(video, 0, 0);
                    document.querySelector('img').src = canvas.toDataURL();
                    document.getElementById('preview').hidden = false;
                  }
                </script>
                """.replace("STOP_TRACK", "true" if stop_track else "false").replace(
                    "CAPTURE_BUTTON", '<button onclick="capture()"><span id="CaptureButton_captureButton"></span></button>'
                    if capture_marker else '<button class="fE2D5" onclick="capture()"></button>')))
            page = context.new_page()
            wait_for_function = page.wait_for_function
            with patch.object(snapchat_web, "RUNTIME", Path(temporary)), patch.object(
                    page, "wait_for_function", side_effect=lambda script, **kwargs:
                    wait_for_function(script, **dict(kwargs, timeout=2000))):
                if stop_track:
                    with self.assertRaisesRegex(snapchat_web.SenderError, "generated camera stream"):
                        snapchat_web.prepare_snap(page, config)
                    self.assertFalse(page.evaluate("window.captured"))
                else:
                    snapchat_web.prepare_snap(page, config)
                    self.assertTrue(page.evaluate("window.captured"))
                    self.assertTrue((Path(temporary) / "last-preview.png").is_file())
                self.assertFalse(page.evaluate("window.sent"))
                self.assertFalse(page.evaluate("""window.__streakCamera.trackIds.includes(
                    document.querySelector('video').srcObject.getVideoTracks()[0].id)"""))

    def test_cloned_camera_stream_can_be_captured_without_sending(self):
        self.check_camera()

    def test_ended_camera_track_cannot_be_captured(self):
        self.check_camera(stop_track=True)

    def test_current_snapchat_capture_button_without_marker(self):
        self.check_camera(capture_marker=False)


if __name__ == "__main__":
    unittest.main()

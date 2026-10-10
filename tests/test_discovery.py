import base64
import unittest
from io import BytesIO

from PIL import Image
from playwright.sync_api import sync_playwright

import snapchat_web


class DiscoveryTests(unittest.TestCase):
    def test_black_snap_has_no_text_even_if_an_old_image_exists(self):
        data = snapchat_web.image_data({"image": "assets/outputs/streak.jpg"})
        with Image.open(BytesIO(base64.b64decode(data.split(",", 1)[1]))) as image:
            self.assertEqual(image.size, (1080, 1920))
            self.assertEqual(image.getextrema(), ((0, 0), (0, 0), (0, 0)))

    def test_finds_streaks_in_later_chat_rows_without_mistaking_a_name(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page()
                page.set_content("""
                  <div id="feed" style="height:100px;overflow-y:auto">
                    <div id="rows">
                      <div role="button"><span id="title-none">🔥 Fan</span><span>Received</span></div>
                      <div role="button"><span id="title-one">Streak Friend</span>
                        <span>🔥 3</span><span id="status-one">Delivered</span></div>
                    </div>
                    <div style="height:900px"></div>
                  </div>
                  <script>
                    const feed = document.getElementById('feed');
                    feed.addEventListener('scroll', () => {
                      if (feed.scrollTop > 20 && !document.getElementById('title-two')) {
                        document.getElementById('rows').insertAdjacentHTML('beforeend',
                          '<div role="button"><span id="title-two">Group Chat</span>' +
                          '<span aria-label="Snapstreak">6</span></div>');
                      }
                    });
                  </script>
                """)
                chats = snapchat_web.scan_chats(page)
                self.assertEqual({chat["id"] for chat in chats if chat["streak"]},
                                 {"one", "two"})
                self.assertEqual({chat["id"] for chat in chats}, {"none", "one", "two"})
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()

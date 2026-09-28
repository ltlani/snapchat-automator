import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from snapchat_web import browser_view_url, show_login_instructions


class LoginTests(unittest.TestCase):
    def test_reverse_proxy_url(self):
        for origin in ("https://snapchat.ouadielaachkar.com", "https://snapchat.ouadielaachkar.com/"):
            with patch.dict("os.environ", {"BROWSER_PUBLIC_URL": origin}, clear=True):
                with patch("snapchat_web.urlopen") as request:
                    self.assertEqual(browser_view_url(), "https://snapchat.ouadielaachkar.com/vnc.html?autoconnect=1&resize=scale")
                    request.assert_not_called()

    def test_invalid_reverse_proxy_urls(self):
        for origin in ("http://example.test", "https:///", "https://user:password@example.test",
                       "https://example.test/path", "https://example.test?query=1",
                       "https://example.test#fragment", "https://example.test:99999",
                       "https://example.test:0", "https://exam ple.test"):
            with patch.dict("os.environ", {"BROWSER_PUBLIC_URL": origin}, clear=True):
                self.assertEqual(browser_view_url(), "")

    def test_public_allocation(self):
        with patch.dict("os.environ", {"SERVER_IP": "89.28.205.45", "SERVER_PORT": "2011"}, clear=True):
            with patch("snapchat_web.urlopen") as request:
                self.assertEqual(browser_view_url(), "https://89.28.205.45:2011/vnc.html?autoconnect=1&resize=scale")
                request.assert_not_called()

    def test_wildcard_private_and_missing_allocation(self):
        for address in ("0.0.0.0", "::", "172.18.0.2", ""):
            with self.subTest(address=address):
                with patch.dict("os.environ", {"SERVER_IP": address, "SERVER_PORT": "2011"}, clear=True):
                    with patch("snapchat_web.urlopen") as request:
                        request.return_value.__enter__.return_value.read.return_value = b"89.28.205.45\n"
                        self.assertIn("https://89.28.205.45:2011/", browser_view_url())

    def test_ipv6_allocation(self):
        with patch.dict("os.environ", {"SERVER_IP": "2a06:9801:f73:14::10", "SERVER_PORT": "2011"}, clear=True):
            self.assertIn("https://[2a06:9801:f73:14::10]:2011/", browser_view_url())

    def test_private_viewer_host(self):
        with patch.dict("os.environ", {"BROWSER_VIEW_HOST": "100.105.121.93", "SERVER_PORT": "2011"}, clear=True):
            with patch("snapchat_web.urlopen") as request:
                self.assertIn("https://100.105.121.93:2011/", browser_view_url())
                request.assert_not_called()

    def test_invalid_viewer_hosts(self):
        for host in ("0.0.0.0", "127.0.0.1", "::", "224.0.0.1", "https://example.test"):
            with patch.dict("os.environ", {"BROWSER_VIEW_HOST": host, "SERVER_PORT": "2011"}, clear=True):
                self.assertEqual(browser_view_url(), "")

    def test_invalid_ports(self):
        for port in ("", "0", "65536", "2011/path"):
            with patch.dict("os.environ", {"SERVER_PORT": port}, clear=True):
                self.assertEqual(browser_view_url(), "")

    def test_ip_lookup_failure_does_not_crash_startup(self):
        with patch.dict("os.environ", {"SERVER_PORT": "2011"}, clear=True):
            with patch("snapchat_web.urlopen", side_effect=OSError("offline")):
                self.assertEqual(browser_view_url(), "")

    def test_cli_login_link(self):
        output = io.StringIO()
        with patch.dict("os.environ", {"BROWSER_VIEW_URL": "https://example.test/vnc.html", "BROWSER_VIEW_PASSWORD": "test-only"}, clear=True):
            with redirect_stdout(output):
                show_login_instructions()
        self.assertIn("Open this login link in your own browser: https://example.test/vnc.html", output.getvalue())
        self.assertIn("Browser password: test-only", output.getvalue())

    def test_local_login_window(self):
        output = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
            show_login_instructions()
        self.assertIn("Chrome window", output.getvalue())


if __name__ == "__main__":
    unittest.main()

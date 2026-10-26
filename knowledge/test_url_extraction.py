
from unittest.mock import Mock, patch

from django.test import SimpleTestCase


from knowledge.url_extraction import (
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    extract_text_from_url,
    validate_public_url,
)


class ValidatePublicURLTests(SimpleTestCase):
    def test_rejects_localhost(self):
        with self.assertRaises(ValueError):
            validate_public_url("http://localhost/")

    def test_rejects_localhost_subdomain(self):
        with self.assertRaises(ValueError):
            validate_public_url("http://service.localhost/")

    def test_rejects_private_ipv4_address(self):
        with self.assertRaises(ValueError):
            validate_public_url("http://127.0.0.1/")

    def test_rejects_private_ipv6_address(self):
        with self.assertRaises(ValueError):
            validate_public_url("http://[::1]/")

    def test_rejects_non_http_scheme(self):
        with self.assertRaises(ValueError):
            validate_public_url("file:///etc/passwd")

    def test_rejects_url_with_credentials(self):
        with self.assertRaises(ValueError):
            validate_public_url("https://user:password@example.com/")

    @patch("knowledge.url_extraction.socket.getaddrinfo")
    def test_rejects_hostname_resolving_to_private_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("192.168.1.10", 443))
        ]

        with self.assertRaises(ValueError):
            validate_public_url("https://example.test/")

    @patch("knowledge.url_extraction.socket.getaddrinfo")
    def test_rejects_hostname_with_mixed_public_and_private_ips(
        self, mock_getaddrinfo
    ):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443)),
            (2, 1, 6, "", ("10.0.0.5", 443)),
        ]

        with self.assertRaises(ValueError):
            validate_public_url("https://example.test/")

    @patch("knowledge.url_extraction.socket.getaddrinfo")
    def test_accepts_hostname_resolving_to_public_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443))
        ]

        self.assertEqual(
            validate_public_url("https://example.test/page"),
            "https://example.test/page",
        )


class FakeRedirectResponse:
    def __init__(self, location):
        self.status = 302
        self.headers = {"Location": location}

    def close(self):
        pass

    def release_conn(self):
        pass


class FakePool:
    def close(self):
        pass


class ExtractTextFromURLRedirectTests(SimpleTestCase):
    def make_redirect_response(self, location):
        return FakeRedirectResponse(location)

    @patch("knowledge.url_extraction._fetch_pinned_response")
    @patch("knowledge.url_extraction.socket.getaddrinfo")
    def test_validates_redirect_destination(
        self, mock_getaddrinfo, mock_fetch
    ):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443))
        ]
        mock_fetch.return_value = (
            FakePool(),
            self.make_redirect_response("http://127.0.0.1/private"),
        )

        with self.assertRaises(ValueError):
            extract_text_from_url("https://example.test/start")

        # The private redirect must be rejected before another request.
        self.assertEqual(mock_fetch.call_count, 1)

    @patch("knowledge.url_extraction._fetch_pinned_response")
    @patch("knowledge.url_extraction.socket.getaddrinfo")
    def test_stops_after_redirect_limit(
        self, mock_getaddrinfo, mock_fetch
    ):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443))
        ]
        mock_fetch.return_value = (
            FakePool(),
            self.make_redirect_response("/next"),
        )

        with self.assertRaisesRegex(ValueError, "redirect limit"):
            extract_text_from_url("https://example.test/start")

        self.assertEqual(
            mock_fetch.call_count,
            MAX_REDIRECTS + 1,
        )


class FakeHTMLResponse:
    def __init__(self, chunks, headers=None, status=200):
        self.status = status
        self.headers = headers or {
            "Content-Type": "text/html; charset=utf-8"
        }
        self.chunks = chunks
        self.closed = False
        self.released = False

    def stream(self, amt=8192, decode_content=False):
        yield from self.chunks

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


class ExtractTextFromURLSizeLimitTests(SimpleTestCase):
    @patch("knowledge.url_extraction._fetch_pinned_response")
    @patch("knowledge.url_extraction.socket.getaddrinfo")
    def test_rejects_response_over_2_mb(
        self, mock_getaddrinfo, mock_fetch
    ):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 80))
        ]

        response = FakeHTMLResponse(
            chunks=[
                b"a" * MAX_RESPONSE_BYTES,
                b"b",
            ]
        )
        pool = Mock()
        mock_fetch.return_value = (pool, response)

        with self.assertRaisesRegex(ValueError, "2 MB size limit"):
            extract_text_from_url("http://example.test/page")

        self.assertTrue(response.closed)
        self.assertTrue(response.released)
        pool.close.assert_called_once()

    @patch("knowledge.url_extraction._fetch_pinned_response")
    @patch("knowledge.url_extraction.socket.getaddrinfo")
    def test_accepts_response_within_2_mb(
        self, mock_getaddrinfo, mock_fetch
    ):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 80))
        ]

        response = FakeHTMLResponse(
            chunks=[b"<html><body>Website content</body></html>"]
        )
        pool = Mock()
        mock_fetch.return_value = (pool, response)

        result = extract_text_from_url("http://example.test/page")

        self.assertIn("Website content", result)
        self.assertTrue(response.closed)
        self.assertTrue(response.released)
        pool.close.assert_called_once()
class ReadableWebsiteContentTests(SimpleTestCase):
    def test_event_archive_keeps_titles_dates_and_links_without_site_navigation(self):
        from knowledge.url_extraction import extract_readable_html
        html = b'''<html><body><header>Site menu</header><div class="main-content">
        <article><a class="screen-reader-text">Duplicate title</a>
        <header><h3><a href="/event-one/">Youth Red Cross Day</a></h3></header>
        <p>Student celebration.</p><footer><time>March 4, 2026</time></footer></article>
        <article><h3><a href="/event-two/">Cancer awareness</a></h3><time>February 25, 2026</time></article>
        </div><div id="footer-outer">Admissions contacts</div><nav>Courses</nav></body></html>'''
        text = extract_readable_html(html, 'https://example.com/events/')
        self.assertIn('Youth Red Cross Day', text)
        self.assertIn('March 4, 2026', text)
        self.assertIn('https://example.com/event-one/', text)
        self.assertIn('Cancer awareness', text)
        self.assertNotIn('Duplicate title', text)
        self.assertNotIn('Admissions contacts', text)
        self.assertNotIn('Site menu', text)
        self.assertNotIn('Courses', text)

    def test_main_content_is_preferred_on_non_archive_page(self):
        from knowledge.url_extraction import extract_readable_html
        text = extract_readable_html(b'<body><div>Menu clutter</div><main><h1>Admissions</h1><p>Apply here.</p></main></body>', 'https://example.com/')
        self.assertEqual(text, 'Admissions Apply here.')

    def test_meta_charset_is_used_when_header_omits_it(self):
        from knowledge.url_extraction import extract_readable_html
        html = '<html><meta charset="utf-8"><body><main>Fresher\u2019s Day</main></body></html>'.encode('utf-8')
        self.assertIn('Fresher\u2019s Day', extract_readable_html(html, 'https://example.com/'))

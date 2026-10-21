
from unittest.mock import patch

from django.test import SimpleTestCase

from knowledge.pinned_transport import (
    PinnedHTTPConnection,
    PinnedHTTPSConnection,
)

from knowledge.pinned_transport import (
    PinnedHTTPConnectionPool,
    PinnedHTTPSConnectionPool,
)

from knowledge.url_extraction import _fetch_pinned_response

class PinnedConnectionTests(SimpleTestCase):
    def test_http_connection_rejects_invalid_ip(self):
        with self.assertRaises(ValueError):
            PinnedHTTPConnection(
                "example.test",
                pinned_ip="not-an-ip",
            )

    def test_https_connection_rejects_invalid_ip(self):
        with self.assertRaises(ValueError):
            PinnedHTTPSConnection(
                "example.test",
                pinned_ip="not-an-ip",
            )

    def test_http_connection_uses_pinned_ip(self):
        connection = PinnedHTTPConnection(
            "example.test",
            port=80,
            pinned_ip="93.184.216.34",
        )

        with patch(
            "knowledge.pinned_transport.socket.create_connection"
        ) as mock_create:
            mock_create.return_value = object()
            connection._new_conn()

        self.assertEqual(
            mock_create.call_args.args[0],
            ("93.184.216.34", 80),
        )

    def test_https_connection_uses_pinned_ip(self):
        connection = PinnedHTTPSConnection(
            "example.test",
            port=443,
            pinned_ip="93.184.216.34",
        )

        with patch(
            "knowledge.pinned_transport.socket.create_connection"
        ) as mock_create:
            mock_create.return_value = object()
            connection._new_conn()

        self.assertEqual(
            mock_create.call_args.args[0],
            ("93.184.216.34", 443),
        )


    def test_https_connection_preserves_tls_verification_defaults(self):
        import ssl

        connection = PinnedHTTPSConnection(
            "example.test",
            port=443,
            pinned_ip="93.184.216.34",
        )

        self.assertEqual(connection.host, "example.test")
        self.assertEqual(connection.pinned_ip, "93.184.216.34")
        self.assertEqual(connection.cert_reqs, ssl.CERT_REQUIRED)
        self.assertIsNone(connection.assert_hostname)
        self.assertIsNone(connection.server_hostname)

class PinnedConnectionPoolTests(SimpleTestCase):
    def test_http_pool_passes_pinned_ip_to_connection(self):
        pool = PinnedHTTPConnectionPool(
            "example.test",
            port=80,
            pinned_ip="93.184.216.34",
        )
        try:
            connection = pool._new_conn()
            self.assertIsInstance(connection, PinnedHTTPConnection)
            self.assertEqual(connection.host, "example.test")
            self.assertEqual(connection.pinned_ip, "93.184.216.34")
        finally:
            pool.close()

    def test_https_pool_passes_pinned_ip_to_connection(self):
        pool = PinnedHTTPSConnectionPool(
            "example.test",
            port=443,
            pinned_ip="93.184.216.34",
        )
        try:
            connection = pool._new_conn()
            self.assertIsInstance(connection, PinnedHTTPSConnection)
            self.assertEqual(connection.host, "example.test")
            self.assertEqual(connection.pinned_ip, "93.184.216.34")
        finally:
            pool.close()


class PinnedRequestTransportTests(SimpleTestCase):
    @patch("knowledge.url_extraction.PinnedHTTPSConnectionPool")
    def test_https_request_keeps_hostname_and_uses_pinned_ip(
        self, mock_pool_class
    ):
        fake_response = object()
        mock_pool = mock_pool_class.return_value
        mock_pool.urlopen.return_value = fake_response

        pool, response = _fetch_pinned_response(
            "https://example.test/docs/page?q=1",
            "93.184.216.34",
        )

        self.assertIs(pool, mock_pool)
        self.assertIs(response, fake_response)

        # Keep the hostname for HTTPS/TLS verification.
        self.assertEqual(
            mock_pool_class.call_args.kwargs["host"],
            "example.test",
        )

        # Pin the network destination to the validated IP.
        self.assertEqual(
            mock_pool_class.call_args.kwargs["pinned_ip"],
            "93.184.216.34",
        )

        # Ensure the request target doesn't contain the hostname.
        request_args = mock_pool.urlopen.call_args
        self.assertEqual(request_args.args[0], "GET")
        self.assertEqual(request_args.args[1], "/docs/page?q=1")
        self.assertFalse(request_args.kwargs["redirect"])

    @patch("knowledge.url_extraction.PinnedHTTPConnectionPool")
    def test_http_request_uses_pinned_transport(
        self, mock_pool_class
    ):
        fake_response = object()
        mock_pool = mock_pool_class.return_value
        mock_pool.urlopen.return_value = fake_response

        pool, response = _fetch_pinned_response(
            "http://example.test/articles",
            "93.184.216.34",
        )

        self.assertIs(pool, mock_pool)
        self.assertIs(response, fake_response)
        self.assertEqual(
            mock_pool_class.call_args.kwargs["host"],
            "example.test",
        )
        self.assertEqual(
            mock_pool_class.call_args.kwargs["pinned_ip"],
            "93.184.216.34",
        )

        request_args = mock_pool.urlopen.call_args
        self.assertEqual(request_args.args[1], "/articles")
        self.assertFalse(request_args.kwargs["redirect"])
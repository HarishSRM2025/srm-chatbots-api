
import unittest
from unittest.mock import Mock, patch

from knowledge.url_extraction import validate_public_url


class PinnedConnectionTests(unittest.TestCase):
    @patch("knowledge.url_extraction.socket.getaddrinfo")
    def test_dns_resolution_returns_only_public_addresses(self, mock_dns):
        mock_dns.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 80)),
        ]

        result = validate_public_url("http://example.com/")

        self.assertEqual(result, "http://example.com/")
        mock_dns.assert_called_once()

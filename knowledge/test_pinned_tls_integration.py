
from multiprocessing.dummy import connection
import socket
import ssl
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from knowledge.pinned_transport import PinnedHTTPSConnection
from knowledge.pinned_transport import PinnedHTTPSConnectionPool
from urllib3.exceptions import SSLError


TLS_DIR = Path(__file__).resolve().parent.parent / "tests" / "tls"


class TestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"TLS integration test passed"

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        pass


class PinnedTLSIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), TestHandler)

        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(
            certfile=str(TLS_DIR / "server.crt"),
            keyfile=str(TLS_DIR / "server.key"),
        )

        cls.server.socket = server_context.wrap_socket(
            cls.server.socket,
            server_side=True,
        )

        cls.server_thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.server_thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)


    def test_trusted_certificate_matches_original_hostname(self):
        pool = PinnedHTTPSConnectionPool(
            host="example.test",
            port=self.port,
            pinned_ip="127.0.0.1",
            timeout=3,
            retries=False,
            cert_reqs=ssl.CERT_REQUIRED,
            ca_certs=str(TLS_DIR / "test-ca.crt"),
        )

        try:
            response = pool.urlopen(
                "GET",
                "/",
                redirect=False,
                retries=False,
            )

            self.assertEqual(response.status, 200)
            self.assertEqual(
                response.data,
                b"TLS integration test passed",
            )
        finally:
            pool.close()


    def test_untrusted_certificate_is_rejected(self):
        connection = PinnedHTTPSConnection(
            host="example.test",
            port=self.port,
            pinned_ip="127.0.0.1",
            timeout=3,
            cert_reqs=ssl.CERT_REQUIRED,
        )

        try:
            with self.assertRaises(ssl.SSLCertVerificationError):
                connection.connect()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()

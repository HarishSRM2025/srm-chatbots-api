
import ipaddress
import socket

from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool


def _open_pinned_socket(connection):
    """Connect to the validated IP without resolving the hostname again."""
    pinned_ip = connection.pinned_ip
    port = connection.port

    try:
        sock = socket.create_connection(
            (pinned_ip, port),
            connection.timeout,
            source_address=connection.source_address,
        )
    except OSError as exc:
        raise OSError(
            f"Could not connect to validated IP {pinned_ip}:{port}"
        ) from exc

    try:
        # Python's socket.create_connection() does not accept socket_options.
        # Apply urllib3's configured options to the connected socket instead.
        if hasattr(sock, "setsockopt"):
            for option in connection.socket_options or ():
                sock.setsockopt(*option)

        return sock
    except OSError:
        sock.close()
        raise


class PinnedHTTPConnection(HTTPConnection):
    """HTTP connection routed to a previously validated IP."""

    def __init__(self, *args, pinned_ip: str, **kwargs):
        self.pinned_ip = str(ipaddress.ip_address(pinned_ip))
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        return _open_pinned_socket(self)


class PinnedHTTPSConnection(HTTPSConnection):
    """HTTPS connection pinned to an IP, retaining hostname verification."""

    def __init__(self, *args, pinned_ip: str, **kwargs):
        self.pinned_ip = str(ipaddress.ip_address(pinned_ip))
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        # HTTPSConnection.connect() retains the original hostname for TLS.
        return _open_pinned_socket(self)


class PinnedHTTPConnectionPool(HTTPConnectionPool):
    """HTTP pool that passes a pinned IP to each new connection."""

    ConnectionCls = PinnedHTTPConnection


class PinnedHTTPSConnectionPool(HTTPSConnectionPool):
    """HTTPS pool that passes a pinned IP to each new connection."""

    ConnectionCls = PinnedHTTPSConnection

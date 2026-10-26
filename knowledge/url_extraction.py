
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import urllib3
from bs4 import BeautifulSoup
from urllib3.util import Timeout

from knowledge.pinned_transport import (
    PinnedHTTPConnectionPool,
    PinnedHTTPSConnectionPool,
)


MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB
REQUEST_TIMEOUT = (5, 15)
MAX_REDIRECTS = 5

HEADERS = {
    "User-Agent": "SRM-Chatbots-KnowledgeBot/1.0",
}

REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def _resolve_public_ips(url: str) -> list[str]:
    """Validate a URL and return only its validated public destination IPs."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("A website URL is required.")

    parsed = urlparse(url)

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS URLs are supported.")

    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("The URL is invalid or contains credentials.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("The URL contains an invalid port.") from exc

    if port is not None and not 1 <= port <= 65535:
        raise ValueError("The URL contains an invalid port.")

    hostname = parsed.hostname.rstrip(".").lower()

    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
    ):
        raise ValueError("Local or private hostnames are not allowed.")

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if not literal_ip.is_global:
            raise ValueError(
                "Private or non-public network addresses are not allowed."
            )
        return [str(literal_ip)]

    destination_port = port or (443 if parsed.scheme.lower() == "https" else 80)

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                hostname,
                destination_port,
                type=socket.SOCK_STREAM,
            )
        }
    except (socket.gaierror, OSError) as exc:
        raise ValueError("The website hostname could not be resolved.") from exc

    if not addresses:
        raise ValueError("The website hostname could not be resolved.")

    public_ips = []

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError("The website returned an invalid IP address.") from exc

        if not ip.is_global:
            raise ValueError(
                "Private or non-public network addresses are not allowed."
            )

        public_ips.append(str(ip))

    return sorted(set(public_ips))


def validate_public_url(url: str) -> str:
    """Validate an HTTP(S) URL and reject non-public destinations."""
    _resolve_public_ips(url)
    return url


def _request_target(parsed) -> str:
    """Build the HTTP request target without the hostname or fragment."""
    target = parsed.path or "/"

    if parsed.query:
        target += "?" + parsed.query

    return target


def _fetch_pinned_response(url: str, pinned_ip: str):
    """Open one request through a pool pinned to the validated IP."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    port = parsed.port or (443 if scheme == "https" else 80)

    pool_class = (
        PinnedHTTPSConnectionPool
        if scheme == "https"
        else PinnedHTTPConnectionPool
    )

    # The pool host remains the original hostname. For HTTPS, urllib3 uses
    # that hostname for TLS SNI and certificate verification.
    pool = pool_class(
        host=parsed.hostname,
        port=port,
        pinned_ip=pinned_ip,
        timeout=Timeout(
            connect=REQUEST_TIMEOUT[0],
            read=REQUEST_TIMEOUT[1],
        ),
        maxsize=1,
        retries=False,
    )

    try:
        response = pool.urlopen(
            "GET",
            _request_target(parsed),
            headers=HEADERS,
            redirect=False,
            retries=False,
            preload_content=False,
            decode_content=True,
            timeout=Timeout(
                connect=REQUEST_TIMEOUT[0],
                read=REQUEST_TIMEOUT[1],
            ),
        )
        return pool, response
    except Exception:
        pool.close()
        raise


def extract_text_from_url(url: str) -> str:
    """Fetch a public HTML page using a validated, pinned destination IP."""
    current_url = url

    for redirect_count in range(MAX_REDIRECTS + 1):
        # Resolve once for this hop and connect only to one of these IPs.
        public_ips = _resolve_public_ips(current_url)
        pool = None
        response = None

        try:
            pool, response = _fetch_pinned_response(
                current_url,
                public_ips[0],
            )

            if response.status in REDIRECT_STATUSES:
                if redirect_count >= MAX_REDIRECTS:
                    raise ValueError("The website exceeded the redirect limit.")

                location = response.headers.get("Location")
                if not location:
                    raise ValueError("The website returned an invalid redirect.")

                next_url = urljoin(current_url, location)

                # Validate the next hop before attempting its connection.
                _resolve_public_ips(next_url)
                current_url = next_url
                continue

            if response.status >= 400:
                raise ValueError("The webpage could not be fetched.")

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type:
                raise ValueError("The URL must point to an HTML webpage.")

            chunks = []
            total_bytes = 0

            for chunk in response.stream(amt=8192, decode_content=True):
                if not chunk:
                    continue

                total_bytes += len(chunk)

                if total_bytes > MAX_RESPONSE_BYTES:
                    raise ValueError("The webpage exceeds the 2 MB size limit.")

                chunks.append(chunk)

            html = b"".join(chunks)
            encoding = response.headers.get("Content-Type", "")
            charset = None

            if "charset=" in encoding.lower():
                charset = encoding.lower().split("charset=", 1)[1]
                charset = charset.split(";", 1)[0].strip(" '\"")

            text = extract_readable_html(html, current_url, charset)

            if not text:
                raise ValueError("No readable text was found on the webpage.")

            return text

        except urllib3.exceptions.HTTPError as exc:
            raise ValueError("The webpage could not be fetched.") from exc
        except OSError as exc:
            raise ValueError("The webpage could not be fetched.") from exc
        finally:
            if response is not None:
                response.close()
                response.release_conn()

            if pool is not None:
                pool.close()

    raise ValueError("The webpage could not be fetched.")


def extract_readable_html(html: bytes, page_url: str, charset: str | None = None) -> str:
    """Prefer the page's main content and preserve article titles and dates.

    Archive pages supply summaries, not the complete linked articles. Include
    the article URL as a reference without silently crawling unrelated pages.
    """
    soup = BeautifulSoup(html, 'html.parser', from_encoding=charset)
    for element in soup(['script', 'style', 'noscript', 'svg', 'nav', 'aside']):
        element.decompose()
    for element in soup.select('.screen-reader-text, #footer-outer, #slide-out-widget-area, [role="navigation"]'):
        element.decompose()
    for element in soup(['header', 'footer']):
        if not element.find_parent('article'):
            element.decompose()
    root = soup.select_one('main, [role="main"], .main-content, #main-content') or soup.body or soup
    articles = root.find_all('article')
    if articles:
        blocks = []
        for article in articles:
            # Nested article elements must not duplicate their parent's text.
            if article.find_parent('article'):
                continue
            block = article.get_text(separator=' ', strip=True)
            link = article.select_one('h1 a[href], h2 a[href], h3 a[href], .entry-title a[href]')
            if link:
                target = urljoin(page_url, link['href'])
                if urlparse(target).scheme in {'http', 'https'}:
                    block += '\nArticle URL: ' + target
            if block:
                blocks.append(block)
        return '\n\n'.join(blocks)
    return root.get_text(separator=' ', strip=True)

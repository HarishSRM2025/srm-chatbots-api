
from urllib.parse import urlsplit

from rest_framework.exceptions import PermissionDenied

def normalize_origin(origin):
    if not isinstance(origin, str) or not origin:
        return None

    if origin == "null" or origin != origin.strip():
        return None

    try:
        parsed = urlsplit(origin)

        if parsed.scheme not in ("http", "https"):
            return None

        if not parsed.hostname:
            return None

        if parsed.username or parsed.password:
            return None

        if parsed.path or parsed.query or parsed.fragment:
            return None

        port = parsed.port

        scheme = parsed.scheme.lower()
        hostname = parsed.hostname.lower()

        if ":" in hostname:
            hostname = f"[{hostname}]"

        if port is not None:
            default_port = (
                (scheme == "http" and port == 80)
                or (scheme == "https" and port == 443)
            )
            if not default_port:
                hostname = f"{hostname}:{port}"

        return f"{scheme}://{hostname}"

    except (ValueError, UnicodeError):
        return None


def is_origin_allowed(origin, allowed_origins):
    # Requests without Origin are handled separately.
    if origin is None:
        return True

    normalized_origin = normalize_origin(origin)

    if normalized_origin is None:
        return False

    if not isinstance(allowed_origins, list):
        return False

    normalized_allowed = {
        normalized
        for item in allowed_origins
        if (normalized := normalize_origin(item)) is not None
    }

    return normalized_origin in normalized_allowed



def validate_widget_origin(request, agent):
    origin = request.headers.get("Origin")

    # Non-browser clients may omit Origin.
    # They must still pass widget session-token validation.
    if origin is None:
        return

    if not is_origin_allowed(origin, agent.allowed_origins):
        raise PermissionDenied(
            "This website origin is not allowed to use this widget."
        )

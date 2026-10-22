
import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from .models import WidgetSession


WIDGET_SESSION_TTL = timedelta(hours=2)


def create_widget_session(agent):
    """Create a temporary session and return its raw token once."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    session = WidgetSession.objects.create(
        agent=agent,
        token_hash=token_hash,
        expires_at=timezone.now() + WIDGET_SESSION_TTL,
    )

    return session, token


def get_widget_session(token, agent_id):
    """Return a valid session for this agent, or None."""
    if not isinstance(token, str) or not token or len(token) > 256:
        return None

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    session = (
        WidgetSession.objects
        .select_related("agent")
        .filter(
            token_hash=token_hash,
            agent_id=agent_id,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
            agent__status="active",
            agent__is_public=True,
        )
        .first()
    )

    return session

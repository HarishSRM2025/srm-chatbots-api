
from rest_framework.throttling import AnonRateThrottle


class WidgetSessionRateThrottle(AnonRateThrottle):
    scope = "widget_session"


class WidgetMessageRateThrottle(AnonRateThrottle):
    scope = "widget_message"

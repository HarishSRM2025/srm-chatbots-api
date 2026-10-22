
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ConversationViewSet,
    WidgetConversationCreateView,
    WidgetMessageCreateView,
    WidgetSessionCreateView,
)

router = DefaultRouter()
router.register(
    "conversations",
    ConversationViewSet,
    basename="conversation",
)

urlpatterns = [
    path(
        "widget/sessions/",
        WidgetSessionCreateView.as_view({"post": "create"}),
        name="widget-session-create",
    ),
    path(
        "widget/conversations/",
        WidgetConversationCreateView.as_view(),
        name="widget-conversation-create",
    ),
    path(
        "widget/conversations/<int:conversation_id>/messages/",
        WidgetMessageCreateView.as_view(),
        name="widget-message-create",
    ),
] + router.urls

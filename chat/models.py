
from django.conf import settings
from django.db import models
from django.utils import timezone


class Conversation(models.Model):
    agent = models.ForeignKey(
        "agents.Agent",
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_conversations",
    )
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversation {self.pk} - {self.agent.name}"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.role} message - Conversation {self.conversation_id}"

class WidgetSession(models.Model):
    agent = models.ForeignKey(
        "agents.Agent",
        on_delete=models.CASCADE,
        related_name="widget_sessions",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agent", "expires_at"]),
        ]

    @property
    def is_valid(self):
        now = timezone.now()
        return (
            self.revoked_at is None
            and self.expires_at > now
            and self.agent.status == "active"
            and self.agent.is_public
        )

    def __str__(self):
        return f"Widget session {self.pk} - Agent {self.agent_id}"



class WidgetConversation(models.Model):
    session = models.ForeignKey(
        WidgetSession,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Widget conversation {self.pk} - Session {self.session_id}"


class WidgetMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        WidgetConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.role} message - Widget conversation {self.conversation_id}"



class WidgetMessageRequest(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    conversation = models.ForeignKey(
        WidgetConversation,
        on_delete=models.CASCADE,
        related_name="message_requests",
    )
    idempotency_key = models.CharField(max_length=128)
    content_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PROCESSING,
    )
    user_message = models.ForeignKey(
        WidgetMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="widget_user_requests",
    )
    assistant_message = models.ForeignKey(
        WidgetMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="widget_assistant_requests",
    )
    sources = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "idempotency_key"],
                name="unique_widget_request_key_per_conversation",
            ),
        ]
        indexes = [
            models.Index(fields=["conversation", "status"]),
        ]

    def __str__(self):
        return (
            f"Widget request {self.pk} - "
            f"Conversation {self.conversation_id} - {self.status}"
        )

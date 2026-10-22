
# Create your models here.
from django.conf import settings
from django.db import models


class Agent(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agents",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    system_prompt = models.TextField()
    model_name = models.CharField(max_length=100, default="qwen3:4b")
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    is_public = models.BooleanField(default=False)
    allowed_origins = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="unique_agent_name_per_owner",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.owner.username})"
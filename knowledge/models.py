
from django.db import models


class KnowledgeSource(models.Model):
    class SourceType(models.TextChoices):
        FILE = "file", "File"
        URL = "url", "Website URL"
        TEXT = "text", "Plain Text"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    agent = models.ForeignKey(
        "agents.Agent",
        on_delete=models.CASCADE,
        related_name="knowledge_sources",
    )

    title = models.CharField(max_length=200)
    source_type = models.CharField(
        max_length=10,
        choices=SourceType.choices,
    )

    file = models.FileField(
        upload_to="knowledge_sources/%Y/%m/",
        blank=True,
    )
    source_url = models.URLField(blank=True)
    text_content = models.TextField(blank=True)

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.agent.name}"


class KnowledgeChunk(models.Model):
    source = models.ForeignKey(
        KnowledgeSource,
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    content = models.TextField()
    chunk_index = models.PositiveIntegerField()
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["source", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "chunk_index"],
                name="unique_chunk_index_per_source",
            ),
        ]

    def __str__(self):
        return f"{self.source.title} - Chunk {self.chunk_index}"

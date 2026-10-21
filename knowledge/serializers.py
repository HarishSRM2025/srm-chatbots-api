
from pathlib import Path
from urllib.parse import urlparse

from rest_framework import serializers

from agents.models import Agent
from .models import KnowledgeSource


class KnowledgeSourceSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(
        source="agent.name",
        read_only=True,
    )

    class Meta:
        model = KnowledgeSource
        fields = [
            "id",
            "agent",
            "agent_name",
            "title",
            "source_type",
            "file",
            "source_url",
            "text_content",
            "status",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "agent_name",
            "status",
            "error_message",
            "created_at",
            "updated_at",
        ]

    def validate_agent(self, agent):
        request = self.context.get("request")

        if request and agent.owner_id != request.user.id:
            raise serializers.ValidationError(
                "You can only add knowledge to your own agents."
            )

        return agent

    def validate(self, attrs):
        source_type = attrs.get(
            "source_type",
            getattr(self.instance, "source_type", None),
        )

        if source_type == KnowledgeSource.SourceType.TEXT:
            text_content = attrs.get(
                "text_content",
                getattr(self.instance, "text_content", ""),
            )

            if not text_content or not text_content.strip():
                raise serializers.ValidationError({
                    "text_content": "Text content cannot be empty."
                })

        elif source_type == KnowledgeSource.SourceType.URL:
            source_url = attrs.get(
                "source_url",
                getattr(self.instance, "source_url", ""),
            )

            if not source_url or not source_url.strip():
                raise serializers.ValidationError({
                    "source_url": "A website URL is required."
                })

            parsed = urlparse(source_url)

            if (
                parsed.scheme.lower() not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise serializers.ValidationError({
                    "source_url": (
                        "Enter a valid public HTTP or HTTPS website URL."
                    )
                })

        elif source_type == KnowledgeSource.SourceType.FILE:
            uploaded_file = attrs.get(
                "file",
                getattr(self.instance, "file", None),
            )

            if not uploaded_file:
                raise serializers.ValidationError({
                    "file": "A file is required."
                })

            if uploaded_file.size == 0:
                raise serializers.ValidationError({
                    "file": "Empty files are not allowed."
                })

            max_size = 10 * 1024 * 1024

            if uploaded_file.size > max_size:
                raise serializers.ValidationError({
                    "file": "File size cannot exceed 10 MB."
                })

            allowed_extensions = {".pdf", ".txt", ".docx", ".md"}
            extension = Path(uploaded_file.name).suffix.lower()

            if extension not in allowed_extensions:
                raise serializers.ValidationError({
                    "file": (
                        "Unsupported file type. Allowed types: "
                        "PDF, TXT, DOCX, and MD."
                    )
                })

        return attrs

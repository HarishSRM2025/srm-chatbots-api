
from rest_framework import serializers

from .models import Agent


class AgentSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(
        source="owner.username",
        read_only=True,
    )

    class Meta:
        model = Agent
        fields = [
            "id",
            "owner",
            "owner_username",
            "name",
            "description",
            "system_prompt",
            "model_name",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "owner_username",
            "created_at",
            "updated_at",
        ]

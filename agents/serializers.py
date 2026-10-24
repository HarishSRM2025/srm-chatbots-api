
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
            "is_public",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "owner_username",
            "model_name",
            "created_at",
            "updated_at",
        ]


    
    def validate_name(self, value):
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            existing_agents = Agent.objects.filter(
                owner=request.user,
                name=value,
            )

            if self.instance:
                existing_agents = existing_agents.exclude(
                    pk=self.instance.pk
                )

            if existing_agents.exists():
                raise serializers.ValidationError(
                    "You already have an agent with this name."
                )

        return value


from rest_framework import serializers

from .models import Agent
from chat.widget_origin import normalize_configured_origin


class AgentSerializer(serializers.ModelSerializer):
    allowed_origins = serializers.ListField(
        child=serializers.CharField(max_length=2048), max_length=50, required=False,
    )
    predefined_questions = serializers.ListField(
        child=serializers.CharField(max_length=500, allow_blank=False),
        max_length=20, required=False,
    )
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
            "allowed_origins",
            "predefined_questions",
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


    
    def validate_allowed_origins(self, value):
        origins = []
        for item in value:
            origin = normalize_configured_origin(item)
            if origin is None:
                raise serializers.ValidationError(
                    "Enter HTTP or HTTPS origins only, without paths, queries, or wildcards."
                )
            if origin not in origins:
                origins.append(origin)
        return origins

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


from rest_framework import serializers

from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = [
            "id",
            "role",
            "content",
            "created_at",
        ]
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(
        source="agent.name",
        read_only=True,
    )
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "agent",
            "agent_name",
            "title",
            "messages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "agent_name",
            "messages",
            "created_at",
            "updated_at",
        ]

    def validate_agent(self, agent):
        request = self.context.get("request")

        if request and agent.owner_id != request.user.id:
            raise serializers.ValidationError(
                "You do not have permission to use this agent."
            )

        return agent

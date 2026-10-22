
from rest_framework import serializers

from .models import WidgetConversation


class WidgetConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WidgetConversation
        fields = [
            "id",
            "title",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

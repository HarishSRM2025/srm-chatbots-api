
from rest_framework import serializers

from .models import WidgetMessage


class WidgetMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = WidgetMessage
        fields = [
            "id",
            "role",
            "content",
            "created_at",
        ]
        read_only_fields = fields

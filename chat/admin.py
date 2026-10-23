from django.contrib import admin

from .models import WidgetMessageRequest


@admin.register(WidgetMessageRequest)
class WidgetMessageRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "idempotency_key",
        "status",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "idempotency_key",
        "conversation__title",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )

from django.contrib import admin

from .models import Agent


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "model_name",
        "status",
        "created_at",
    )
    list_filter = ("status", "model_name", "created_at")
    search_fields = ("name", "owner__username", "owner__email")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
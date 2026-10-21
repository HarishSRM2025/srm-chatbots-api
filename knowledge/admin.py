from django.contrib import admin

from .models import KnowledgeSource,KnowledgeChunk


@admin.register(KnowledgeSource)
class KnowledgeSourceAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "agent",
        "source_type",
        "status",
        "created_at",
    )

    list_filter = (
        "source_type",
        "status",
        "created_at",
    )

    search_fields = (
        "title",
        "agent__name",
        "source_url",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)

@admin.register(KnowledgeChunk)
class KnowledgeChunkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "chunk_index",
        "created_at",
    )

    list_filter = ("created_at",)

    search_fields = (
        "content",
        "source__title",
        "source__agent__name",
    )

    readonly_fields = ("created_at",)

    ordering = ("source", "chunk_index")

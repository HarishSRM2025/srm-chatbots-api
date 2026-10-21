
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .chunking import create_source_chunks
from .models import KnowledgeSource
from .serializers import KnowledgeSourceSerializer


class KnowledgeSourceViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeSourceSerializer
    permission_classes = [IsAuthenticated]

    SUPPORTED_TYPES = [
        KnowledgeSource.SourceType.TEXT,
        KnowledgeSource.SourceType.FILE,
        KnowledgeSource.SourceType.URL,
    ]

    def get_queryset(self):
        return KnowledgeSource.objects.filter(
            agent__owner=self.request.user
        ).select_related("agent")

    def _process_source(self, source):
        """Process a supported source and return its chunk count."""
        if source.source_type not in self.SUPPORTED_TYPES:
            source.status = KnowledgeSource.Status.FAILED
            source.error_message = "Unsupported knowledge source type."
            source.save(
                update_fields=["status", "error_message", "updated_at"]
            )
            return None

        source.status = KnowledgeSource.Status.PROCESSING
        source.error_message = ""
        source.save(
            update_fields=["status", "error_message", "updated_at"]
        )

        try:
            return create_source_chunks(source)
        except Exception:
            source.refresh_from_db()
            source.status = KnowledgeSource.Status.FAILED
            source.error_message = (
                "Knowledge source processing failed. Please retry."
            )
            source.save(
                update_fields=["status", "error_message", "updated_at"]
            )
            return None

    def _processing_error_response(self, source):
        """Return an error while preserving the failed source record."""
        source.refresh_from_db()

        return Response(
            {
                "detail": (
                    "The knowledge source was saved, but processing failed. "
                    "You can retry using the process endpoint."
                ),
                "source_id": source.id,
                "status": source.status,
                "error_message": source.error_message,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        agent = serializer.validated_data["agent"]
        if agent.owner_id != request.user.id:
            raise PermissionDenied(
                "You can only add knowledge to your own agents."
            )

        source = serializer.save()
        chunk_count = self._process_source(source)

        if chunk_count is None:
            return self._processing_error_response(source)

        output_serializer = self.get_serializer(source)
        headers = self.get_success_headers(output_serializer.data)

        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)

        agent = serializer.validated_data.get("agent", instance.agent)
        if agent.owner_id != request.user.id:
            raise PermissionDenied(
                "You can only add knowledge to your own agents."
            )

        source = serializer.save()
        chunk_count = self._process_source(source)

        if chunk_count is None:
            return self._processing_error_response(source)

        output_serializer = self.get_serializer(source)

        return Response(output_serializer.data)

    def perform_create(self, serializer):
        # Creation is handled in create() so processing failures
        # can return an HTTP 500 response.
        pass

    def perform_update(self, serializer):
        # Updates are handled in update() so processing failures
        # can return an HTTP 500 response.
        pass

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        source = self.get_object()
        chunk_count = self._process_source(source)
        source.refresh_from_db()

        if chunk_count is None:
            return Response(
                {
                    "id": source.id,
                    "title": source.title,
                    "status": source.status,
                    "detail": source.error_message,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "id": source.id,
                "title": source.title,
                "status": source.status,
                "chunks_created": chunk_count,
            },
            status=status.HTTP_200_OK,
        )

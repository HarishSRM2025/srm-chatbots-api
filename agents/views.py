
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Agent
from .serializers import AgentSerializer


class AgentViewSet(viewsets.ModelViewSet):
    serializer_class = AgentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Agent.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

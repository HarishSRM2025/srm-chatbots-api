
from datetime import datetime, time, timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agents.models import Agent
from chat.models import Conversation, Message


class AnalyticsOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        today = timezone.localdate()
        start_date = today - timedelta(days=6)

        start_datetime = timezone.make_aware(
            datetime.combine(start_date, time.min)
        )

        agents = Agent.objects.filter(owner=user)
        conversations = Conversation.objects.filter(user=user)
        messages = Message.objects.filter(conversation__user=user)

        recent_conversations = conversations.filter(
            created_at__gte=start_datetime,
            created_at__lt=now,
        )

        daily_activity = (
            recent_conversations
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(total=Count("id"))
            .order_by("day")
        )

        activity_by_date = {
            item["day"].isoformat(): item["total"]
            for item in daily_activity
        }

        activity = [
            {
                "date": (start_date + timedelta(days=offset)).isoformat(),
                "conversations": activity_by_date.get(
                    (start_date + timedelta(days=offset)).isoformat(),
                    0,
                ),
            }
            for offset in range(7)
        ]

        agent_usage = list(
            agents.annotate(
                conversation_count=Count(
                    "conversations",
                    distinct=True,
                ),
                message_count=Count(
                    "conversations__messages",
                    distinct=True,
                ),
            )
            .values(
                "id",
                "name",
                "status",
                "conversation_count",
                "message_count",
            )
            .order_by("-conversation_count", "name")
        )

        return Response(
            {
                "summary": {
                    "total_agents": agents.count(),
                    "active_agents": agents.filter(
                        status=Agent.Status.ACTIVE
                    ).count(),
                    "total_conversations": conversations.count(),
                    "total_messages": messages.count(),
                    "user_messages": messages.filter(
                        role=Message.Role.USER
                    ).count(),
                    "assistant_messages": messages.filter(
                        role=Message.Role.ASSISTANT
                    ).count(),
                    "conversations_last_7_days": (
                        recent_conversations.count()
                    ),
                },
                "daily_activity": activity,
                "agent_usage": agent_usage,
            }
        )

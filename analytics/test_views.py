
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from agents.models import Agent
from chat.models import Conversation, Message


User = get_user_model()


class AnalyticsOverviewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="analytics_user",
            email="analytics@example.com",
            password="TestPass!987654",
        )
        self.other_user = User.objects.create_user(
            username="other_analytics_user",
            email="other@example.com",
            password="TestPass!987654",
        )

        self.agent = Agent.objects.create(
            owner=self.user,
            name="Support Agent",
            description="Support test agent",
            system_prompt="You are a helpful support assistant.",
        )
        self.other_agent = Agent.objects.create(
            owner=self.other_user,
            name="Private Agent",
            description="Private test agent",
            system_prompt="You are a private assistant.",
        )

        self.url = reverse("analytics-overview")

    def create_conversation(self, user, agent, title):
        return Conversation.objects.create(
            user=user,
            agent=agent,
            title=title,
        )

    def test_authentication_is_required(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_overview_counts_only_current_users_data(self):
        self.client.force_authenticate(user=self.user)

        conversation = self.create_conversation(
            self.user,
            self.agent,
            "My conversation",
        )
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="Hello",
        )
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Hi there",
        )

        other_conversation = self.create_conversation(
            self.other_user,
            self.other_agent,
            "Another user's conversation",
        )
        Message.objects.create(
            conversation=other_conversation,
            role=Message.Role.USER,
            content="Private message",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        summary = response.data["summary"]
        self.assertEqual(summary["total_agents"], 1)
        self.assertEqual(summary["active_agents"], 1)
        self.assertEqual(summary["total_conversations"], 1)
        self.assertEqual(summary["total_messages"], 2)
        self.assertEqual(summary["user_messages"], 1)
        self.assertEqual(summary["assistant_messages"], 1)

        self.assertEqual(len(response.data["daily_activity"]), 7)
        self.assertEqual(len(response.data["agent_usage"]), 1)
        self.assertEqual(
            response.data["agent_usage"][0]["name"],
            "Support Agent",
        )

    def test_empty_account_returns_zero_counts(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["total_agents"], 1)
        self.assertEqual(
            response.data["summary"]["total_conversations"],
            0,
        )
        self.assertEqual(response.data["summary"]["total_messages"], 0)
        self.assertEqual(
            sum(
                day["conversations"]
                for day in response.data["daily_activity"]
            ),
            0,
        )

    def test_inactive_agents_are_not_counted_as_active(self):
        self.agent.status = Agent.Status.INACTIVE
        self.agent.save(update_fields=["status"])

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["total_agents"], 1)
        self.assertEqual(response.data["summary"]["active_agents"], 0)

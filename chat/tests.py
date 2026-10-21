
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from agents.models import Agent
from chat.models import Conversation, Message
from knowledge.models import KnowledgeChunk, KnowledgeSource


class ConversationAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()

        self.user1 = User.objects.create_user(
            username="chat_test_user1",
            password="TestPass123!safe",
        )
        self.user2 = User.objects.create_user(
            username="chat_test_user2",
            password="TestPass123!safe",
        )

        self.agent1 = Agent.objects.create(
            owner=self.user1,
            name="Nursing Assistant",
            system_prompt="Answer nursing questions using the provided context.",
        )
        self.agent2 = Agent.objects.create(
            owner=self.user2,
            name="Engineering Assistant",
            system_prompt="Answer engineering questions using the provided context.",
        )

        self.conversation = Conversation.objects.create(
            agent=self.agent1,
            user=self.user1,
            title="Admission questions",
        )

        self.list_url = "/api/chat/conversations/"
        self.detail_url = (
            f"/api/chat/conversations/{self.conversation.id}/"
        )
        self.send_url = f"{self.detail_url}send/"

    def test_unauthenticated_user_cannot_list_conversations(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_user_can_create_conversation_for_own_agent(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            self.list_url,
            {"agent": self.agent1.id, "title": "New conversation"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )
        self.assertTrue(
            Conversation.objects.filter(
                user=self.user1,
                agent=self.agent1,
                title="New conversation",
            ).exists()
        )

    def test_user_cannot_create_conversation_for_another_users_agent(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            self.list_url,
            {"agent": self.agent2.id},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_user_only_sees_own_conversations(self):
        other_conversation = Conversation.objects.create(
            agent=self.agent2,
            user=self.user2,
            title="Private engineering conversation",
        )
        self.client.force_authenticate(user=self.user1)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [item["id"] for item in response.data]

        self.assertIn(self.conversation.id, returned_ids)
        self.assertNotIn(other_conversation.id, returned_ids)

    def test_user_cannot_retrieve_another_users_conversation(self):
        other_conversation = Conversation.objects.create(
            agent=self.agent2,
            user=self.user2,
            title="Private conversation",
        )
        self.client.force_authenticate(user=self.user1)

        response = self.client.get(
            f"{self.list_url}{other_conversation.id}/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_empty_message_is_rejected(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            self.send_url,
            {"content": "   "},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            Message.objects.filter(conversation=self.conversation).count(),
            0,
        )

    def test_inactive_agent_cannot_receive_messages(self):
        self.agent1.status = Agent.Status.INACTIVE
        self.agent1.save(update_fields=["status"])

        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            self.send_url,
            {"content": "What are the admission requirements?"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            Message.objects.filter(conversation=self.conversation).count(),
            0,
        )

    @patch("chat.views.generate_response")
    @patch("chat.views.retrieve_relevant_chunks")
    def test_send_message_uses_agent_knowledge_and_saves_messages(
        self,
        mock_retrieve,
        mock_generate,
    ):
        source = KnowledgeSource.objects.create(
            agent=self.agent1,
            title="Nursing Admissions FAQ",
            source_type=KnowledgeSource.SourceType.TEXT,
            text_content="Nursing applicants need biology.",
            status=KnowledgeSource.Status.READY,
        )
        chunk = KnowledgeChunk.objects.create(
            source=source,
            content="Nursing applicants need biology.",
            chunk_index=0,
        )
        mock_retrieve.return_value = [chunk]
        mock_generate.return_value = "Biology is required."

        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            self.send_url,
            {"content": "Is biology required?"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )
        mock_retrieve.assert_called_once_with(
            agent_id=self.agent1.id,
            query="Is biology required?",
            limit=5,
        )
        mock_generate.assert_called_once()

        prompt = mock_generate.call_args.kwargs["prompt"]
        self.assertIn("Nursing applicants need biology.", prompt)
        self.assertIn("Is biology required?", prompt)

        self.assertEqual(
            Message.objects.filter(
                conversation=self.conversation
            ).count(),
            2,
        )
        self.assertEqual(
            response.data["assistant_message"]["content"],
            "Biology is required.",
        )
        self.assertEqual(
            response.data["sources"][0]["title"],
            "Nursing Admissions FAQ",
        )

    @patch("chat.views.generate_response")
    def test_ollama_failure_returns_service_unavailable(
        self,
        mock_generate,
    ):
        from chat.ollama_client import OllamaError

        mock_generate.side_effect = OllamaError("Internal test detail")
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            self.send_url,
            {"content": "Explain admission eligibility."},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertNotIn("Internal test detail", str(response.data))

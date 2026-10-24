
import hashlib
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from agents.models import Agent
from chat.models import (
    Conversation,
    Message,
    WidgetConversation,
    WidgetMessage,
    WidgetSession,
)
from chat.widget_origin import is_origin_allowed, normalize_origin
from chat.widget_security import create_widget_session, get_widget_session
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


    def test_message_over_10000_characters_is_rejected(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            self.send_url,
            {"content": "a" * 10001},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            Message.objects.filter(
                conversation=self.conversation
            ).count(),
            0,
        )

    @patch("chat.views.generate_response")
    def test_ollama_failure_preserves_user_message_only(
        self,
        mock_generate,
    ):
        from chat.ollama_client import OllamaError

        mock_generate.side_effect = OllamaError(
            "Internal test detail"
        )
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

        messages = Message.objects.filter(
            conversation=self.conversation
        )

        self.assertEqual(messages.count(), 1)

        saved_message = messages.get()
        self.assertEqual(saved_message.role, Message.Role.USER)
        self.assertEqual(
            saved_message.content,
            "Explain admission eligibility.",
        )
        self.assertNotIn("Internal test detail", str(response.data))



class WidgetSessionSecurityTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="widget_owner",
            password="TestPass123!safe",
        )
        self.other_owner = User.objects.create_user(
            username="widget_other_owner",
            password="TestPass123!safe",
        )

        self.agent = Agent.objects.create(
            owner=self.owner,
            name="Public Widget Agent",
            system_prompt="Answer helpfully.",
            is_public=True,
        )
        self.other_agent = Agent.objects.create(
            owner=self.other_owner,
            name="Other Public Agent",
            system_prompt="Answer helpfully.",
            is_public=True,
        )

    def test_session_creation_returns_token_but_stores_only_hash(self):
        session, token = create_widget_session(self.agent)

        self.assertTrue(token)
        self.assertNotEqual(session.token_hash, token)
        self.assertEqual(
            len(session.token_hash),
            64,
        )
        self.assertEqual(
            session.token_hash,
            __import__("hashlib").sha256(
                token.encode("utf-8")
            ).hexdigest(),
        )

    def test_valid_session_can_be_retrieved_for_its_agent(self):
        session, token = create_widget_session(self.agent)

        retrieved = get_widget_session(token, self.agent.id)

        self.assertEqual(retrieved, session)

    def test_session_cannot_be_used_for_another_agent(self):
        _, token = create_widget_session(self.agent)

        retrieved = get_widget_session(token, self.other_agent.id)

        self.assertIsNone(retrieved)

    def test_expired_session_is_rejected(self):
        session, token = create_widget_session(self.agent)
        session.expires_at = timezone.now() - timedelta(seconds=1)
        session.save(update_fields=["expires_at"])

        self.assertIsNone(
            get_widget_session(token, self.agent.id)
        )

    def test_revoked_session_is_rejected(self):
        session, token = create_widget_session(self.agent)
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])

        self.assertIsNone(
            get_widget_session(token, self.agent.id)
        )

    def test_private_agent_session_is_rejected(self):
        _, token = create_widget_session(self.agent)
        self.agent.is_public = False
        self.agent.save(update_fields=["is_public"])

        self.assertIsNone(
            get_widget_session(token, self.agent.id)
        )

    def test_inactive_agent_session_is_rejected(self):
        _, token = create_widget_session(self.agent)
        self.agent.status = Agent.Status.INACTIVE
        self.agent.save(update_fields=["status"])

        self.assertIsNone(
            get_widget_session(token, self.agent.id)
        )

    def test_invalid_or_oversized_tokens_are_rejected(self):
        self.assertIsNone(
            get_widget_session("", self.agent.id)
        )
        self.assertIsNone(
            get_widget_session(None, self.agent.id)
        )
        self.assertIsNone(
            get_widget_session("x" * 257, self.agent.id)
        )



class WidgetSessionCreateAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="widget_api_owner",
            password="TestPass123!safe",
        )
        self.public_agent = Agent.objects.create(
            owner=self.owner,
            name="Public Widget API Agent",
            system_prompt="Answer helpfully.",
            status=Agent.Status.ACTIVE,
            is_public=True,
        )
        self.private_agent = Agent.objects.create(
            owner=self.owner,
            name="Private Widget API Agent",
            system_prompt="Answer helpfully.",
            status=Agent.Status.ACTIVE,
            is_public=False,
        )
        self.inactive_agent = Agent.objects.create(
            owner=self.owner,
            name="Inactive Widget API Agent",
            system_prompt="Answer helpfully.",
            status=Agent.Status.INACTIVE,
            is_public=True,
        )
        self.url = "/api/chat/widget/sessions/"

    def test_public_active_agent_can_create_widget_session(self):
        response = self.client.post(
            self.url,
            {"agent_id": self.public_agent.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("session_token", response.data)
        self.assertIn("expires_at", response.data)
        self.assertEqual(response.data["agent_id"], self.public_agent.id)
        self.assertNotIn("token_hash", response.data)

        session = WidgetSession.objects.get(agent=self.public_agent)
        self.assertNotEqual(
            session.token_hash,
            response.data["session_token"],
        )
        self.assertTrue(
            get_widget_session(
                response.data["session_token"],
                self.public_agent.id,
            )
        )

    def test_private_agent_cannot_create_widget_session(self):
        response = self.client.post(
            self.url,
            {"agent_id": self.private_agent.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(
            WidgetSession.objects.filter(agent=self.private_agent).exists()
        )

    def test_inactive_agent_cannot_create_widget_session(self):
        response = self.client.post(
            self.url,
            {"agent_id": self.inactive_agent.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(
            WidgetSession.objects.filter(agent=self.inactive_agent).exists()
        )

    def test_missing_agent_id_returns_validation_error(self):
        response = self.client.post(
            self.url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("agent_id", response.data)
        self.assertEqual(WidgetSession.objects.count(), 0)

    def test_allowed_origin_can_create_widget_session(self):
        self.public_agent.allowed_origins = ["https://example.com"]
        self.public_agent.save(update_fields=["allowed_origins"])

        response = self.client.post(
            self.url,
            {"agent_id": self.public_agent.id},
            format="json",
            HTTP_ORIGIN="https://example.com",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertTrue(
            WidgetSession.objects.filter(
                agent=self.public_agent
            ).exists()
        )

    def test_disallowed_origin_cannot_create_widget_session(self):
        self.public_agent.allowed_origins = ["https://example.com"]
        self.public_agent.save(update_fields=["allowed_origins"])

        response = self.client.post(
            self.url,
            {"agent_id": self.public_agent.id},
            format="json",
            HTTP_ORIGIN="https://malicious.example",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertFalse(
            WidgetSession.objects.filter(
                agent=self.public_agent
            ).exists()
        )


    def test_session_rate_limit_returns_429(self):
        from django.core.cache import cache
        from unittest.mock import patch

        cache.clear()

        with patch(
            "chat.throttles.WidgetSessionRateThrottle.get_rate",
            return_value="2/minute",
        ):
            self.client.post(
                self.url,
                {"agent_id": self.public_agent.id},
                format="json",
            )
            self.client.post(
                self.url,
                {"agent_id": self.public_agent.id},
                format="json",
            )
            response = self.client.post(
                self.url,
                {"agent_id": self.public_agent.id},
                format="json",
            )

        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
        cache.clear()




class WidgetConversationCreateAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="widget_conversation_owner",
            password="TestPass123!safe",
        )
        self.other_owner = User.objects.create_user(
            username="widget_conversation_other",
            password="TestPass123!safe",
        )

        self.agent = Agent.objects.create(
            owner=self.owner,
            name="Widget Conversation Agent",
            system_prompt="Answer helpfully.",
            status=Agent.Status.ACTIVE,
            is_public=True,
        )
        self.other_agent = Agent.objects.create(
            owner=self.other_owner,
            name="Other Widget Conversation Agent",
            system_prompt="Answer helpfully.",
            status=Agent.Status.ACTIVE,
            is_public=True,
        )

        self.session, self.token = create_widget_session(self.agent)
        self.url = "/api/chat/widget/conversations/"

    def test_valid_session_can_create_conversation(self):
        response = self.client.post(
            self.url,
            {"agent_id": self.agent.id, "title": "Visitor question"},
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )
        self.assertEqual(response.data["title"], "Visitor question")
        self.assertTrue(
            WidgetConversation.objects.filter(
                session=self.session,
                title="Visitor question",
            ).exists()
        )

    def test_missing_session_token_is_rejected(self):
        response = self.client.post(
            self.url,
            {"agent_id": self.agent.id},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_session_cannot_create_conversation_for_another_agent(self):
        response = self.client.post(
            self.url,
            {"agent_id": self.other_agent.id},
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(WidgetConversation.objects.count(), 0)

    def test_expired_session_cannot_create_conversation(self):
        self.session.expires_at = timezone.now() - timedelta(seconds=1)
        self.session.save(update_fields=["expires_at"])

        response = self.client.post(
            self.url,
            {"agent_id": self.agent.id},
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(WidgetConversation.objects.count(), 0)

    def test_missing_agent_id_is_rejected(self):
        response = self.client.post(
            self.url,
            {},
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(WidgetConversation.objects.count(), 0)

    def test_allowed_origin_can_create_conversation(self):
        self.agent.allowed_origins = ["https://example.com"]
        self.agent.save(update_fields=["allowed_origins"])

        response = self.client.post(
            self.url,
            {
                "agent_id": self.agent.id,
                "title": "Allowed origin conversation",
            },
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
            HTTP_ORIGIN="https://example.com",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )
        self.assertTrue(
            WidgetConversation.objects.filter(
                session=self.session,
                title="Allowed origin conversation",
            ).exists()
        )

    def test_disallowed_origin_cannot_create_conversation(self):
        self.agent.allowed_origins = ["https://example.com"]
        self.agent.save(update_fields=["allowed_origins"])

        response = self.client.post(
            self.url,
            {
                "agent_id": self.agent.id,
                "title": "Rejected origin conversation",
            },
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
            HTTP_ORIGIN="https://malicious.example",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertFalse(
            WidgetConversation.objects.filter(
                session=self.session,
            ).exists()
        )

    def test_invalid_title_is_rejected(self):
        response = self.client.post(
            self.url,
            {"agent_id": self.agent.id, "title": 123},
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(WidgetConversation.objects.count(), 0)



class WidgetConversationHistoryAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="widget_history_owner",
            password="TestPass123!safe",
        )
        self.agent = Agent.objects.create(
            owner=self.owner,
            name="Widget History Agent",
            system_prompt="Answer helpfully.",
            status=Agent.Status.ACTIVE,
            is_public=True,
        )
        self.session, self.token = create_widget_session(self.agent)
        self.conversation = WidgetConversation.objects.create(
            session=self.session,
            title="Previous questions",
        )
        self.user_message = WidgetMessage.objects.create(
            conversation=self.conversation,
            role=WidgetMessage.Role.USER,
            content="What are your opening hours?",
        )
        self.assistant_message = WidgetMessage.objects.create(
            conversation=self.conversation,
            role=WidgetMessage.Role.ASSISTANT,
            content="Please check the institution's published hours.",
        )
        self.url = (
            f"/api/chat/widget/conversations/{self.conversation.id}/"
        )

    def test_valid_session_can_retrieve_conversation_history(self):
        response = self.client.get(
            self.url,
            {"agent_id": self.agent.id},
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["conversation"]["id"],
            self.conversation.id,
        )
        self.assertEqual(len(response.data["messages"]), 2)
        self.assertEqual(
            response.data["messages"][0]["content"],
            "What are your opening hours?",
        )
        self.assertEqual(
            response.data["messages"][1]["content"],
            "Please check the institution's published hours.",
        )

    def test_missing_session_token_is_rejected(self):
        response = self.client.get(
            self.url,
            {"agent_id": self.agent.id},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_missing_agent_id_is_rejected(self):
        response = self.client.get(
            self.url,
            HTTP_X_WIDGET_SESSION=self.token,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_conversation_from_another_session_is_not_accessible(self):
        other_session, other_token = create_widget_session(self.agent)

        response = self.client.get(
            self.url,
            {"agent_id": self.agent.id},
            HTTP_X_WIDGET_SESSION=other_token,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_disallowed_origin_is_rejected(self):
        self.agent.allowed_origins = ["https://example.com"]
        self.agent.save(update_fields=["allowed_origins"])

        response = self.client.get(
            self.url,
            {"agent_id": self.agent.id},
            HTTP_X_WIDGET_SESSION=self.token,
            HTTP_ORIGIN="https://malicious.example",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_expired_session_is_rejected(self):
        self.session.expires_at = timezone.now() - timedelta(seconds=1)
        self.session.save(update_fields=["expires_at"])

        response = self.client.get(
            self.url,
            {"agent_id": self.agent.id},
            HTTP_X_WIDGET_SESSION=self.token,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class WidgetMessageCreateAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="widget_message_owner",
            email="widget_message_owner@example.com",
            password="TestPass!987654",
        )

        self.agent = Agent.objects.create(
            owner=self.user,
            name="Public Test Agent",
            description="Agent used for widget message tests",
            system_prompt="You are a helpful institutional assistant.",
            model_name="qwen3:4b",
            status=Agent.Status.ACTIVE,
            is_public=True,
        )

        self.session, self.token = create_widget_session(self.agent)

        self.conversation = WidgetConversation.objects.create(
            session=self.session,
            title="Test conversation",
        )

        self.url = (
            f"/api/chat/widget/conversations/"
            f"{self.conversation.pk}/messages/"
        )


    def send_message(
        self,
        content,
        token=None,
        agent_id=None,
        idempotency_key=None,
    ):
        return self.client.post(
            self.url,
            {
                "agent_id": agent_id or self.agent.pk,
                "content": content,
            },
            format="json",
            HTTP_X_WIDGET_SESSION=token or self.token,
            HTTP_IDEMPOTENCY_KEY=(
                idempotency_key or str(uuid.uuid4())
            ),
        )


    @patch("chat.views.generate_response")
    @patch("chat.views.retrieve_relevant_chunks")
    def test_sends_message_and_returns_ai_response(
        self, mock_retrieve, mock_generate
    ):
        mock_retrieve.return_value = []
        mock_generate.return_value = "Hello! How can I help you?"

        response = self.send_message("Hello")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["user_message"]["content"], "Hello"
        )
        self.assertEqual(
            response.data["user_message"]["role"], "user"
        )
        self.assertEqual(
            response.data["assistant_message"]["content"],
            "Hello! How can I help you?",
        )
        self.assertEqual(
            response.data["assistant_message"]["role"], "assistant"
        )
        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation
            ).count(),
            2,
        )

        mock_retrieve.assert_called_once_with(
            agent_id=self.agent.pk,
            query="Hello",
            limit=5,
        )
        mock_generate.assert_called_once()

    @patch("chat.views.generate_response")
    @patch("chat.views.retrieve_relevant_chunks")
    def test_passes_agent_knowledge_to_ai(
        self, mock_retrieve, mock_generate
    ):
        source = KnowledgeSource.objects.create(
            agent=self.agent,
            title="Admissions Guide",
            source_type=KnowledgeSource.SourceType.TEXT,
            text_content="Admission information",
            status=KnowledgeSource.Status.READY,
        )
        chunk = KnowledgeChunk.objects.create(
            source=source,
            content="Applications open in June.",
            chunk_index=0,
        )

        mock_retrieve.return_value = [chunk]
        mock_generate.return_value = "Applications open in June."

        response = self.send_message("When do applications open?")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        prompt = mock_generate.call_args.kwargs["prompt"]
        self.assertIn("Admissions Guide", prompt)
        self.assertIn("Applications open in June.", prompt)

        self.assertEqual(
            response.data["sources"],
            [{"title": "Admissions Guide", "chunk_index": 0}],
        )

    def test_rejects_missing_session_token(self):
        response = self.client.post(
            self.url,
            {
                "agent_id": self.agent.pk,
                "content": "Hello",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code, status.HTTP_401_UNAUTHORIZED
        )
        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation
            ).count(),
            0,
        )

    def test_rejects_invalid_session_token(self):
        response = self.send_message(
            "Hello",
            token="invalid-widget-token",
        )

        self.assertEqual(
            response.status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_rejects_token_for_different_agent(self):
        other_agent = Agent.objects.create(
            owner=self.user,
            name="Another Public Agent",
            description="Another test agent",
            system_prompt="You are helpful.",
            model_name="qwen3:4b",
            status=Agent.Status.ACTIVE,
            is_public=True,
        )

        response = self.send_message(
            "Hello",
            agent_id=other_agent.pk,
        )

        self.assertEqual(
            response.status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_cannot_access_another_sessions_conversation(self):
        another_session, another_token = create_widget_session(
            self.agent
        )
        another_conversation = WidgetConversation.objects.create(
            session=another_session,
            title="Private visitor conversation",
        )

        response = self.client.post(
            f"/api/chat/widget/conversations/"
            f"{another_conversation.pk}/messages/",
            {
                "agent_id": self.agent.pk,
                "content": "Hello",
            },
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=another_conversation
            ).count(),
            0,
        )

    def test_rejects_empty_message(self):
        response = self.send_message("   ")

        self.assertEqual(
            response.status_code, status.HTTP_400_BAD_REQUEST
        )

    def test_rejects_oversized_message(self):
        response = self.send_message("x" * 10001)

        self.assertEqual(
            response.status_code, status.HTTP_400_BAD_REQUEST
        )

    @patch("chat.views.generate_response")
    @patch("chat.views.retrieve_relevant_chunks")
    def test_ollama_failure_returns_service_unavailable(
        self, mock_retrieve, mock_generate
    ):
        from chat.ollama_client import OllamaError

        mock_retrieve.return_value = []
        mock_generate.side_effect = OllamaError("Test connection failure")

        response = self.send_message("Hello")

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation,
                role=WidgetMessage.Role.USER,
            ).count(),
            1,
        )

        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation,
                role=WidgetMessage.Role.ASSISTANT,
            ).count(),
            0,
        )


    @patch("chat.views.generate_response")
    @patch("chat.views.retrieve_relevant_chunks")
    def test_allowed_origin_can_send_message(
        self, mock_retrieve, mock_generate
    ):
        self.agent.allowed_origins = ["https://example.com"]
        self.agent.save(update_fields=["allowed_origins"])

        mock_retrieve.return_value = []
        mock_generate.return_value = "Hello from the assistant."

        response = self.client.post(
            self.url,
            {
                "agent_id": self.agent.pk,
                "content": "Hello",
            },
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
            HTTP_ORIGIN="https://example.com",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )
        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation
            ).count(),
            2,
        )

    def test_disallowed_origin_cannot_send_message(self):
        self.agent.allowed_origins = ["https://example.com"]
        self.agent.save(update_fields=["allowed_origins"])

        response = self.client.post(
            self.url,
            {
                "agent_id": self.agent.pk,
                "content": "Hello",
            },
            format="json",
            HTTP_X_WIDGET_SESSION=self.token,
            HTTP_ORIGIN="https://malicious.example",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation
            ).count(),
            0,
        )

    def test_message_rate_limit_returns_429(self):
        from django.core.cache import cache
        from unittest.mock import patch

        cache.clear()

        with patch(
            "chat.throttles.WidgetMessageRateThrottle.get_rate",
            return_value="2/minute",
        ):
            with patch("chat.views.generate_response") as mock_generate:
                with patch(
                    "chat.views.retrieve_relevant_chunks",
                    return_value=[],
                ):
                    mock_generate.return_value = "Test response"

                    self.send_message("First message")
                    self.send_message("Second message")
                    response = self.send_message("Third message")

        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
        cache.clear()


    @patch("chat.views.generate_response")
    def test_repeated_idempotency_key_returns_original_response(
        self,
        mock_generate,
    ):
        mock_generate.return_value = "Hello from the AI"
        key = str(uuid.uuid4())

        first_response = self.send_message(
            "Hello",
            idempotency_key=key,
        )
        second_response = self.send_message(
            "Hello",
            idempotency_key=key,
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)

        self.assertEqual(
            first_response.data,
            second_response.data,
        )
        self.assertEqual(mock_generate.call_count, 1)

        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation,
                role=WidgetMessage.Role.USER,
            ).count(),
            1,
        )
        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation,
                role=WidgetMessage.Role.ASSISTANT,
            ).count(),
            1,
        )


    @patch("chat.views.generate_response")
    def test_reusing_idempotency_key_with_different_content_returns_conflict(
        self,
        mock_generate,
    ):
        mock_generate.return_value = "Hello from the AI"
        key = str(uuid.uuid4())

        first_response = self.send_message(
            "Hello",
            idempotency_key=key,
        )
        second_response = self.send_message(
            "Tell me about admissions",
            idempotency_key=key,
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_409_CONFLICT,
        )
        self.assertEqual(mock_generate.call_count, 1)

        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation,
                role=WidgetMessage.Role.USER,
            ).count(),
            1,
        )

    @patch("chat.views.generate_response")
    def test_processing_idempotency_key_returns_conflict(
        self,
        mock_generate,
    ):
        from chat.models import WidgetMessageRequest

        content = "Hello"
        key = str(uuid.uuid4())
        content_hash = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

        user_message = WidgetMessage.objects.create(
            conversation=self.conversation,
            role=WidgetMessage.Role.USER,
            content=content,
        )

        WidgetMessageRequest.objects.create(
            conversation=self.conversation,
            idempotency_key=key,
            content_hash=content_hash,
            status=WidgetMessageRequest.Status.PROCESSING,
            user_message=user_message,
        )

        response = self.send_message(
            content,
            idempotency_key=key,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )
        mock_generate.assert_not_called()

        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation,
                role=WidgetMessage.Role.USER,
            ).count(),
            1,
        )
        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation,
                role=WidgetMessage.Role.ASSISTANT,
            ).count(),
            0,
        )

    @patch("chat.views.generate_response")
    def test_failed_request_can_be_retried_with_same_key(
        self,
        mock_generate,
    ):
        from chat.views import OllamaError

        mock_generate.side_effect = [
            OllamaError("Local AI service unavailable"),
            "Recovered AI response",
        ]
        key = str(uuid.uuid4())

        first_response = self.send_message(
            "Hello",
            idempotency_key=key,
        )
        second_response = self.send_message(
            "Hello",
            idempotency_key=key,
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(mock_generate.call_count, 2)

        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation,
                role=WidgetMessage.Role.USER,
            ).count(),
            1,
        )
        self.assertEqual(
            WidgetMessage.objects.filter(
                conversation=self.conversation,
                role=WidgetMessage.Role.ASSISTANT,
            ).count(),
            1,
        )


class WidgetOriginValidationTests(SimpleTestCase):
    def test_normalizes_scheme_hostname_and_default_port(self):
        self.assertEqual(
            normalize_origin("HTTPS://Example.com:443"),
            "https://example.com",
        )

    def test_normalizes_http_default_port(self):
        self.assertEqual(
            normalize_origin("http://Example.com:80"),
            "http://example.com",
        )

    def test_rejects_null_origin(self):
        self.assertIsNone(normalize_origin("null"))

    def test_rejects_origin_with_path(self):
        self.assertIsNone(
            normalize_origin("https://example.com/page")
        )

    def test_rejects_invalid_origin(self):
        self.assertIsNone(normalize_origin("not-a-valid-origin"))

    def test_allows_configured_origin(self):
        self.assertTrue(
            is_origin_allowed(
                "https://example.com",
                ["https://example.com"],
            )
        )

    def test_rejects_unconfigured_origin(self):
        self.assertFalse(
            is_origin_allowed(
                "https://attacker.example",
                ["https://example.com"],
            )
        )

    def test_rejects_origin_when_allowlist_is_empty(self):
        self.assertFalse(
            is_origin_allowed("https://example.com", [])
        )

    def test_rejects_malformed_allowlist(self):
        self.assertFalse(
            is_origin_allowed(
                "https://example.com",
                "https://example.com",
            )
        )

    def test_allows_missing_origin_for_token_validation(self):
        self.assertTrue(
            is_origin_allowed(None, [])
        )




class WidgetMessageConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="widget_concurrency_owner",
            email="widget_concurrency_owner@example.com",
            password="TestPass!987654",
        )

        self.agent = Agent.objects.create(
            owner=self.user,
            name="Concurrency Test Agent",
            description="Agent used for widget concurrency tests",
            system_prompt="You are a helpful assistant.",
            model_name="qwen3:4b",
            status=Agent.Status.ACTIVE,
            is_public=True,
        )

        self.session, self.token = create_widget_session(self.agent)
        self.conversation = WidgetConversation.objects.create(
            session=self.session,
            title="Concurrency test conversation",
        )
        self.url = (
            f"/api/chat/widget/conversations/"
            f"{self.conversation.pk}/messages/"
        )

    def test_duplicate_request_while_first_is_processing(self):
        ai_started = threading.Event()
        release_ai = threading.Event()
        key = str(uuid.uuid4())
        content = "Hello during concurrency testing"

        def generate_response_side_effect(*args, **kwargs):
            ai_started.set()
            if not release_ai.wait(timeout=20):
                raise TimeoutError("Timed out waiting to release mocked AI")
            return "Concurrent AI response"

        def send_first_request():
            close_old_connections()
            try:
                client = APIClient()
                return client.post(
                    self.url,
                    {
                        "agent_id": self.agent.pk,
                        "content": content,
                    },
                    format="json",
                    HTTP_X_WIDGET_SESSION=self.token,
                    HTTP_IDEMPOTENCY_KEY=key,
                )
            finally:
                close_old_connections()

        try:
            with patch(
                "chat.views.retrieve_relevant_chunks",
                return_value=[],
            ), patch(
                "chat.views.generate_response",
                side_effect=generate_response_side_effect,
            ) as mock_generate:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    first_future = executor.submit(send_first_request)

                    self.assertTrue(
                        ai_started.wait(timeout=15),
                        "The first request did not reach AI generation",
                    )

                    # The first request has claimed the idempotency key
                    # and is paused inside AI generation.
                    close_old_connections()
                    try:
                        second_client = APIClient()
                        second_response = second_client.post(
                            self.url,
                            {
                                "agent_id": self.agent.pk,
                                "content": content,
                            },
                            format="json",
                            HTTP_X_WIDGET_SESSION=self.token,
                            HTTP_IDEMPOTENCY_KEY=key,
                        )
                    finally:
                        close_old_connections()

                    self.assertEqual(
                        second_response.status_code,
                        status.HTTP_409_CONFLICT,
                    )

                    release_ai.set()
                    first_response = first_future.result(timeout=30)

                self.assertEqual(
                    first_response.status_code,
                    status.HTTP_200_OK,
                )
                self.assertEqual(mock_generate.call_count, 1)

            self.assertEqual(
                WidgetMessage.objects.filter(
                    conversation=self.conversation,
                    role=WidgetMessage.Role.USER,
                ).count(),
                1,
            )
            self.assertEqual(
                WidgetMessage.objects.filter(
                    conversation=self.conversation,
                    role=WidgetMessage.Role.ASSISTANT,
                ).count(),
                1,
            )

        finally:
            # Always unblock the worker if an assertion fails.
            release_ai.set()

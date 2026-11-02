from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from agents.models import Agent
from chat.models import Conversation
from knowledge.context import build_sources
from knowledge.models import KnowledgeSource, KnowledgeChunk


class QuestionsAndSourcesTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="questions", password="test-password")
        self.agent = Agent.objects.create(owner=self.user, name="Admissions", system_prompt="Help", is_public=True)
        self.client.force_authenticate(self.user)
        self.source = KnowledgeSource.objects.create(agent=self.agent, title="Admissions", source_type="url", source_url="https://example.edu/admissions", status="ready")
        self.chunk = KnowledgeChunk.objects.create(source=self.source, chunk_index=0, content="Admissions are open.")

    def test_questions_can_be_updated_and_cleared(self):
        url = f"/api/agents/{self.agent.pk}/"
        response = self.client.patch(url, {"predefined_questions": ["How do I apply?"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["predefined_questions"], ["How do I apply?"])
        for invalid in [[" "], ["a" * 501], ["Question"] * 21, "Question"]:
            self.assertEqual(self.client.patch(url, {"predefined_questions": invalid}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"predefined_questions": []}, format="json").data["predefined_questions"], [])

    @patch("chat.views.generate_response", return_value="Admissions are open.")
    def test_independent_question_and_persisted_links(self, generate):
        self.agent.predefined_questions = ["How do I apply?"]
        self.agent.save()
        conversation = Conversation.objects.create(agent=self.agent, user=self.user)
        url = f"/api/chat/conversations/{conversation.pk}/"
        response = self.client.post(url + "send/", {"content": "Are admissions open?"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assistant_message"]["sources"][0]["url"], self.source.source_url)
        self.assertIn(self.source.source_url, generate.call_args.kwargs["prompt"])
        self.assertEqual(self.client.get(url).data["messages"][-1]["sources"], response.data["sources"])
        for content in [None, 123, ""]:
            self.assertEqual(self.client.post(url + "send/", {"content": content}, format="json").status_code, 400)

    @patch("chat.views.generate_response", return_value="Admissions are open.")
    def test_widget_questions_links_history_and_replay(self, generate):
        self.agent.predefined_questions = ["Are admissions open?"]
        self.agent.save()
        self.client.force_authenticate(user=None)
        session = self.client.post("/api/chat/widget/sessions/", {"agent_id": self.agent.pk}, format="json")
        self.assertEqual(session.status_code, 201)
        self.assertEqual(session.data["predefined_questions"], self.agent.predefined_questions)
        self.client.credentials(HTTP_X_WIDGET_SESSION=session.data["session_token"])
        conversation = self.client.post("/api/chat/widget/conversations/", {"agent_id": self.agent.pk}, format="json")
        url = f"/api/chat/widget/conversations/{conversation.data['id']}/"
        payload = {"agent_id": self.agent.pk, "content": "Are admissions open?"}
        import uuid
        headers = {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}
        response = self.client.post(url + "messages/", payload, format="json", **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assistant_message"]["sources"][0]["url"], self.source.source_url)
        replay = self.client.post(url + "messages/", payload, format="json", **headers)
        self.assertEqual(replay.data, response.data)
        history = self.client.get(url, {"agent_id": self.agent.pk})
        self.assertEqual(history.data["predefined_questions"], self.agent.predefined_questions)
        self.assertEqual(history.data["messages"][-1]["sources"], response.data["sources"])
        self.assertEqual(generate.call_count, 1)

    def test_sources_are_deduplicated_and_unsafe_urls_omitted(self):
        self.assertEqual(len(build_sources([self.chunk, self.chunk])), 1)
        self.source.source_url = "javascript:alert(1)"
        self.assertEqual(build_sources([self.chunk])[0]["url"], "")
        self.source.source_url = ""
        self.assertEqual(build_sources([self.chunk])[0]["url"], "")

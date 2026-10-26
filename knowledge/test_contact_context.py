from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from agents.models import Agent
from knowledge.chunking import split_text
from knowledge.context import build_knowledge_context
from knowledge.models import KnowledgeSource, KnowledgeChunk


class PhoneBoundaryTests(SimpleTestCase):
    def test_phone_numbers_are_not_split_at_chunk_edges(self):
        for number in ("9585228600", "+91 95852 28600", "0431-2258501 / 02 / 03"):
            with self.subTest(number=number):
                prefix = "x" * (499 - len(" College Mobile: ")) + " College Mobile: "
                chunks = split_text(prefix + number + " More information " * 40)
                self.assertIn("College Mobile: " + number, chunks[0])


class ContactContextTests(TestCase):
    def test_legacy_truncated_number_is_completed_from_same_source(self):
        user = get_user_model().objects.create(username="contact-test")
        agent = Agent.objects.create(owner=user, name="College")
        source = KnowledgeSource.objects.create(agent=agent, title="Contact", status="ready", source_type="text")
        first = KnowledgeChunk.objects.create(source=source, chunk_index=0, content="College Mobile : 9")
        KnowledgeChunk.objects.create(source=source, chunk_index=1, content="College Mobile : 9585228600 Principal Office")
        other = KnowledgeSource.objects.create(agent=agent, title="Other", status="ready", source_type="text")
        KnowledgeChunk.objects.create(source=other, chunk_index=1, content="Unrelated private content")
        context = build_knowledge_context([first])
        self.assertIn("College Mobile : 9585228600", context)
        self.assertNotIn("Unrelated private content", context)
        self.assertEqual(context.count("College Mobile"), 1)

    def test_empty_context(self):
        self.assertEqual(build_knowledge_context([]), "")

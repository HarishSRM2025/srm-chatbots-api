from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
# from django.test import APITestCase, SimpleTestCase, TestCase

from django.core.files.base import ContentFile

# from rest_framework import status

from agents.models import Agent
from knowledge.chunking import create_source_chunks, split_text
from knowledge.models import KnowledgeChunk, KnowledgeSource
from knowledge.serializers import KnowledgeSourceSerializer

from django.test import SimpleTestCase, TestCase
from rest_framework import status
from rest_framework.test import APITestCase

class SplitTextTests(SimpleTestCase):
    def test_empty_text_returns_no_chunks(self):
        self.assertEqual(split_text(""), [])

    def test_whitespace_only_text_returns_no_chunks(self):
        self.assertEqual(split_text("   \n\t  "), [])

    def test_short_text_returns_one_chunk(self):
        text = "SRM Nursing College provides admission information."
        self.assertEqual(split_text(text), [text])

    def test_long_text_is_split_into_chunks(self):
        text = "A" * 1200
        chunks = split_text(text)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(
            [len(chunk) for chunk in chunks],
            [500, 500, 400],
        )

    def test_chunks_have_expected_overlap(self):
        chunks = split_text("A" * 1200)

        self.assertEqual(chunks[0][-100:], chunks[1][:100])
        self.assertEqual(chunks[1][-100:], chunks[2][:100])

    def test_invalid_chunk_size_raises_error(self):
        with self.assertRaises(ValueError):
            split_text("Some text", chunk_size=0)

    def test_invalid_overlap_raises_error(self):
        with self.assertRaises(ValueError):
            split_text("Some text", chunk_size=100, overlap=100)


class CreateSourceChunksTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="knowledge_test_user",
            password="test-password-not-for-production",
        )

        self.agent = Agent.objects.create(
            owner=self.user,
            name="Test Nursing Agent",
            system_prompt="Answer questions using nursing college knowledge.",
        )

        self.source = KnowledgeSource.objects.create(
            agent=self.agent,
            title="Nursing Admissions FAQ",
            source_type=KnowledgeSource.SourceType.TEXT,
            text_content=(
                "SRM Nursing College provides information about "
                "courses, admissions, eligibility, and fees."
            ),
        )


    def test_processing_uploaded_text_file_creates_chunks(self):
        self.source.source_type = KnowledgeSource.SourceType.FILE
        self.source.text_content = ""
        self.source.file.save(
            "nursing-faq.txt",
            ContentFile(
                b"SRM Nursing College provides admission information."
            ),
            save=True,
        )

        try:
            chunk_count = create_source_chunks(self.source)

            self.source.refresh_from_db()

            self.assertEqual(chunk_count, 1)
            self.assertEqual(
                self.source.status,
                KnowledgeSource.Status.READY,
            )
            self.assertEqual(
                self.source.chunks.count(),
                1,
            )
            self.assertIn(
                "SRM Nursing College",
                self.source.chunks.first().content,
            )
        finally:
            self.source.file.delete(save=False)


    def test_processing_saves_chunks_and_marks_source_ready(self):
        chunk_count = create_source_chunks(self.source)

        self.source.refresh_from_db()

        self.assertEqual(chunk_count, 1)
        self.assertEqual(
            KnowledgeChunk.objects.filter(source=self.source).count(),
            1,
        )
        self.assertEqual(
            self.source.status,
            KnowledgeSource.Status.READY,
        )
        self.assertIn(
            "SRM Nursing College",
            self.source.chunks.first().content,
        )

    def test_reprocessing_replaces_existing_chunks(self):
        create_source_chunks(self.source)

        self.source.text_content = (
            "UPDATED: Nursing admissions include eligibility "
            "and application procedures."
        )
        self.source.save(update_fields=["text_content"])

        create_source_chunks(self.source)

        chunks = KnowledgeChunk.objects.filter(source=self.source)

        self.assertEqual(chunks.count(), 1)
        self.assertIn("UPDATED:", chunks.first().content)
        self.assertNotIn(
            "SRM Nursing College",
            chunks.first().content,
        )

    def test_failed_reprocessing_preserves_existing_chunks(self):
        # First, create valid chunks.
        create_source_chunks(self.source)

        original_chunks = list(
            self.source.chunks.order_by("chunk_index").values_list(
                "content", flat=True
            )
        )

        self.assertGreater(len(original_chunks), 0)

        # Change the source to content that cannot be processed.
        self.source.text_content = "   "
        self.source.save(update_fields=["text_content"])

        # Reprocessing should fail without deleting existing chunks.
        with self.assertRaises(ValueError):
            create_source_chunks(self.source)

        preserved_chunks = list(
            self.source.chunks.order_by("chunk_index").values_list(
                "content", flat=True
            )
        )

        self.assertEqual(preserved_chunks, original_chunks)

    def test_empty_text_is_rejected(self):
        self.source.text_content = "   "
        self.source.save(update_fields=["text_content"])

        with self.assertRaises(ValueError):
            create_source_chunks(self.source)

        self.assertEqual(
            KnowledgeChunk.objects.filter(source=self.source).count(),
            0,
        )


class KnowledgeSourcePermissionTests(APITestCase):
    def setUp(self):
        User = get_user_model()

        self.user1 = User.objects.create_user(
            username="knowledge_user1",
            email="user1@example.com",
            password="TestPass123!safe",
        )
        self.user2 = User.objects.create_user(
            username="knowledge_user2",
            email="user2@example.com",
            password="TestPass123!safe",
        )

        self.agent1 = Agent.objects.create(
            owner=self.user1,
            name="Nursing College",
            system_prompt="Help with nursing college questions.",
        )
        self.agent2 = Agent.objects.create(
            owner=self.user2,
            name="Engineering College",
            system_prompt="Help with engineering college questions.",
        )

        self.source1 = KnowledgeSource.objects.create(
            agent=self.agent1,
            title="Nursing FAQ",
            source_type=KnowledgeSource.SourceType.TEXT,
            text_content="Nursing admissions information.",
        )
        self.source2 = KnowledgeSource.objects.create(
            agent=self.agent2,
            title="Engineering FAQ",
            source_type=KnowledgeSource.SourceType.TEXT,
            text_content="Engineering admissions information.",
        )

        self.list_url = "/api/knowledge/"
        self.source2_url = f"/api/knowledge/{self.source2.id}/"

    def test_unauthenticated_user_cannot_list_sources(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_user_only_sees_own_sources(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        returned_ids = [item["id"] for item in response.data]
        self.assertIn(self.source1.id, returned_ids)
        self.assertNotIn(self.source2.id, returned_ids)

    def test_user_cannot_retrieve_another_users_source(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.get(self.source2_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_update_another_users_source(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.patch(
            self.source2_url,
            {"title": "Unauthorized change"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_delete_another_users_source(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.delete(self.source2_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(
            KnowledgeSource.objects.filter(pk=self.source2.id).exists()
        )

    def test_user_cannot_process_another_users_source(self):
        self.client.force_authenticate(user=self.user2)

        response = self.client.post(
            f"/api/knowledge/{self.source1.id}/process/"
        )

        self.assertEqual(response.status_code, 404)


class KnowledgeSourceFileValidationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="file_validation_user",
            password="TestPass123!safe",
        )
        self.agent = Agent.objects.create(
            owner=self.user,
            name="File Validation Agent",
            system_prompt="Answer questions using uploaded knowledge.",
        )

    def get_serializer(self, uploaded_file):
        return KnowledgeSourceSerializer(
            data={
                "agent": self.agent.id,
                "title": "Test Upload",
                "source_type": "file",
                "file": uploaded_file,
            }
        )

    def test_accepts_valid_pdf_extension(self):
        uploaded_file = SimpleUploadedFile(
            "college.pdf",
            b"%PDF-1.4 test content",
            content_type="application/pdf",
        )
        serializer = self.get_serializer(uploaded_file)

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rejects_unsupported_extension(self):
        uploaded_file = SimpleUploadedFile(
            "program.exe",
            b"test content",
            content_type="application/octet-stream",
        )
        serializer = self.get_serializer(uploaded_file)

        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)

    def test_rejects_empty_file(self):
        uploaded_file = SimpleUploadedFile(
            "empty.txt",
            b"",
            content_type="text/plain",
        )
        serializer = self.get_serializer(uploaded_file)

        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)

    def test_rejects_file_over_10_mb(self):
        uploaded_file = SimpleUploadedFile(
            "large.pdf",
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="application/pdf",
        )
        serializer = self.get_serializer(uploaded_file)

        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)




class KnowledgeSourceProcessingAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()

        self.user1 = User.objects.create_user(
            username="processing_user1",
            password="TestPass123!safe",
        )
        self.user2 = User.objects.create_user(
            username="processing_user2",
            password="TestPass123!safe",
        )

        self.agent1 = Agent.objects.create(
            owner=self.user1,
            name="Processing Nursing Agent",
            system_prompt="Answer nursing college questions.",
        )
        self.agent2 = Agent.objects.create(
            owner=self.user2,
            name="Processing Engineering Agent",
            system_prompt="Answer engineering college questions.",
        )

        self.source = KnowledgeSource.objects.create(
            agent=self.agent1,
            title="Nursing FAQ Upload",
            source_type=KnowledgeSource.SourceType.FILE,
        )

        self.source.file.save(
            "processing-nursing-faq.txt",
            ContentFile(
                b"Admissions: Nursing applicants must meet college eligibility requirements."
            ),
            save=True,
        )

        self.process_url = (
            f"/api/knowledge/{self.source.id}/process/"
        )

    def tearDown(self):
        # Remove uploaded test files from local media storage.
        for source in KnowledgeSource.objects.filter(
            title="Nursing FAQ Upload"
        ):
            if source.file:
                source.file.delete(save=False)

    def test_authenticated_user_can_process_own_file(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(self.process_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ready")
        self.assertEqual(response.data["chunks_created"], 1)

        self.source.refresh_from_db()
        self.assertEqual(
            self.source.status,
            KnowledgeSource.Status.READY,
        )
        self.assertEqual(self.source.chunks.count(), 1)
        self.assertIn(
            "Admissions",
            self.source.chunks.first().content,
        )

    def test_user_cannot_process_another_users_file(self):
        self.client.force_authenticate(user=self.user2)

        response = self.client.post(self.process_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.source.chunks.count(), 0)

    def test_unauthenticated_user_cannot_process_file(self):
        response = self.client.post(self.process_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


    @patch("knowledge.chunking.extract_text_from_url")
    def test_url_source_can_be_processed(self, mock_extract):
        from django.core.files.base import ContentFile

        mock_extract.return_value = (
            "Nursing admissions are open in June."
        )

        source = KnowledgeSource.objects.create(
            agent=self.agent1,
            title="Website Nursing FAQ",
            source_type=KnowledgeSource.SourceType.URL,
            source_url="https://example.com/nursing",
        )
        self.client.force_authenticate(user=self.user1)
        response = self.client.post(
            f"/api/knowledge/{source.id}/process/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )
        self.assertEqual(response.data["status"], "ready")
        self.assertGreaterEqual(response.data["chunks_created"], 1)
        chunks = KnowledgeChunk.objects.filter(
            source=source
        ).order_by("chunk_index")

        self.assertGreater(chunks.count(), 0)
        self.assertIn(
            "Nursing admissions are open in June.",
            chunks.first().content,
        )
        mock_extract.assert_called_once_with(
            "https://example.com/nursing"
        )


    @patch("knowledge.chunking.extract_text_from_url")
    def test_url_processing_failure_marks_source_failed(
        self, mock_extract
    ):
        mock_extract.side_effect = ValueError(
            "The website could not be fetched."
        )

        source = KnowledgeSource.objects.create(
            agent=self.agent1,
            title="Unreachable Website",
            source_type=KnowledgeSource.SourceType.URL,
            source_url="https://example.com/unreachable",
        )

        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            f"/api/knowledge/{source.id}/process/"
        )

        source.refresh_from_db()

        self.assertEqual(
            response.status_code,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        self.assertEqual(
            source.status,
            KnowledgeSource.Status.FAILED,
        )
        self.assertTrue(source.error_message)

    def test_creating_text_source_processes_it_automatically(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            "/api/knowledge/",
            {
                "agent": self.agent1.id,
                "title": "Automatic Text Test",
                "source_type": KnowledgeSource.SourceType.TEXT,
                "text_content": (
                    "The nursing admissions office opens at 9 AM."
                ),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        source = KnowledgeSource.objects.get(id=response.data["id"])

        self.assertEqual(source.status, KnowledgeSource.Status.READY)
        self.assertEqual(source.error_message, "")
        self.assertGreater(source.chunks.count(), 0)
        self.assertIn(
            "nursing admissions",
            source.chunks.first().content.lower(),
        )

    @patch("knowledge.chunking.extract_text_from_url")
    def test_creating_url_source_processes_it_automatically(
        self, mock_extract
    ):
        mock_extract.return_value = (
            "The engineering admissions office opens at 10 AM."
        )
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            "/api/knowledge/",
            {
                "agent": self.agent1.id,
                "title": "Automatic URL Test",
                "source_type": KnowledgeSource.SourceType.URL,
                "source_url": "https://example.com/engineering",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        source = KnowledgeSource.objects.get(id=response.data["id"])

        self.assertEqual(source.status, KnowledgeSource.Status.READY)
        self.assertGreater(source.chunks.count(), 0)
        self.assertIn(
            "engineering admissions",
            source.chunks.first().content.lower(),
        )
        mock_extract.assert_called_once_with(
            "https://example.com/engineering"
        )

    @patch("knowledge.chunking.extract_text_from_url")
    def test_creating_url_source_processing_failure_returns_error(
        self, mock_extract
    ):
        mock_extract.side_effect = ValueError(
            "The website could not be fetched."
        )
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            "/api/knowledge/",
            {
                "agent": self.agent1.id,
                "title": "Failed Automatic URL Test",
                "source_type": KnowledgeSource.SourceType.URL,
                "source_url": "https://example.com/unreachable",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            response.data,
        )

        source = KnowledgeSource.objects.get(
            title="Failed Automatic URL Test",
            agent=self.agent1,
        )
        self.assertEqual(
            source.status,
            KnowledgeSource.Status.FAILED,
        )
        self.assertTrue(source.error_message)
        self.assertEqual(source.chunks.count(), 0)


    @patch("knowledge.chunking.extract_text_from_url")
    def test_failed_url_source_can_be_retried_successfully(
        self, mock_extract
    ):
        source = KnowledgeSource.objects.create(
            agent=self.agent1,
            title="Retry Website Test",
            source_type=KnowledgeSource.SourceType.URL,
            source_url="https://example.com/retry",
            status=KnowledgeSource.Status.FAILED,
            error_message="Previous processing failed.",
        )

        self.client.force_authenticate(user=self.user1)

        # First attempt fails.
        mock_extract.side_effect = ValueError(
            "Temporary website error."
        )
        first_response = self.client.post(
            f"/api/knowledge/{source.id}/process/"
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

        source.refresh_from_db()
        self.assertEqual(
            source.status,
            KnowledgeSource.Status.FAILED,
        )

        # Second attempt succeeds.
        mock_extract.side_effect = None
        mock_extract.return_value = (
            "The website is available again. "
            "Engineering admissions open in July."
        )

        retry_response = self.client.post(
            f"/api/knowledge/{source.id}/process/"
        )

        self.assertEqual(
            retry_response.status_code,
            status.HTTP_200_OK,
            retry_response.data,
        )

        source.refresh_from_db()
        self.assertEqual(
            source.status,
            KnowledgeSource.Status.READY,
        )
        self.assertEqual(source.error_message, "")
        self.assertGreater(source.chunks.count(), 0)
        self.assertIn(
            "Engineering admissions",
            source.chunks.first().content,
        )
        self.assertEqual(mock_extract.call_count, 2)


    # @patch("knowledge.views.create_source_chunks")
    def test_creating_file_source_processes_it_automatically(self):
        self.client.force_authenticate(user=self.user1)

        uploaded_file = SimpleUploadedFile(
            "admissions-test.txt",
            (
                b"Admissions office hours are 10 AM to 4 PM. "
                b"The admissions email is admissions-test@example.com."
            ),
            content_type="text/plain",
        )

        response = self.client.post(
            "/api/knowledge/",
            {
                "agent": self.agent1.id,
                "title": "Admissions Test Document",
                "source_type": KnowledgeSource.SourceType.FILE,
                "file": uploaded_file,
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        source = KnowledgeSource.objects.get(
            id=response.data["id"]
        )

        self.assertEqual(
            source.status,
            KnowledgeSource.Status.READY,
        )
        self.assertEqual(source.error_message, "")

        chunks = KnowledgeChunk.objects.filter(
            source=source
        )

        self.assertGreater(chunks.count(), 0)

        chunk_text = " ".join(
            chunks.values_list("content", flat=True)
        )

        self.assertIn("Admissions office hours", chunk_text)
        self.assertIn(
            "admissions-test@example.com",
            chunk_text,
        )

        # Remove the uploaded file created by this test.
        source.file.delete(save=False)


class KnowledgeSourceSerializerValidationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="serializer_validation_user",
            password="TestPass123!safe",
        )
        self.agent = Agent.objects.create(
            owner=self.user,
            name="Serializer Validation Agent",
            system_prompt="Answer questions using college knowledge.",
        )

    def get_serializer(self, source_type, **extra_data):
        data = {
            "agent": self.agent.id,
            "title": "Validation Test Source",
            "source_type": source_type,
            **extra_data,
        }
        return KnowledgeSourceSerializer(data=data)

    def test_accepts_valid_text_source(self):
        serializer = self.get_serializer(
            "text",
            text_content="College admission and eligibility information.",
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rejects_empty_text_source(self):
        serializer = self.get_serializer(
            "text",
            text_content="   ",
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("text_content", serializer.errors)

    def test_accepts_valid_http_url_source(self):
        serializer = self.get_serializer(
            "url",
            source_url="https://example.com/admissions",
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_accepts_valid_https_url_source(self):
        serializer = self.get_serializer(
            "url",
            source_url="http://example.com/admissions",
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rejects_missing_url(self):
        serializer = self.get_serializer(
            "url",
            source_url="",
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("source_url", serializer.errors)

    def test_rejects_unsupported_url_scheme(self):
        serializer = self.get_serializer(
            "url",
            source_url="ftp://example.com/admissions",
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("source_url", serializer.errors)

    def test_rejects_url_with_credentials(self):
        serializer = self.get_serializer(
            "url",
            source_url="https://user:password@example.com/admissions",
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("source_url", serializer.errors)

    def test_rejects_url_without_hostname(self):
        serializer = self.get_serializer(
            "url",
            source_url="https:///admissions",
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("source_url", serializer.errors)

    def test_rejects_missing_text_content(self):
        serializer = self.get_serializer(
            "text",
            text_content="",
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("text_content", serializer.errors)


from knowledge.retrieval import retrieve_relevant_chunks


class KnowledgeRetrievalTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user1 = User.objects.create_user(
            username="retrieval_user1",
            password="TestPass123!safe",
        )
        self.user2 = User.objects.create_user(
            username="retrieval_user2",
            password="TestPass123!safe",
        )

        self.agent1 = Agent.objects.create(
            owner=self.user1,
            name="Nursing College Agent",
            system_prompt="Answer nursing college questions.",
        )
        self.agent2 = Agent.objects.create(
            owner=self.user2,
            name="Engineering College Agent",
            system_prompt="Answer engineering college questions.",
        )

        self.source1 = KnowledgeSource.objects.create(
            agent=self.agent1,
            title="Nursing Admissions",
            source_type=KnowledgeSource.SourceType.TEXT,
            text_content="Nursing admission information.",
            status=KnowledgeSource.Status.READY,
        )
        self.source2 = KnowledgeSource.objects.create(
            agent=self.agent2,
            title="Engineering Admissions",
            source_type=KnowledgeSource.SourceType.TEXT,
            text_content="Engineering admission information.",
            status=KnowledgeSource.Status.READY,
        )

        self.nursing_chunk = KnowledgeChunk.objects.create(
            source=self.source1,
            content=(
                "Nursing applicants need biology and chemistry "
                "for admission eligibility."
            ),
            chunk_index=0,
        )
        self.engineering_chunk = KnowledgeChunk.objects.create(
            source=self.source2,
            content=(
                "Engineering applicants need mathematics and physics "
                "for admission eligibility."
            ),
            chunk_index=0,
        )

    def test_retrieves_relevant_chunk(self):
        results = retrieve_relevant_chunks(
            self.agent1.id,
            "nursing biology eligibility",
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, self.nursing_chunk.id)

    def test_never_returns_another_agents_knowledge(self):
        results = retrieve_relevant_chunks(
            self.agent1.id,
            "engineering mathematics physics admission eligibility",
        )

        result_ids = [chunk.id for chunk in results]

        self.assertNotIn(self.engineering_chunk.id, result_ids)

    def test_ignores_sources_that_are_not_ready(self):
        self.source1.status = KnowledgeSource.Status.PENDING
        self.source1.save(update_fields=["status"])

        results = retrieve_relevant_chunks(
            self.agent1.id,
            "nursing biology eligibility",
        )

        self.assertEqual(results, [])

    def test_empty_query_returns_no_results(self):
        self.assertEqual(
            retrieve_relevant_chunks(self.agent1.id, ""),
            [],
        )

    def test_whitespace_query_returns_no_results(self):
        self.assertEqual(
            retrieve_relevant_chunks(self.agent1.id, "   "),
            [],
        )

    def test_non_matching_query_returns_no_results(self):
        results = retrieve_relevant_chunks(
            self.agent1.id,
            "astronomy galaxies telescope",
        )

        self.assertEqual(results, [])

    def test_limit_restricts_number_of_results(self):
        KnowledgeChunk.objects.create(
            source=self.source1,
            content="Nursing biology admission requirements.",
            chunk_index=1,
        )
        KnowledgeChunk.objects.create(
            source=self.source1,
            content="Nursing biology admission application process.",
            chunk_index=2,
        )

        results = retrieve_relevant_chunks(
            self.agent1.id,
            "nursing biology admission",
            limit=1,
        )

        self.assertEqual(len(results), 1)

    def test_zero_limit_returns_no_results(self):
        results = retrieve_relevant_chunks(
            self.agent1.id,
            "nursing biology",
            limit=0,
        )

        self.assertEqual(results, [])

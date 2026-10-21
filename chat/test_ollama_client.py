
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from chat.ollama_client import OllamaError, generate_response


@override_settings(
    OLLAMA_BASE_URL="http://localhost:11434",
    OLLAMA_MODEL="qwen3:4b",
)
class OllamaClientTests(SimpleTestCase):

    @patch("chat.ollama_client.requests.post")
    def test_generate_response_success(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": "Hello from Ollama"
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = generate_response("Say hello")

        self.assertEqual(result, "Hello from Ollama")

        request_body = mock_post.call_args.kwargs["json"]
        self.assertEqual(request_body["model"], "qwen3:4b")
        self.assertEqual(request_body["stream"], False)
        self.assertEqual(request_body["think"], False)

    @patch("chat.ollama_client.requests.post")
    def test_connection_error(self, mock_post):
        mock_post.side_effect = requests.ConnectionError(
            "Connection refused"
        )

        with self.assertRaises(OllamaError):
            generate_response("Say hello")

    @patch("chat.ollama_client.requests.post")
    def test_empty_response(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"response": ""}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with self.assertRaises(OllamaError):
            generate_response("Say hello")

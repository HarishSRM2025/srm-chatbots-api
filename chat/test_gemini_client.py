from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from chat.gemini_client import GeminiError, generate_response


@override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-2.5-flash-lite")
class GeminiClientTests(SimpleTestCase):
    @patch("chat.gemini_client.requests.post")
    def test_success_and_request_authentication(self, post):
        post.return_value = Mock()
        post.return_value.json.return_value = {"candidates": [{
            "finishReason": "STOP",
            "content": {"parts": [
                {"text": "private reasoning", "thought": True},
                {"text": "Hello "}, {"text": "world"},
            ]},
        }]}
        self.assertEqual(generate_response("Hi", timeout=15), "Hello world")
        post.assert_called_once_with(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash-lite:generateContent",
            headers={"x-goog-api-key": "test-key"},
            json={"contents": [{"role": "user", "parts": [{"text": "Hi"}]}]},
            timeout=15,
        )

    @patch("chat.gemini_client.requests.post")
    def test_missing_key_or_project_id_does_not_make_request(self, post):
        for key in ("", "  ", "gen-lang-client-0875340898"):
            with self.subTest(key=key), override_settings(GEMINI_API_KEY=key):
                with self.assertRaises(GeminiError):
                    generate_response("Hi")
        post.assert_not_called()

    @patch("chat.gemini_client.requests.post")
    def test_network_and_http_errors(self, post):
        for error in (requests.Timeout(), requests.ConnectionError(),
                      requests.HTTPError("401"), requests.HTTPError("429"),
                      requests.HTTPError("503")):
            with self.subTest(error=error):
                post.return_value.raise_for_status.side_effect = error
                with self.assertRaises(GeminiError):
                    generate_response("Hi")

    @patch("chat.gemini_client.requests.post")
    def test_invalid_json(self, post):
        post.return_value.json.side_effect = ValueError("Invalid JSON")
        with self.assertRaises(GeminiError):
            generate_response("Hi")

    @patch("chat.gemini_client.requests.post")
    def test_empty_malformed_and_blocked_responses(self, post):
        for data in (None, [], {}, {"candidates": []},
                     {"promptFeedback": {"blockReason": "SAFETY"}},
                     {"candidates": [{"finishReason": "SAFETY"}]},
                     {"candidates": [{"finishReason": "STOP", "content": {"parts": []}}]},
                     {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": 42}]}}]}):
            with self.subTest(data=data):
                post.return_value.json.return_value = data
                with self.assertRaises(GeminiError):
                    generate_response("Hi")

    @patch("chat.gemini_client.requests.post")
    def test_model_override_and_legacy_fallback(self, post):
        post.return_value.json.return_value = {"candidates": [{
            "finishReason": "STOP", "content": {"parts": [{"text": "OK"}]},
        }]}
        for model, expected in (("models/gemini-2.5-flash", "gemini-2.5-flash"),
                                ("qwen3:4b", "gemini-2.5-flash-lite")):
            with self.subTest(model=model):
                generate_response("Hi", model=model)
                self.assertTrue(post.call_args.args[0].endswith(f"/{expected}:generateContent"))

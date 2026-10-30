import json
from unittest.mock import patch

import httpx
from django.test import SimpleTestCase, override_settings

from apps.customer_portal import chatbot_groq, chatbot_service
from apps.customer_portal.chatbot_contract import ChatUnavailable


@override_settings(CHATBOT_PROVIDER="groq", GROQ_API_KEY="groq-test-placeholder", GROQ_MODEL="qwen/qwen3.8-27b")
class GroqProviderTests(SimpleTestCase):
    def setUp(self):
        patcher = patch("apps.customer_portal.chatbot_groq.httpx.Client")
        self.constructor = patcher.start()
        self.addCleanup(patcher.stop)
        self.post = self.constructor.return_value.__enter__.return_value.post
        self.response({"answer": "Xin chào", "dish_ids": [1]})

    def response(self, value):
        self.post.return_value = httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]})

    def test_remote_api_has_fixed_endpoint_no_redirects_no_tools_and_strict_json(self):
        result = chatbot_service.generate_reply({"menu": []}, [], "Hello")
        self.assertEqual(result["answer"], "Xin chào")
        self.post.assert_called_once()
        self.assertEqual(self.post.call_args.args[0], "https://api.groq.com/openai/v1/chat/completions")
        self.assertFalse(self.constructor.call_args.kwargs["follow_redirects"])
        body = self.post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "qwen/qwen3.8-27b")
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertNotIn("tools", body)
        self.assertNotIn("groq-test-placeholder", json.dumps(body))

    def test_http_errors_are_sanitized_without_fallback(self):
        with patch("apps.customer_portal.chatbot_service.chatbot_gemini.generate_reply") as other:
            for status in (400, 401, 402, 403, 404, 429, 500, 302):
                self.post.return_value = httpx.Response(status, text="sensitive-provider-error")
                with self.subTest(status=status), self.assertLogs("apps.customer_portal.chatbot_groq", level="WARNING") as captured:
                    with self.assertRaises(ChatUnavailable) as raised:
                        chatbot_service.generate_reply({}, [], "Hello")
                self.assertNotIn("sensitive-provider-error", raised.exception.message)
                self.assertNotIn("sensitive-provider-error", " ".join(captured.output))
                self.assertEqual(raised.exception.status, 429 if status == 429 else 503)
            other.assert_not_called()

    def test_invalid_empty_truncated_and_secret_responses_are_rejected(self):
        examples = ({"answer": "", "dish_ids": []}, {"answer": "groq-test-placeholder", "dish_ids": []},
                    {"answer": "Hello", "dish_ids": [True]}, {"answer": "Hello", "dish_ids": [], "url": "https://invalid.example"})
        for value in examples:
            self.response(value)
            with self.assertLogs("apps.customer_portal.chatbot_groq", level="WARNING"), self.assertRaises(ChatUnavailable):
                chatbot_groq.generate_reply({}, [], "Hello")
        self.post.return_value = httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]})
        with self.assertLogs("apps.customer_portal.chatbot_groq", level="WARNING"), self.assertRaises(ChatUnavailable):
            chatbot_groq.generate_reply({}, [], "Hello")

    def test_network_timeout_is_safe(self):
        self.post.side_effect = httpx.ReadTimeout("sensitive-provider-error")
        with self.assertLogs("apps.customer_portal.chatbot_groq", level="WARNING") as captured, self.assertRaises(ChatUnavailable):
            chatbot_service.generate_reply({}, [], "Hello")
        self.assertNotIn("sensitive-provider-error", " ".join(captured.output))

    @override_settings(GROQ_API_KEY="")
    def test_missing_groq_key_does_not_try_gemini(self):
        self.assertFalse(chatbot_service.configured())
        with patch("apps.customer_portal.chatbot_service.chatbot_gemini.generate_reply") as other:
            with self.assertRaises(ChatUnavailable): chatbot_service.generate_reply({}, [], "Hello")
        self.constructor.assert_not_called()
        other.assert_not_called()

    @override_settings(GROQ_MODEL="unverified-model")
    def test_unknown_model_does_not_call_provider(self):
        self.assertFalse(chatbot_service.configured())
        with self.assertRaises(ChatUnavailable): chatbot_service.generate_reply({}, [], "Hello")
        self.constructor.assert_not_called()

    def test_large_context_is_rejected_before_network(self):
        with self.assertRaises(ChatUnavailable):
            chatbot_service.generate_reply({"menu": ["x" * 15000]}, [], "Hello")
        self.constructor.assert_not_called()

    @override_settings(CHATBOT_PROVIDER="gemini", GEMINI_API_KEY="gemini-test-placeholder", GEMINI_MODEL="gemini-3.1-flash-lite")
    def test_explicit_gemini_choice_keeps_working_without_groq_request(self):
        with patch("apps.customer_portal.chatbot_service.chatbot_gemini.generate_reply", return_value={"answer": "Hello", "dish_ids": []}) as gemini:
            self.assertTrue(chatbot_service.configured())
            self.assertEqual(chatbot_service.provider_name(), "Gemini")
            self.assertEqual(chatbot_service.generate_reply({}, [], "Hello")["answer"], "Hello")
            gemini.assert_called_once()
        self.constructor.assert_not_called()

    def test_public_privacy_label_only_exposes_provider_name(self):
        from apps.customer_portal.chatbot_data import public_restaurant
        context = public_restaurant(None)
        self.assertEqual(context["chat_provider_name"], "Groq")
        self.assertNotIn("groq-test-placeholder", json.dumps(context))

    def test_unknown_provider_never_calls_a_backend(self):
        with override_settings(CHATBOT_PROVIDER="unknown"):
            self.assertFalse(chatbot_service.configured())
            with self.assertRaises(ChatUnavailable): chatbot_service.generate_reply({}, [], "Hello")
        self.constructor.assert_not_called()

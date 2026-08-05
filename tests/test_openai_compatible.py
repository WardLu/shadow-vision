import os
import unittest
from unittest.mock import Mock, patch

from vision_mcp.backends import OpenAICompatibleBackend
from vision_mcp.config import Config


class OpenAICompatibleConfigTests(unittest.TestCase):
    def test_new_openai_names_take_precedence_over_legacy_names(self) -> None:
        env = {
            "OPENAI_API_BASE": "https://new.example/v1",
            "VISION_API_BASE": "https://legacy.example/v1",
            "OPENAI_API_KEY": "new-key",
            "VISION_API_KEY": "legacy-key",
            "OPENAI_MAX_TOKENS": "2048",
            "VISION_MAX_TOKENS": "1024",
            "OPENAI_MAX_TOKENS_FIELD": "max_completion_tokens",
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config()

        self.assertEqual(config.api_base, "https://new.example/v1")
        self.assertEqual(config.api_key, "new-key")
        self.assertEqual(config.openai_max_tokens, 2048)
        self.assertEqual(config.openai_max_tokens_field, "max_completion_tokens")

    def test_legacy_names_remain_supported(self) -> None:
        env = {
            "VISION_API_BASE": "https://legacy.example/v1",
            "VISION_API_KEY": "legacy-key",
            "VISION_MAX_TOKENS": "1024",
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config()

        self.assertEqual(config.api_base, "https://legacy.example/v1")
        self.assertEqual(config.api_key, "legacy-key")
        self.assertEqual(config.openai_max_tokens, 1024)
        self.assertEqual(config.openai_max_tokens_field, "max_tokens")

    def test_openai_max_tokens_is_optional(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config()

        self.assertIsNone(config.openai_max_tokens)


class OpenAICompatiblePayloadTests(unittest.TestCase):
    def test_max_tokens_field_is_selected_explicitly(self) -> None:
        config = Config(openai_max_tokens=512, openai_max_tokens_field="max_completion_tokens")
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with patch("vision_mcp.backends.httpx.post", return_value=response) as post:
            result = OpenAICompatibleBackend(config).analyze("prompt", [(b"image", "image/png")], "vision-model")

        self.assertEqual(result, "ok")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["max_completion_tokens"], 512)
        self.assertNotIn("max_tokens", payload)

    def test_token_limit_is_omitted_when_unconfigured(self) -> None:
        config = Config(openai_max_tokens=None)
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with patch("vision_mcp.backends.httpx.post", return_value=response) as post:
            OpenAICompatibleBackend(config).analyze("prompt", [(b"image", "image/png")], "vision-model")

        payload = post.call_args.kwargs["json"]
        self.assertNotIn("max_tokens", payload)
        self.assertNotIn("max_completion_tokens", payload)


if __name__ == "__main__":
    unittest.main()

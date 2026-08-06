"""Multi-image payload structure tests (P0 analyze signature / F3 visitor)."""
import base64
import os
from unittest.mock import patch

import httpx
import pytest

from vision_mcp.backends import (
    AnthropicBackend,
    GeminiBackend,
    OllamaBackend,
    OpenAICompatibleBackend,
)
from vision_mcp.config import Config

IMAGES = [(b"\x89PNG", "image/png"), (b"\xff\xd8", "image/jpeg")]


def _response() -> httpx.Response:
    return httpx.Response(
        200,
        content=b"{}",
        request=httpx.Request("POST", "http://example/v1"),
    )


def _patch_post():
    return patch("vision_mcp.backends.httpx.post", return_value=_response())


def test_openai_multi_image_payload() -> None:
    config = Config(openai_max_tokens=None)
    with _patch_post() as post:
        OpenAICompatibleBackend(config).analyze("prompt", IMAGES, "m")
    content = post.call_args.kwargs["json"]["messages"][0]["content"]
    urls = [c["image_url"]["url"] for c in content if c["type"] == "image_url"]
    assert len(urls) == 2
    assert urls[0] == f"data:image/png;base64,{base64.b64encode(IMAGES[0][0]).decode()}"
    assert urls[1] == f"data:image/jpeg;base64,{base64.b64encode(IMAGES[1][0]).decode()}"


def test_ollama_multi_image_payload() -> None:
    config = Config()
    with _patch_post() as post:
        OllamaBackend(config).analyze("prompt", IMAGES, "m")
    payload = post.call_args.kwargs["json"]
    images = payload["messages"][0]["images"]
    assert images == [base64.b64encode(d).decode() for d, _ in IMAGES]


def test_ollama_no_think_appended_by_default() -> None:
    config = Config()
    with _patch_post() as post:
        OllamaBackend(config).analyze("prompt", IMAGES, "m")
    content = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert content == "prompt\n/no_think"


def test_ollama_no_think_disabled() -> None:
    config = Config(ollama_no_think=False)
    with _patch_post() as post:
        OllamaBackend(config).analyze("prompt", IMAGES, "m")
    content = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert content == "prompt"


def test_anthropic_multi_image_payload() -> None:
    config = Config(anthropic_api_key="k", anthropic_max_tokens=1024)
    with _patch_post() as post:
        AnthropicBackend(config).analyze("prompt", IMAGES, "m")
    content = post.call_args.kwargs["json"]["messages"][0]["content"]
    image_blocks = [c for c in content if c["type"] == "image"]
    assert len(image_blocks) == 2
    assert image_blocks[1]["source"]["media_type"] == "image/jpeg"
    assert image_blocks[1]["source"]["data"] == base64.b64encode(IMAGES[1][0]).decode()
    assert content[-1] == {"type": "text", "text": "prompt"}


def test_gemini_multi_image_payload() -> None:
    config = Config(gemini_api_key="k")
    with _patch_post() as post:
        GeminiBackend(config).analyze("prompt", IMAGES, "m")
    payload = post.call_args.kwargs["json"]
    parts = payload["input"]
    images = [p for p in parts if p["type"] == "image"]
    assert len(images) == 2
    assert images[1]["mime_type"] == "image/jpeg"
    assert images[1]["data"] == base64.b64encode(IMAGES[1][0]).decode()


def test_single_image_backward_compatible_payload() -> None:
    config = Config(openai_max_tokens=None)
    with _patch_post() as post:
        OpenAICompatibleBackend(config).analyze("prompt", [(b"x", "image/png")], "m")
    content = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert len([c for c in content if c["type"] == "image_url"]) == 1

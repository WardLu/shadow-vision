"""Vision backend abstraction.

The MCP layer only talks to `VisionBackend`, so the backend can be swapped
without touching the server code. Four built-in backends are provided:

- `ollama`: native Ollama chat API (default)
- `openai_compatible`: any OpenAI-compatible vision endpoint (e.g. LM Studio,
  vLLM, or cloud providers)
- `anthropic`: Anthropic Messages API (Claude)
- `gemini`: Google Gemini API
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from .config import Config

# MIME types for common image extensions.
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


class VisionBackend(ABC):
    """Minimal interface for a vision backend."""

    @abstractmethod
    def analyze(self, prompt: str, image_data: str, mime: str, model: str) -> str:
        """Send a prompt plus an image to the backend and return the text answer."""


class OllamaBackend(VisionBackend):
    """Native Ollama chat API backend."""

    def __init__(self, config: Config) -> None:
        self.url = config.ollama_url
        self.timeout = config.timeout

    def analyze(self, prompt: str, image_data: str, mime: str, model: str) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": [image_data]}],
            "stream": False,
        }
        resp = httpx.post(self.url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {})
        if message.get("content"):
            return message["content"]
        if message.get("thinking"):
            return message["thinking"]
        return "no response"


class OpenAICompatibleBackend(VisionBackend):
    """OpenAI-compatible chat completions backend with image_url support."""

    def __init__(self, config: Config) -> None:
        self.base = config.api_base.rstrip("/")
        self.api_key = config.api_key
        self.max_tokens = config.openai_max_tokens
        self.max_tokens_field = config.openai_max_tokens_field
        self.timeout = config.timeout

    def analyze(self, prompt: str, image_data: str, mime: str, model: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_data}"}},
                    ],
                }
            ],
            "stream": False,
        }
        if self.max_tokens is not None:
            if self.max_tokens_field not in {"max_tokens", "max_completion_tokens"}:
                raise ValueError(
                    "OPENAI_MAX_TOKENS_FIELD must be max_tokens or max_completion_tokens"
                )
            payload[self.max_tokens_field] = self.max_tokens
        resp = httpx.post(f"{self.base}/chat/completions", headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if choices and choices[0].get("message", {}).get("content"):
            return choices[0]["message"]["content"]
        return "no response"


def create_backend(config: Config) -> VisionBackend:
    """Factory that returns the configured backend."""
    if config.backend == "ollama":
        return OllamaBackend(config)
    if config.backend in ("openai", "openai_compatible"):
        return OpenAICompatibleBackend(config)
    raise ValueError(f"unknown vision backend: {config.backend}")


def _read_image(image_path: str, image_base64: str | None, mime_type: str | None) -> tuple[str, str]:
    """Read an image from a local path or base64 data, returning (base64, mime)."""
    if image_base64:
        return image_base64, mime_type or "image/png"
    path = Path(image_path).expanduser()
    if not path.exists():
        raise ValueError(f"image not found: {path}")
    data = base64.b64encode(path.read_bytes()).decode()
    mime = MIME_TYPES.get(path.suffix.lower(), "image/png")
    return data, mime


class AnthropicBackend(VisionBackend):
    """Anthropic Messages API backend (Claude)."""

    def __init__(self, config: Config) -> None:
        self.api_key = config.anthropic_api_key
        self.base = config.anthropic_base_url.rstrip("/")
        self.version = config.anthropic_version
        self.max_tokens = config.anthropic_max_tokens
        self.timeout = config.timeout

    def analyze(self, prompt: str, image_data: str, mime: str, model: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.version,
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": self.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        resp = httpx.post(f"{self.base}/v1/messages", headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        texts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
        return "".join(texts) or "no response"


class GeminiBackend(VisionBackend):
    """Google Gemini API backend (interactions / generateContent)."""

    def __init__(self, config: Config) -> None:
        self.api_key = config.gemini_api_key
        self.base = config.gemini_base_url.rstrip("/")
        self.max_tokens = config.gemini_max_tokens
        self.timeout = config.timeout

    def analyze(self, prompt: str, image_data: str, mime: str, model: str) -> str:
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "input": [
                {"type": "text", "text": prompt},
                {"type": "image", "data": image_data, "mime_type": mime},
            ],
            "config": {"maxOutputTokens": self.max_tokens},
        }
        resp = httpx.post(f"{self.base}/v1beta/interactions", headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        # The interactions endpoint nests output under candidates[].content.
        candidates = data.get("candidates", [])
        for candidate in candidates:
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                if part.get("text"):
                    return part["text"]
        # Fallback: some responses expose outputText directly.
        if data.get("outputText"):
            return data["outputText"]
        return "no response"


def create_backend(config: Config) -> VisionBackend:
    """Factory that returns the configured backend."""
    if config.backend == "ollama":
        return OllamaBackend(config)
    if config.backend in ("openai", "openai_compatible"):
        return OpenAICompatibleBackend(config)
    if config.backend == "anthropic":
        return AnthropicBackend(config)
    if config.backend == "gemini":
        return GeminiBackend(config)
    raise ValueError(f"unknown vision backend: {config.backend}")

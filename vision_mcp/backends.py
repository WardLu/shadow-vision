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
import random
import time
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from .config import Config
from . import fetch
from . import imageproc

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

    def __init__(self, config: Config) -> None:
        self.config = config

    def _post(self, url: str, *, headers: dict, json: dict) -> httpx.Response:
        """POST with retry on transient failures and 5xx, plus fine-grained
        timeouts (R4). 4xx and non-retryable errors propagate immediately."""
        timeout = httpx.Timeout(
            connect=self.config.connect_timeout,
            read=self.config.read_timeout,
            write=10.0,
            pool=10.0,
        )
        last_error: Exception | None = None
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            try:
                resp = httpx.post(url, headers=headers, json=json, timeout=timeout)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise
                last_error = exc
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = exc
            if attempt < self.config.max_retries:
                delay = self.config.retry_base_delay * (2**attempt) + random.uniform(0, 0.5)
                time.sleep(delay)
        assert last_error is not None
        raise last_error

    @abstractmethod
    def analyze(self, prompt: str, images: list[tuple[bytes, str]], model: str) -> str:
        """Send a prompt plus one or more images to the backend and return the text answer.

        `images` is a list of (raw_bytes, mime) tuples. Base64 encoding is
        backend-specific and handled in each implementation.
        """


class OllamaBackend(VisionBackend):
    """Native Ollama chat API backend."""

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.url = config.ollama_url

    def analyze(self, prompt: str, images: list[tuple[bytes, str]], model: str) -> str:
        content = prompt
        # Qwen3 family defaults to thinking mode; `/no_think` disables it so
        # latency/tokens stay low for the MCP use case.
        if self.config.ollama_no_think:
            content = f"{prompt}\n/no_think"
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": content,
                "images": [_b64(data) for data, _ in images],
            }],
            "stream": False,
            "options": {"num_ctx": self.config.ollama_num_ctx},
        }
        resp = self._post(self.url, headers={}, json=payload)
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
        super().__init__(config)
        self.base = config.api_base.rstrip("/")
        self.api_key = config.api_key
        self.max_tokens = config.openai_max_tokens
        self.max_tokens_field = config.openai_max_tokens_field

    def analyze(self, prompt: str, images: list[tuple[bytes, str]], model: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        content: list[dict] = [{"type": "text", "text": prompt}]
        content.extend(
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{_b64(data)}"}}
            for data, mime in images
        )
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }
        if self.max_tokens is not None:
            if self.max_tokens_field not in {"max_tokens", "max_completion_tokens"}:
                raise ValueError(
                    "OPENAI_MAX_TOKENS_FIELD must be max_tokens or max_completion_tokens"
                )
            payload[self.max_tokens_field] = self.max_tokens
        resp = self._post(f"{self.base}/chat/completions", headers=headers, json=payload)
        data = resp.json()
        choices = data.get("choices", [])
        if choices and choices[0].get("message", {}).get("content"):
            return choices[0]["message"]["content"]
        return "no response"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


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


def _process_image(
    config: Config, raw: bytes, mime: str, *, tile: bool | None = None
) -> list[tuple[bytes, str, dict | None]]:
    """Tile then compress a single image. Returns [(bytes, mime, tile_meta_or_None)].
    Tile runs on the original layout first (so splitting stays faithful), then
    each block is independently compressed. `tile` overrides config.auto_tile."""
    if config.auto_tile if tile is None else tile:
        tiles = imageproc.tile_if_needed(
            raw, mime,
            tile_long_edge=config.tile_long_edge,
            overlap=config.tile_overlap,
            max_tiles=config.max_tiles,
        )
    else:
        tiles = [(raw, mime, None)]
    out: list[tuple[bytes, str, dict | None]] = []
    for tile_bytes, tile_mime, meta in tiles:
        if config.auto_compress:
            tile_bytes, tile_mime = imageproc.compress_if_needed(
                tile_bytes, tile_mime,
                max_long_edge=config.max_long_edge,
                max_pixels=config.max_pixels,
                quality=config.compress_quality,
            )
        out.append((tile_bytes, tile_mime, meta))
    return out


def _load_images(
    config: Config, args: dict, *, tile: bool | None = None
) -> list[tuple[bytes, str, dict | None]]:
    """Load, tile and compress images from tool-call args.

    Single-image entry via image_base64 / image_path. Remote image_url is
    handled by fetch in the F1 milestone. Returns [(bytes, mime, tile_meta)].
    """
    image_path = str(args.get("image_path", ""))
    image_base64 = args.get("image_base64")
    mime_type = args.get("mime_type")
    image_url = args.get("image_url")
    if not image_base64 and not image_path and image_url:
        if not config.allow_remote_url:
            raise ValueError("remote image URLs are disabled")
        raw, mime = fetch.fetch_image_from_url(image_url, config)
        return _process_image(config, raw, mime, tile=tile)
    data, mime = _read_image(image_path, image_base64, mime_type)
    return _process_image(config, base64.b64decode(data), mime, tile=tile)


class AnthropicBackend(VisionBackend):
    """Anthropic Messages API backend (Claude)."""

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.api_key = config.anthropic_api_key
        self.base = config.anthropic_base_url.rstrip("/")
        self.version = config.anthropic_version
        self.max_tokens = config.anthropic_max_tokens

    def analyze(self, prompt: str, images: list[tuple[bytes, str]], model: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.version,
            "Content-Type": "application/json",
        }
        content: list[dict] = [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": _b64(data)}}
            for data, mime in images
        ]
        content.append({"type": "text", "text": prompt})
        payload = {
            "model": model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        resp = self._post(f"{self.base}/v1/messages", headers=headers, json=payload)
        data = resp.json()
        texts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
        return "".join(texts) or "no response"


class GeminiBackend(VisionBackend):
    """Google Gemini API backend (interactions / generateContent)."""

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.api_key = config.gemini_api_key
        self.base = config.gemini_base_url.rstrip("/")
        self.max_tokens = config.gemini_max_tokens

    def analyze(self, prompt: str, images: list[tuple[bytes, str]], model: str) -> str:
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        input_parts: list[dict] = [{"type": "text", "text": prompt}]
        input_parts.extend(
            {"type": "image", "data": _b64(data), "mime_type": mime} for data, mime in images
        )
        payload = {
            "model": model,
            "input": input_parts,
            "config": {"maxOutputTokens": self.max_tokens},
        }
        resp = self._post(f"{self.base}/v1beta/interactions", headers=headers, json=payload)
        data = resp.json()
        candidates = data.get("candidates", [])
        for candidate in candidates:
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                if part.get("text"):
                    return part["text"]
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


def _load_images_batch(config: Config, args: dict) -> tuple[list[tuple[bytes, str]], list[str]]:
    """Load a batch of images from `args["images"]` (F3 vision_compare).

    Each image is compressed but never tiled (tiling + multi-image would blow up
    context). Returns (images, labels). Enforces VISION_MAX_BATCH_IMAGES."""
    items = args.get("images")
    if not isinstance(items, list) or not items:
        raise ValueError("images array is required")
    if len(items) > config.max_batch_images:
        raise ValueError(f"too many images: {len(items)} (max {config.max_batch_images})")
    images: list[tuple[bytes, str]] = []
    labels: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each image must be an object")
        image_path = str(item.get("image_path", ""))
        image_base64 = item.get("image_base64")
        mime_type = item.get("mime_type")
        image_url = item.get("image_url")
        if not image_base64 and not image_path and image_url:
            if not config.allow_remote_url:
                raise ValueError("remote image URLs are disabled")
            raw, mime = fetch.fetch_image_from_url(image_url, config)
        else:
            data, mime = _read_image(image_path, image_base64, mime_type)
            raw = base64.b64decode(data)
        processed = _process_image(config, raw, mime, tile=False)
        images.append((processed[0][0], processed[0][1]))
        labels.append(str(item.get("label", "")) if item.get("label") else "")
    return images, labels

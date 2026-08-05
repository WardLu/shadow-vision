"""Runtime configuration for the vision MCP server.

All values are read from environment variables with sensible defaults,
so the server can be configured without touching code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(primary: str, legacy: str, default: str | None = None) -> str | None:
    """Read the new variable name first, then fall back to the legacy name."""
    return os.getenv(primary) or os.getenv(legacy) or default


def _optional_int(primary: str, legacy: str) -> int | None:
    """Read an optional integer environment variable with a legacy fallback."""
    value = _env(primary, legacy)
    return int(value) if value else None


@dataclass(frozen=True)
class Config:
    backend: str = field(default_factory=lambda: os.getenv("VISION_BACKEND", "ollama"))
    model: str = field(default_factory=lambda: os.getenv("VISION_MODEL", "qwen3-vl:2b"))
    # Ollama
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat"))
    # OpenAI-compatible endpoint. OPENAI_* is preferred; VISION_* remains supported.
    api_base: str = field(
        default_factory=lambda: _env(
            "OPENAI_API_BASE", "VISION_API_BASE", "http://127.0.0.1:11434/v1"
        ) or "http://127.0.0.1:11434/v1"
    )
    api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY", "VISION_API_KEY", "") or "")
    openai_max_tokens: int | None = field(
        default_factory=lambda: _optional_int("OPENAI_MAX_TOKENS", "VISION_MAX_TOKENS")
    )
    openai_max_tokens_field: str = field(
        default_factory=lambda: _env(
            "OPENAI_MAX_TOKENS_FIELD", "VISION_MAX_TOKENS_FIELD", "max_tokens"
        ) or "max_tokens"
    )
    # Anthropic
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_base_url: str = field(default_factory=lambda: os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
    anthropic_version: str = field(default_factory=lambda: os.getenv("ANTHROPIC_VERSION", "2023-06-01"))
    anthropic_max_tokens: int = field(default_factory=lambda: int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024")))
    # Gemini
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_base_url: str = field(default_factory=lambda: os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"))
    gemini_max_tokens: int = field(default_factory=lambda: int(os.getenv("GEMINI_MAX_TOKENS", "1024")))
    timeout: float = field(default_factory=lambda: float(os.getenv("VISION_TIMEOUT", "180")))

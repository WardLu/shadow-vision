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
    ollama_num_ctx: int = field(default_factory=lambda: int(os.getenv("VISION_OLLAMA_NUM_CTX", "32768")))
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
    # Timeout (R4). VISION_TIMEOUT is kept as a legacy alias for the read timeout.
    timeout: float = field(default_factory=lambda: float(os.getenv("VISION_TIMEOUT", "180")))
    connect_timeout: float = field(
        default_factory=lambda: float(os.getenv("VISION_CONNECT_TIMEOUT", "10"))
    )
    read_timeout: float = field(
        default_factory=lambda: float(_env("VISION_READ_TIMEOUT", "VISION_TIMEOUT", "180") or "180")
    )
    # Retry (R4)
    max_retries: int = field(default_factory=lambda: int(os.getenv("VISION_MAX_RETRIES", "2")))
    retry_base_delay: float = field(
        default_factory=lambda: float(os.getenv("VISION_RETRY_BASE_DELAY", "1.0"))
    )
    # Compression / tiling (R1)
    auto_compress: bool = field(default_factory=lambda: os.getenv("VISION_AUTO_COMPRESS", "true").lower() == "true")
    max_long_edge: int = field(default_factory=lambda: int(os.getenv("VISION_MAX_LONG_EDGE", "1800")))
    max_pixels: int = field(default_factory=lambda: int(os.getenv("VISION_MAX_PIXELS", "3500000")))
    compress_quality: int = field(default_factory=lambda: int(os.getenv("VISION_COMPRESS_QUALITY", "85")))
    auto_tile: bool = field(default_factory=lambda: os.getenv("VISION_AUTO_TILE", "true").lower() == "true")
    tile_long_edge: int = field(default_factory=lambda: int(os.getenv("VISION_TILE_LONG_EDGE", "3600")))
    tile_overlap: int = field(default_factory=lambda: int(os.getenv("VISION_TILE_OVERLAP", "100")))
    max_tiles: int = field(default_factory=lambda: int(os.getenv("VISION_MAX_TILES", "8")))
    # Task routing (M2)
    task_routing: bool = field(default_factory=lambda: os.getenv("VISION_TASK_ROUTING", "true").lower() == "true")
    # Remote URL / SSRF (F1)
    allow_remote_url: bool = field(default_factory=lambda: os.getenv("VISION_ALLOW_REMOTE_URL", "true").lower() == "true")
    max_remote_size: int = field(default_factory=lambda: int(os.getenv("VISION_MAX_REMOTE_SIZE", "20971520")))
    fetch_timeout: float = field(default_factory=lambda: float(os.getenv("VISION_FETCH_TIMEOUT", "30")))
    ssrf_allow_private: bool = field(default_factory=lambda: os.getenv("VISION_SSRF_ALLOW_PRIVATE", "false").lower() == "true")
    # Batch images (F3)
    max_batch_images: int = field(default_factory=lambda: int(os.getenv("VISION_MAX_BATCH_IMAGES", "5")))
    # Reconstruct closed-loop / rendering (R2 v2)
    reconstruct_render: bool = field(default_factory=lambda: os.getenv("VISION_RECONSTRUCT_RENDER", "false").lower() == "true")
    reconstruct_max_iterations: int = field(default_factory=lambda: int(os.getenv("VISION_RECONSTRUCT_MAX_ITERATIONS", "2")))
    reconstruct_threshold: int = field(default_factory=lambda: int(os.getenv("VISION_RECONSTRUCT_THRESHOLD", "85")))
    render_timeout: float = field(default_factory=lambda: float(os.getenv("VISION_RENDER_TIMEOUT", "30")))
    render_viewport: str = field(default_factory=lambda: os.getenv("VISION_RENDER_VIEWPORT", "1280x800"))
    render_allow_network: bool = field(default_factory=lambda: os.getenv("VISION_RENDER_ALLOW_NETWORK", "false").lower() == "true")
    reconstruct_judge_model: str = field(default_factory=lambda: os.getenv("VISION_RECONSTRUCT_JUDGE_MODEL", ""))

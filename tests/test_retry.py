"""Retry and timeout tests (R4)."""
import time
from unittest.mock import patch

import httpx
import pytest

from vision_mcp.backends import OpenAICompatibleBackend
from vision_mcp.config import Config


def _response(status: int) -> httpx.Response:
    return httpx.Response(
        status,
        content=b"{}",
        request=httpx.Request("POST", "http://example/v1/chat/completions"),
    )


def _backend(**overrides) -> OpenAICompatibleBackend:
    config = Config(max_retries=2, retry_base_delay=1.0, **overrides)
    return OpenAICompatibleBackend(config)


def _analyze(backend, images=((b"img", "image/png"),)) -> str:
    return backend.analyze("prompt", list(images), "vision-model")


def test_5xx_retries_then_succeeds() -> None:
    backend = _backend()
    with patch("vision_mcp.backends.httpx.post", side_effect=[_response(500), _response(200)]) as post:
        result = _analyze(backend)
    assert result == "no response"
    assert post.call_count == 2


def test_4xx_does_not_retry() -> None:
    backend = _backend()
    with patch("vision_mcp.backends.httpx.post", return_value=_response(400)) as post:
        with pytest.raises(httpx.HTTPStatusError):
            _analyze(backend)
    assert post.call_count == 1


def test_reaches_limit_then_raises() -> None:
    backend = _backend()
    with patch("vision_mcp.backends.httpx.post", return_value=_response(503)) as post:
        with pytest.raises(httpx.HTTPStatusError):
            _analyze(backend)
    assert post.call_count == 3  # 1 + retries(2)


def test_transport_error_retries() -> None:
    backend = _backend()
    with patch(
        "vision_mcp.backends.httpx.post",
        side_effect=[httpx.ConnectError("boom"), _response(200)],
    ) as post:
        result = _analyze(backend)
    assert result == "no response"
    assert post.call_count == 2


def test_exponential_backoff_with_jitter() -> None:
    backend = _backend()
    with patch("vision_mcp.backends.httpx.post", return_value=_response(503)), patch(
        "vision_mcp.backends.time.sleep"
    ) as sleep:
        with pytest.raises(httpx.HTTPStatusError):
            _analyze(backend)
    assert sleep.call_count == 2
    first_delay = sleep.call_args_list[0].args[0]
    second_delay = sleep.call_args_list[1].args[0]
    assert 1.0 <= first_delay < 1.5
    assert 2.0 <= second_delay < 2.5

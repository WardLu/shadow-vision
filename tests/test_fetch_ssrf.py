"""SSRF and remote fetch tests (F1)."""
import socket
from unittest.mock import Mock, patch

import pytest

from vision_mcp import fetch
from vision_mcp.config import Config


def _addr(ip: str) -> list:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))]


def test_private_ipv4_rejected() -> None:
    with patch("vision_mcp.fetch.socket.getaddrinfo", return_value=_addr("10.0.0.1")):
        ok, reason = fetch.is_safe_url("http://internal/")
    assert ok is False
    assert "blocked" in reason


def test_metadata_ip_rejected() -> None:
    with patch("vision_mcp.fetch.socket.getaddrinfo", return_value=_addr("169.254.169.254")):
        ok, _ = fetch.is_safe_url("http://metadata/")
    assert ok is False


def test_loopback_rejected() -> None:
    with patch("vision_mcp.fetch.socket.getaddrinfo", return_value=_addr("127.0.0.1")):
        ok, _ = fetch.is_safe_url("http://localhost/")
    assert ok is False


def test_ipv6_ula_rejected() -> None:
    with patch("vision_mcp.fetch.socket.getaddrinfo", return_value=_addr("fc00::1")):
        ok, _ = fetch.is_safe_url("http://v6/")
    assert ok is False


def test_allow_private_overrides() -> None:
    with patch("vision_mcp.fetch.socket.getaddrinfo", return_value=_addr("10.0.0.1")):
        ok, _ = fetch.is_safe_url("http://internal/", allow_private=True)
    assert ok is True


def test_non_http_scheme_rejected() -> None:
    ok, reason = fetch.is_safe_url("file:///etc/passwd")
    assert ok is False
    assert "scheme" in reason


def test_userinfo_rejected() -> None:
    with patch("vision_mcp.fetch.socket.getaddrinfo", return_value=_addr("93.184.216.34")):
        ok, reason = fetch.is_safe_url("http://user:pass@example.com/img.png")
    assert ok is False
    assert "userinfo" in reason


def test_public_ip_allowed() -> None:
    with patch("vision_mcp.fetch.socket.getaddrinfo", return_value=_addr("93.184.216.34")):
        ok, _ = fetch.is_safe_url("http://example.com/img.png")
    assert ok is True


def _client() -> Mock:
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    return client


def _stream(status=200, ctype="image/png", chunks=(b"abc",)):
    resp = Mock()
    resp.status_code = status
    resp.headers = {"content-type": ctype}
    resp.iter_bytes.return_value = iter(chunks)
    resp.__enter__ = Mock(return_value=resp)
    resp.__exit__ = Mock(return_value=False)
    return resp


def test_fetch_valid_image() -> None:
    client = _client()
    client.stream.return_value = _stream()
    with patch("vision_mcp.fetch.is_safe_url", return_value=(True, "")), patch(
        "vision_mcp.fetch.httpx.Client", return_value=client
    ):
        data, mime = fetch.fetch_image_from_url("http://example.com/img.png", Config())
    assert data == b"abc"
    assert mime == "image/png"


def test_fetch_redirect_rejected() -> None:
    client = _client()
    client.stream.return_value = _stream(status=302)
    with patch("vision_mcp.fetch.is_safe_url", return_value=(True, "")), patch(
        "vision_mcp.fetch.httpx.Client", return_value=client
    ):
        with pytest.raises(ValueError, match="redirect"):
            fetch.fetch_image_from_url("http://example.com/img.png", Config())


def test_fetch_non_image_rejected() -> None:
    client = _client()
    client.stream.return_value = _stream(ctype="text/html")
    with patch("vision_mcp.fetch.is_safe_url", return_value=(True, "")), patch(
        "vision_mcp.fetch.httpx.Client", return_value=client
    ):
        with pytest.raises(ValueError, match="not an image"):
            fetch.fetch_image_from_url("http://example.com/img", Config())


def test_fetch_size_limit_aborts() -> None:
    client = _client()
    config = Config(max_remote_size=4)
    client.stream.return_value = _stream(chunks=(b"aaaa", b"bbbb"))
    with patch("vision_mcp.fetch.is_safe_url", return_value=(True, "")), patch(
        "vision_mcp.fetch.httpx.Client", return_value=client
    ):
        with pytest.raises(ValueError, match="size"):
            fetch.fetch_image_from_url("http://example.com/img.png", config)


def test_fetch_unsafe_url_raises() -> None:
    with patch("vision_mcp.fetch.is_safe_url", return_value=(False, "private address")):
        with pytest.raises(ValueError, match="private"):
            fetch.fetch_image_from_url("http://example.com/img.png", Config())

"""Renderer availability, network policy and degrade tests (R2 v2)."""
from unittest.mock import MagicMock, Mock, patch

import pytest

from vision_mcp import renderer
from vision_mcp.config import Config
from vision_mcp.renderer import PlaywrightRenderer, RenderError


class _FakePW:
    def __init__(self, png=b"PNGDATA"):
        page = Mock()
        page.screenshot.return_value = png
        browser = Mock()
        browser.new_page.return_value = page
        self.chromium = Mock()
        self.chromium.launch.return_value = browser

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _mock_sync(png=b"PNGDATA"):
    return _FakePW(png)


def test_available_when_playwright_and_chromium_present() -> None:
    with patch("vision_mcp.renderer._playwright_installed", return_value=True), patch(
        "vision_mcp.renderer._chromium_installed", return_value=True
    ):
        assert renderer.is_available() is True


def test_unavailable_when_playwright_missing() -> None:
    with patch("vision_mcp.renderer._playwright_installed", return_value=False), patch(
        "vision_mcp.renderer._chromium_installed", return_value=True
    ):
        assert renderer.is_available() is False


def test_unavailable_when_chromium_missing() -> None:
    with patch("vision_mcp.renderer._playwright_installed", return_value=True), patch(
        "vision_mcp.renderer._chromium_installed", return_value=False
    ):
        assert renderer.is_available() is False


def test_create_renderer_none_when_unavailable() -> None:
    with patch("vision_mcp.renderer.is_available", return_value=False):
        assert renderer.create_renderer(Config()) is None


def test_create_renderer_returns_playwright_when_available() -> None:
    with patch("vision_mcp.renderer.is_available", return_value=True):
        assert isinstance(renderer.create_renderer(Config()), PlaywrightRenderer)


def test_html_render_returns_png_and_uses_viewport() -> None:
    r = PlaywrightRenderer(Config(render_viewport="800x600", render_allow_network=False))
    with patch("vision_mcp.renderer._sync_playwright", return_value=_mock_sync(b"PNGDATA")) as sp:
        data = r.render("<html><body>hi</body></html>", "html")
    assert data == b"PNGDATA"
    ctx = sp.return_value
    browser = ctx.chromium.launch.return_value
    page = browser.new_page.return_value
    browser.new_page.assert_called_once()
    kw = browser.new_page.call_args.kwargs
    assert kw["viewport"] == {"width": 800, "height": 600}
    assert kw["device_scale_factor"] == 2
    page.screenshot.assert_called_once()


def test_no_network_aborts_requests() -> None:
    r = PlaywrightRenderer(Config(render_allow_network=False))
    with patch("vision_mcp.renderer._sync_playwright", return_value=_mock_sync()) as sp:
        r.render("<html></html>", "html")
    page = sp.return_value.chromium.launch.return_value.new_page.return_value
    page.route.assert_called_once_with("**", renderer._abort_route)


def test_network_allowed_skips_abort() -> None:
    r = PlaywrightRenderer(Config(render_allow_network=True))
    with patch("vision_mcp.renderer._sync_playwright", return_value=_mock_sync()) as sp:
        r.render("<html></html>", "html")
    page = sp.return_value.chromium.launch.return_value.new_page.return_value
    page.route.assert_not_called()


def test_react_with_network_disabled_raises() -> None:
    r = PlaywrightRenderer(Config(render_allow_network=False))
    with pytest.raises(RenderError, match="开网络"):
        r.render("const App = () => <div/>;", "react")


def test_svg_wrapped_in_html() -> None:
    r = PlaywrightRenderer(Config(render_allow_network=False))
    with patch("vision_mcp.renderer._sync_playwright", return_value=_mock_sync()) as sp:
        r.render("<svg><rect/></svg>", "svg")
    page = sp.return_value.chromium.launch.return_value.new_page.return_value
    assert page.goto.call_args.args[0].endswith(".html")

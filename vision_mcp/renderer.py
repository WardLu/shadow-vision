"""Code rendering for reconstruct closed-loop (R2 v2).

`Renderer` abstracts rendering generated code to PNG bytes. The Playwright
renderer loads a local HTML file and screenshots it. Network is blocked by
default (security); react requires CDN (babel-standalone) and degrades to
open-loop when network is disabled.
"""

from __future__ import annotations

import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from .config import Config

try:
    from playwright.sync_api import sync_playwright as _sync_playwright
except ImportError:  # pragma: no cover - optional dependency
    _sync_playwright = None

_REACT_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/babel-standalone@6/babel.min.js"></script></head><body>
<div id="root"></div>
<script type="text/babel">{code}</script>
</body></html>"""


class RenderError(Exception):
    """Raised when rendering fails (e.g. network policy, bad format)."""


class Renderer(ABC):
    @abstractmethod
    def render(self, code: str, target_format: str) -> bytes:
        """Render code to PNG bytes. Raise RenderError on failure."""


def _playwright_installed() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _chromium_installed() -> bool:
    if _sync_playwright is None:
        return False
    try:
        with _sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        return True
    except Exception:
        return False


def is_available() -> bool:
    """True when playwright is importable AND a chromium browser is installed."""
    return _playwright_installed() and _chromium_installed()


def create_renderer(config: Config) -> Renderer | None:
    """Return a PlaywrightRenderer when available, else None (caller degrades)."""
    if not is_available():
        return None
    return PlaywrightRenderer(config)


def _parse_viewport(spec: str) -> dict:
    width, height = spec.lower().split("x")
    return {"width": int(width), "height": int(height)}


def _wrap_html(code: str, target_format: str) -> str:
    if target_format == "html":
        return code
    if target_format == "svg":
        return f"<!doctype html><html><head><meta charset='utf-8'></head><body>{code}</body></html>"
    if target_format == "react":
        return _REACT_TEMPLATE.format(code=code)
    raise RenderError(f"unsupported target format: {target_format}")


def _abort_route(route) -> None:
    route.abort()


class PlaywrightRenderer(Renderer):
    def __init__(self, config: Config) -> None:
        self.viewport = _parse_viewport(config.render_viewport)
        self.allow_network = config.render_allow_network
        self.timeout = config.render_timeout

    def render(self, code: str, target_format: str) -> bytes:
        if target_format == "react" and not self.allow_network:
            raise RenderError("react 闭环需开网络（VISION_RENDER_ALLOW_NETWORK=true）")
        html = _wrap_html(code, target_format)
        if _sync_playwright is None:
            raise RenderError("playwright 未安装")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "render.html"
            path.write_text(html, encoding="utf-8")
            with _sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport=self.viewport, device_scale_factor=2)
                if not self.allow_network:
                    page.route("**", _abort_route)
                page.goto(path.as_uri())
                page.wait_for_load_state("networkidle", timeout=self.timeout * 1000)
                data = page.screenshot(full_page=True)
                browser.close()
            return data

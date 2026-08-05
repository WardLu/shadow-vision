"""Packaging metadata tests (F2)."""
import tomllib
from pathlib import Path

import vision_mcp

ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def test_version_nonempty() -> None:
    assert vision_mcp.__version__


def test_dynamic_version_single_source() -> None:
    data = _pyproject()
    assert "version" in data["project"].get("dynamic", [])
    hatch = data["tool"]["hatch"]["version"]
    assert hatch["source"] == "regex"
    version_path = ROOT / hatch["path"]
    assert "__version__" in version_path.read_text(encoding="utf-8")


def test_required_metadata_present() -> None:
    data = _pyproject()
    proj = data["project"]
    for field in ("name", "readme", "license", "requires-python", "classifiers", "authors"):
        assert field in proj, field
    assert data["project"].get("urls")


def test_script_entry_present() -> None:
    assert "vision-mcp" in _pyproject()["project"]["scripts"]


def test_render_extras_present() -> None:
    assert "render" in _pyproject()["project"]["optional-dependencies"]

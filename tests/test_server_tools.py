"""MCP tool schema tests."""
from vision_mcp.server import _build_tools
from vision_mcp.config import Config


def _props() -> dict:
    return {t.name: t.input_schema["properties"] for t in _build_tools(Config())}


def test_core_tools_present() -> None:
    names = set(_props())
    assert {"vision_ocr", "vision_inspect", "vision_annotate", "vision_layout", "vision_reconstruct", "vision_compare"} <= names


def test_inspect_task_enum() -> None:
    enum = _props()["vision_inspect"]["task"]["enum"]
    assert enum == ["general", "ui_structure", "ui_bug", "chart"]


def test_ocr_task_enum() -> None:
    enum = _props()["vision_ocr"]["task"]["enum"]
    assert enum == ["general", "error", "table"]


def test_annotate_schema() -> None:
    props = _props()["vision_annotate"]
    assert {"image_path", "image_base64", "mime_type", "focus", "model"} <= set(props)


def test_layout_schema() -> None:
    props = _props()["vision_layout"]
    assert props["task"]["enum"] == ["layout"]
    assert "model" in props


def test_reconstruct_schema() -> None:
    props = _props()["vision_reconstruct"]
    assert props["target_format"]["enum"] == ["html", "react", "svg"]
    assert "reference_layout" in props
    assert "model" in props


def test_all_image_tools_have_image_url() -> None:
    props = _props()
    for name in ("vision_ocr", "vision_inspect", "vision_annotate", "vision_layout", "vision_reconstruct"):
        assert "image_url" in props[name], name


def test_compare_schema() -> None:
    props = _props()["vision_compare"]
    assert props["task"]["enum"] == ["diff", "compare", "sequence"]
    assert props["images"]["maxItems"] == 5
    assert "model" in props

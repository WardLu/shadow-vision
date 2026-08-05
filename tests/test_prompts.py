"""Task routing tests (M2)."""
import pytest

from vision_mcp import prompts


def test_explicit_task_hits() -> None:
    tp = prompts.route("vision_ocr", "error", "", enable_routing=True)
    assert tp.name == "ocr_error"
    assert "error" in tp.user_prefix.lower()


def test_explicit_ui_structure_task() -> None:
    tp = prompts.route("vision_inspect", "ui_structure", "看看", enable_routing=True)
    assert tp.name == "inspect_ui_structure"


def test_ocr_defaults_to_general() -> None:
    tp = prompts.route("vision_ocr", None, "", enable_routing=True)
    assert tp.name == "ocr_general"


def test_inspect_heuristic_bug_keyword() -> None:
    tp = prompts.route("vision_inspect", None, "这个页面有 bug", enable_routing=True)
    assert tp.name == "inspect_ui_bug"


def test_inspect_heuristic_layout_keyword() -> None:
    tp = prompts.route("vision_inspect", None, "分析这个布局", enable_routing=True)
    assert tp.name == "inspect_ui_structure"


def test_inspect_heuristic_chart_keyword() -> None:
    tp = prompts.route("vision_inspect", None, "chart 趋势如何", enable_routing=True)
    assert tp.name == "inspect_chart"


def test_inspect_defaults_to_general() -> None:
    tp = prompts.route("vision_inspect", None, "随便看看", enable_routing=True)
    assert tp.name == "inspect_general"


def test_unknown_task_raises() -> None:
    with pytest.raises(ValueError):
        prompts.route("vision_ocr", "bogus", "", enable_routing=True)


def test_routing_disabled_falls_back_to_general() -> None:
    tp = prompts.route("vision_inspect", None, "有 bug", enable_routing=False)
    assert tp.name == "inspect_general"


def test_prompt_composition() -> None:
    tp = prompts.route("vision_inspect", "ui_bug", "检查首页", enable_routing=True)
    prompt = tp.user_prefix + "检查首页" + tp.output_hint
    assert "检查首页" in prompt
    assert tp.user_prefix


def test_annotate_prompt_requires_json() -> None:
    assert "STRICT JSON" in prompts.ANNOTATE_PROMPT
    assert "bbox" in prompts.ANNOTATE_PROMPT


def test_layout_prompt_requires_json() -> None:
    assert "STRICT JSON" in prompts.LAYOUT_PROMPT
    assert "canvas" in prompts.LAYOUT_PROMPT


def test_reconstruct_prompt_includes_format_and_self_check() -> None:
    prompt = prompts.reconstruct_prompt("html")
    assert "html" in prompt
    assert "SELF-CHECK" in prompt


def test_reconstruct_prompt_includes_reference_when_given() -> None:
    prompt = prompts.reconstruct_prompt("react", reference_layout='{"canvas":{}}')
    assert '{"canvas":{}}' in prompt


def test_compare_prompt_diff() -> None:
    prompt = prompts.compare_prompt("diff", "列出不同", ["A", "B"])
    assert "differences" in prompt
    assert "图1=A" in prompt


def test_compare_prompt_labels_skipped_when_empty() -> None:
    prompt = prompts.compare_prompt("compare", "q", [None, None])
    assert "图片标签" not in prompt


def test_compare_render_prompt_requires_json() -> None:
    prompt = prompts.compare_render_prompt()
    assert "STRICT JSON" in prompt
    assert "score" in prompt


def test_refine_prompt_includes_code_and_differences() -> None:
    prompt = prompts.refine_prompt("<code>", {"differences": ["x"], "suggestions": "y"})
    assert "x" in prompt
    assert "y" in prompt
    assert "<code>" in prompt


def test_reconstruct_prompt_inline_constraint() -> None:
    prompt = prompts.reconstruct_prompt("html")
    assert "self-contained" in prompt.lower() or "no external dependencies" in prompt.lower()

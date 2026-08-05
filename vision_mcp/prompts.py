"""Task-specific prompts and heuristic routing (M2).

External enums are user-friendly (no tool prefix); internal TASKS keys use
`{tool_key}_{task}` (e.g. `inspect_ui_bug`). `route` maps externally supplied
task values to TaskPrompts and runs lightweight keyword heuristics for
`vision_inspect` when no task is given.
"""

from __future__ import annotations

from dataclasses import dataclass

OCR_GENERAL = "Extract all text visible in this image. Return only the text, no commentary."
OCR_ERROR = (
    "This is an error/screenshot report. Extract the error title, error code, and key "
    "stack lines in order. Return only the extracted text, no commentary."
)
OCR_TABLE = (
    "This is a table or data screenshot. Preserve the table structure and row/column "
    "alignment, extracting each cell's text. Return only the text, no commentary."
)

INSPECT_UI_BUG = "Inspect this UI from a visual and layout perspective and identify bugs or visual anomalies (alignment, overflow, missing elements, broken hierarchy): "
INSPECT_UI_STRUCTURE = "Analyze this UI's component tree and layout structure (container hierarchy, positioning, spacing): "
INSPECT_CHART = "Interpret this chart's data and trend (axes, values, trend, takeaway): "

LAYOUT_PROMPT = (
    "Analyze this UI/image and extract its layout structure. Return STRICT JSON only, "
    'no markdown, with schema: {"canvas":{"width":0,"height":0,"background":"#ffffff"},'
    '"elements":[{"id":"el_1","type":"container|text|image|button|icon|qr_code",'
    '"bbox":[0,0,0,0],"text":"","styles":{"font_size":14,"color":"#111",'
    '"font_weight":"normal","align":"left"},"image_region":{"crop_index":0,'
    '"description":""},"parent":"root","children":[]}],'
    '"relations":[{"from":"el_1","to":"el_2","type":"contains|adjacent|overlaps"}]}'
)


def reconstruct_prompt(target_format: str, reference_layout: str | None = None) -> str:
    """Build the reconstruction prompt for a target format, optionally with a
    reference layout JSON from vision_layout, plus a model self-check."""
    inline = (
        "Output must be self-contained inline HTML with no external dependencies "
        "(no CDN or external links), because rendering runs with network disabled by "
        "default. For the react format, output JSX component code that relies on CDN "
        "(only renderable when network is enabled)."
    )
    prompt = (
        f"Reconstruct this screenshot into {target_format} code. Produce runnable, "
        "faithful code that mirrors the layout, colors, text, and spacing. After the "
        f"code, add a SELF-CHECK section listing any discrepancies you noticed between "
        f"the reference image and your implementation.\n{inline}"
    )
    if reference_layout:
        prompt += f"\nUse this reference layout JSON as a guide:\n{reference_layout}"
    return prompt


def compare_render_prompt() -> str:
    """Prompt that compares the original reference image with the rendered
    screenshot, returning a strict JSON verdict."""
    return (
        "Compare the original reference image with the rendered screenshot of the "
        "reconstructed code. Ignore differences in size/scale between the two images; "
        "focus on structure, layout, colors, and text consistency. Return STRICT JSON "
        'only, no markdown, with schema: {"match": false, "score": 85, '
        '"differences": ["..."], "suggestions": "..."}. score is 0-100 overall visual '
        "similarity; match is true when the rendering is acceptably faithful."
    )


def refine_prompt(prev_code: str, verdict: dict) -> str:
    """Build a refinement prompt feeding the previous code and the verdict's
    differences back, asking for a complete corrected revision."""
    diffs = verdict.get("differences") or []
    suggestions = verdict.get("suggestions") or ""
    parts = [
        "The previous reconstruction did not fully match the reference image. Differences found:",
    ]
    if diffs:
        parts.extend(f"- {d}" for d in diffs)
    else:
        parts.append("- (unspecified)")
    if suggestions:
        parts.append(f"Suggestions: {suggestions}")
    parts.append(
        "Produce the complete corrected code (no SELF-CHECK section, since the loop "
        "has a real visual comparison). Keep it self-contained inline HTML with no "
        "external dependencies, unless network is explicitly enabled."
    )
    parts.append("Previous code:\n```\n" + prev_code + "\n```")
    return "\n".join(parts)


ANNOTATE_PROMPT = (
    "Analyze the user's visual annotations on this image (circles, arrows, underlines, "
    "highlights, scribbles, handwritten text). Identify each annotation's type, position, "
    "confidence, and the target region it points to. Return STRICT JSON only, no markdown, "
    'with schema: {"annotations":[{"type":"circle|arrow|underline|highlight|scribble|'
    'handwritten_text","bbox":[x,y,w,h],"confidence":0.0,"target":{"description":"",'
    '"bbox":[x,y,w,h],"text":""},"handwritten_text":""}],"summary":""}'
)


@dataclass(frozen=True)
class TaskPrompt:
    name: str
    user_prefix: str
    output_hint: str = ""


TASKS: dict[str, TaskPrompt] = {
    "ocr_general": TaskPrompt("ocr_general", OCR_GENERAL),
    "ocr_error": TaskPrompt("ocr_error", OCR_ERROR),
    "ocr_table": TaskPrompt("ocr_table", OCR_TABLE),
    "inspect_general": TaskPrompt("inspect_general", ""),
    "inspect_ui_structure": TaskPrompt("inspect_ui_structure", INSPECT_UI_STRUCTURE),
    "inspect_ui_bug": TaskPrompt("inspect_ui_bug", INSPECT_UI_BUG),
    "inspect_chart": TaskPrompt("inspect_chart", INSPECT_CHART),
}

# External enum values exposed to the user (no tool prefix).
OCR_TASKS = {"general", "error", "table"}
INSPECT_TASKS = {"general", "ui_structure", "ui_bug", "chart"}

_BUG_KEYS = ("bug", "错误", "error")
_STRUCTURE_KEYS = ("布局", "结构", "layout", "组件")
_CHART_KEYS = ("图表", "chart", "趋势")


def route(tool: str, task: str | None, question: str, *, enable_routing: bool = True) -> TaskPrompt:
    """Resolve a TaskPrompt. Explicit task wins; otherwise heuristic routing for
    inspect, or general for ocr. Unknown task raises ValueError."""
    tool_key = tool.removeprefix("vision_")
    if task:
        key = f"{tool_key}_{task}"
        if key not in TASKS:
            raise ValueError(f"unknown task '{task}' for tool '{tool}'")
        return TASKS[key]
    if not enable_routing:
        return TASKS[f"{tool_key}_general"]
    if tool_key == "ocr":
        return TASKS["ocr_general"]
    q = question.lower()
    if any(k in q for k in _BUG_KEYS):
        return TASKS["inspect_ui_bug"]
    if any(k in q for k in _STRUCTURE_KEYS):
        return TASKS["inspect_ui_structure"]
    if any(k in q for k in _CHART_KEYS):
        return TASKS["inspect_chart"]
    return TASKS["inspect_general"]


COMPARE_HINTS = {
    "diff": "Compare these images and describe their differences in detail.",
    "compare": "Compare these images.",
    "sequence": "Analyze these images as a sequence and describe the transitions between them.",
}


def compare_prompt(task: str, question: str, labels: list[str] | None = None) -> str:
    """Build the compare prompt for a task, optional question and image labels."""
    hint = COMPARE_HINTS.get(task, COMPARE_HINTS["compare"])
    parts = [hint]
    if question:
        parts.append(question)
    if labels:
        indexed = "，".join(f"图{i + 1}={lbl}" for i, lbl in enumerate(labels) if lbl)
        if indexed:
            parts.append(f"图片标签：{indexed}")
    return "\n".join(parts)

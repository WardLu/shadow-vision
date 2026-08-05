"""Closed-loop reconstruct orchestrator (R2 v2).

Open-loop by default; when enabled and a renderer is available, generates code,
renders it, compares against the reference, and iterates on differences.
"""

from __future__ import annotations

import json
import re

from . import prompts
from .backends import VisionBackend
from .config import Config
from .renderer import RenderError, create_renderer

_DEFAULT_VERDICT = {"match": False, "score": -1, "differences": [], "suggestions": ""}


def _parse_verdict(text: str) -> dict:
    """Extract the first top-level JSON object and parse it. On any failure
    return a verdict with score=-1 (triggers iteration or degrade)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return dict(_DEFAULT_VERDICT)
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return dict(_DEFAULT_VERDICT)
    return {
        "match": bool(data.get("match", False)),
        "score": int(data.get("score", -1)),
        "differences": data.get("differences", []) or [],
        "suggestions": data.get("suggestions", "") or "",
    }


def _satisfied(verdict: dict, threshold: int) -> bool:
    return bool(verdict.get("match")) or int(verdict.get("score", -1)) >= threshold


def _report(code: str, verdict: dict, iterations: int, max_iterations: int, status: str) -> str:
    diffs = verdict.get("differences") or []
    diff_text = "; ".join(diffs) if diffs else "无"
    met = "已达标" if _satisfied(verdict, 0) else "未达标"
    return (
        f"{code}\n\n--- 闭环校验报告 ---\n"
        f"迭代轮数: {iterations}/{max_iterations}\n"
        f"最终评分: {int(verdict.get('score', -1))}/100（阈值 {max_iterations}，{met}）\n"
        f"差异: {diff_text}\n"
        f"渲染状态: {status}"
    )


def run(
    config: Config,
    backend: VisionBackend,
    images: list[tuple[bytes, str]],
    args: dict,
    model: str,
) -> str:
    """Open-loop by default; closed-loop when config.reconstruct_render and a
    renderer is available. Returns a text report for CallToolResult."""
    target_format = str(args.get("target_format", "html"))
    reference_layout = args.get("reference_layout")
    render_on = bool(args.get("render", config.reconstruct_render))
    max_iterations = int(args.get("iterations", config.reconstruct_max_iterations))
    threshold = config.reconstruct_threshold
    judge_model = config.reconstruct_judge_model or model

    code = backend.analyze(prompts.reconstruct_prompt(target_format, reference_layout), images, model)

    if not render_on:
        return code

    renderer = create_renderer(config)
    if renderer is None:
        return code + "\n\n--- 降级说明 ---\n闭环不可用（未装 playwright/chromium），已降级为开环自检。"

    try:
        render_data = renderer.render(code, target_format)
    except RenderError as exc:
        return code + f"\n\n--- 降级说明 ---\n闭环渲染失败（{exc}），已降级为开环自检。"

    compare_images = images + [(render_data, "image/png")]
    verdict = _parse_verdict(backend.analyze(prompts.compare_render_prompt(), compare_images, judge_model))

    iterations_used = 0
    for i in range(1, max_iterations + 1):
        if _satisfied(verdict, threshold):
            break
        code = backend.analyze(prompts.refine_prompt(code, verdict), compare_images, model)
        try:
            render_data = renderer.render(code, target_format)
        except RenderError as exc:
            return _report(code, verdict, iterations_used, max_iterations, f"降级开环（{exc}）")
        compare_images = images + [(render_data, "image/png")]
        verdict = _parse_verdict(backend.analyze(prompts.compare_render_prompt(), compare_images, judge_model))
        iterations_used = i

    return _report(code, verdict, iterations_used, max_iterations, "成功")

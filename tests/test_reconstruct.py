"""Closed-loop reconstruction orchestrator tests (R2 v2)."""
import json
from unittest.mock import Mock, patch

from vision_mcp import reconstruct
from vision_mcp.config import Config
from vision_mcp.renderer import RenderError


def _backend() -> Mock:
    b = Mock()
    b.analyze.side_effect = lambda prompt, images, model: "code"
    return b


def _verdict(score=90, match=True):
    return json.dumps({"match": match, "score": score, "differences": ["a"], "suggestions": "b"})


def _renderer(png=b"PNG"):
    r = Mock()
    r.render.return_value = png
    return r


def _args(**kw):
    base = {"target_format": "html"}
    base.update(kw)
    return base


def test_rendering_disabled_returns_open_loop() -> None:
    config = Config(reconstruct_render=False)
    backend = _backend()
    with patch("vision_mcp.reconstruct.create_renderer") as cr:
        out = reconstruct.run(config, backend, [(b"x", "image/png")], _args(), "m")
    assert out == "code"
    cr.assert_not_called()
    assert backend.analyze.call_count == 1


def test_renderer_unavailable_degrades_to_open_loop() -> None:
    config = Config(reconstruct_render=True)
    backend = _backend()
    with patch("vision_mcp.reconstruct.create_renderer", return_value=None) as cr:
        out = reconstruct.run(config, backend, [(b"x", "image/png")], _args(), "m")
    cr.assert_called_once()
    assert "降级" in out
    assert "闭环不可用" in out


def test_closed_loop_stops_when_satisfied() -> None:
    config = Config(reconstruct_render=True, reconstruct_threshold=85)
    backend = _backend()
    backend.analyze.side_effect = ["code", _verdict(score=90, match=True)]
    with patch("vision_mcp.reconstruct.create_renderer", return_value=_renderer()):
        out = reconstruct.run(config, backend, [(b"x", "image/png")], _args(), "m")
    assert "闭环校验报告" in out
    assert "已达标" in out


def test_closed_loop_iterates_to_limit() -> None:
    config = Config(reconstruct_render=True, reconstruct_threshold=85, reconstruct_max_iterations=2)
    backend = _backend()
    # 1 generate + 3 compares (initial + 2 iterations), never satisfied
    backend.analyze.side_effect = ["code", _verdict(score=50, match=False), "code2",
                                   _verdict(score=60, match=False), "code3",
                                   _verdict(score=70, match=False)]
    with patch("vision_mcp.reconstruct.create_renderer", return_value=_renderer()):
        out = reconstruct.run(config, backend, [(b"x", "image/png")], _args(), "m")
    assert "迭代轮数: 2/2" in out


def test_max_iterations_zero_single_round() -> None:
    config = Config(reconstruct_render=True, reconstruct_max_iterations=0)
    backend = _backend()
    backend.analyze.side_effect = ["code", _verdict(score=50, match=False)]
    with patch("vision_mcp.reconstruct.create_renderer", return_value=_renderer()):
        out = reconstruct.run(config, backend, [(b"x", "image/png")], _args(), "m")
    assert "迭代轮数: 0/0" in out
    assert backend.analyze.call_count == 2


def test_render_failure_degrades_current_round() -> None:
    config = Config(reconstruct_render=True)
    backend = _backend()
    backend.analyze.side_effect = ["code", _verdict(score=60, match=False)]
    r = _renderer()
    r.render.side_effect = RenderError("react 闭环需开网络")
    with patch("vision_mcp.reconstruct.create_renderer", return_value=r):
        out = reconstruct.run(config, backend, [(b"x", "image/png")], _args(), "m")
    assert "渲染失败" in out
    assert "降级" in out


def test_verdict_parse_tolerates_markdown() -> None:
    config = Config(reconstruct_render=True, reconstruct_threshold=85)
    backend = _backend()
    backend.analyze.side_effect = ["code", "Here is the result: ```json\n" + _verdict(95, True) + "\n```"]
    with patch("vision_mcp.reconstruct.create_renderer", return_value=_renderer()):
        out = reconstruct.run(config, backend, [(b"x", "image/png")], _args(), "m")
    assert "已达标" in out


def test_verdict_parse_failure_triggers_iteration() -> None:
    config = Config(reconstruct_render=True, reconstruct_threshold=85, reconstruct_max_iterations=1)
    backend = _backend()
    backend.analyze.side_effect = ["code", "not json at all", "code2", _verdict(90, True)]
    with patch("vision_mcp.reconstruct.create_renderer", return_value=_renderer()):
        out = reconstruct.run(config, backend, [(b"x", "image/png")], _args(), "m")
    assert "已达标" in out


def test_judge_model_used_for_compare() -> None:
    config = Config(reconstruct_render=True, reconstruct_threshold=85)
    backend = _backend()
    backend.analyze.side_effect = ["code", _verdict(90, True)]
    with patch("vision_mcp.reconstruct.create_renderer", return_value=_renderer()):
        reconstruct.run(config, backend, [(b"x", "image/png")], _args(), "m")
    generate_call, compare_call = backend.analyze.call_args_list
    assert generate_call.args[2] == "m"
    assert compare_call.args[2] == "m"


def test_judge_model_custom() -> None:
    config = Config(reconstruct_render=True, reconstruct_threshold=85, reconstruct_judge_model="judge-strong")
    backend = _backend()
    backend.analyze.side_effect = ["code", _verdict(90, True)]
    with patch("vision_mcp.reconstruct.create_renderer", return_value=_renderer()):
        reconstruct.run(config, backend, [(b"x", "image/png")], _args(), "m")
    generate_call, compare_call = backend.analyze.call_args_list
    assert generate_call.args[2] == "m"
    assert compare_call.args[2] == "judge-strong"

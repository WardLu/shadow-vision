"""MCP server layer.

Handles tool definitions and dispatch only. All vision logic lives in
`vision_mcp.backends`, so the backend can be swapped independently.
"""

from __future__ import annotations

import sys
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams, Tool

from .backends import _load_images, _load_images_batch, create_backend
from .config import Config
from . import __version__
from . import reconstruct
from . import prompts

DEFAULT_QUESTION = "Describe this image in detail."


def _tile_hint(loaded: list) -> dict | None:
    """Return tile meta when a single image was split into blocks."""
    if len(loaded) == 1:
        meta = loaded[0][2]
        if meta and meta.get("total", 1) > 1:
            return meta
    return None


def _with_tile_hint(base: str, meta: dict | None) -> str:
    if not meta:
        return base
    return (
        f"{base}\n\n输入图像为长图切块（共{meta['total']}块，按顺序排列），"
        "重叠区域内容可能重复，请仅保留一份，按序完整输出。"
    )


def _build_tools(config: Config) -> list[Tool]:
    return [
        Tool(
            name="vision_ocr",
            description="Extract all text from an image. Pass image_path (local file) or image_base64 + mime_type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Local path to the image file"},
                    "image_base64": {"type": "string", "description": "Base64-encoded image data"},
                    "mime_type": {"type": "string", "description": "MIME type of image_base64 (e.g. image/png)"},
                    "image_url": {"type": "string", "description": "Remote HTTP(S) image URL"},
                    "task": {"type": "string", "enum": ["general", "error", "table"], "description": "Optional OCR task hint"},
                    "model": {"type": "string", "description": "Vision model name", "default": config.model},
                },
            },
        ),
        Tool(
            name="vision_inspect",
            description="Describe or answer questions about an image. Pass image_path (local file) or image_base64 + mime_type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Local path to the image file"},
                    "image_base64": {"type": "string", "description": "Base64-encoded image data"},
                    "mime_type": {"type": "string", "description": "MIME type of image_base64 (e.g. image/png)"},
                    "image_url": {"type": "string", "description": "Remote HTTP(S) image URL"},
                    "question": {"type": "string", "description": "Question to ask about the image", "default": DEFAULT_QUESTION},
                    "task": {"type": "string", "enum": ["general", "ui_structure", "ui_bug", "chart"], "description": "Optional inspect task hint"},
                    "model": {"type": "string", "description": "Vision model name", "default": config.model},
                },
            },
        ),
        Tool(
            name="vision_annotate",
            description="Identify user's visual annotations (circles, arrows, underlines, highlights, scribbles, handwritten text) and their targets, returning structured JSON.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Local path to the image file"},
                    "image_base64": {"type": "string", "description": "Base64-encoded image data"},
                    "mime_type": {"type": "string", "description": "MIME type of image_base64 (e.g. image/png)"},
                    "image_url": {"type": "string", "description": "Remote HTTP(S) image URL"},
                    "focus": {"type": "string", "description": "User note to help interpret annotation intent"},
                    "model": {"type": "string", "description": "Vision model name", "default": config.model},
                },
            },
        ),
        Tool(
            name="vision_layout",
            description="Analyze an image's layout structure and return structured JSON (canvas, elements, relations).",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Local path to the image file"},
                    "image_base64": {"type": "string", "description": "Base64-encoded image data"},
                    "mime_type": {"type": "string", "description": "MIME type of image_base64 (e.g. image/png)"},
                    "image_url": {"type": "string", "description": "Remote HTTP(S) image URL"},
                    "task": {"type": "string", "enum": ["layout"], "description": "Layout task hint"},
                    "model": {"type": "string", "description": "Vision model name", "default": config.model},
                },
            },
        ),
        Tool(
            name="vision_reconstruct",
            description="Reconstruct a screenshot into code (html/react/svg) with a model self-check.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Local path to the image file"},
                    "image_base64": {"type": "string", "description": "Base64-encoded image data"},
                    "mime_type": {"type": "string", "description": "MIME type of image_base64 (e.g. image/png)"},
                    "image_url": {"type": "string", "description": "Remote HTTP(S) image URL"},
                    "target_format": {"type": "string", "enum": ["html", "react", "svg"], "default": "html"},
                    "reference_layout": {"type": "string", "description": "Optional JSON output from vision_layout"},
                    "render": {"type": "boolean", "description": "Attempt closed-loop rendering (default from VISION_RECONSTRUCT_RENDER)"},
                    "iterations": {"type": "integer", "description": "Max refinement iterations (default from config)"},
                    "model": {"type": "string", "description": "Vision model name", "default": config.model},
                },
            },
        ),
        Tool(
            name="vision_compare",
            description="Analyze multiple related images (diff, compare, sequence) in one call.",
            inputSchema={
                "type": "object",
                "properties": {
                    "images": {
                        "type": "array",
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "properties": {
                                "image_path": {"type": "string", "description": "Local path to the image file"},
                                "image_base64": {"type": "string", "description": "Base64-encoded image data"},
                                "image_url": {"type": "string", "description": "Remote HTTP(S) image URL"},
                                "mime_type": {"type": "string", "description": "MIME type of image_base64"},
                                "label": {"type": "string", "description": "Image label for reference"},
                            },
                        },
                    },
                    "task": {"type": "string", "enum": ["diff", "compare", "sequence"], "default": "compare"},
                    "question": {"type": "string", "description": "Question to ask about the images", "default": DEFAULT_QUESTION},
                    "model": {"type": "string", "description": "Vision model name", "default": config.model},
                },
            },
        ),
    ]


def _make_server() -> Server:
    config = Config()
    backend = create_backend(config)
    tools = _build_tools(config)

    async def _list_tools(_ctx, _params) -> ListToolsResult:
        return ListToolsResult(tools=tools)

    async def _call_tool(_ctx, params: CallToolRequestParams) -> CallToolResult:
        args = params.arguments or {}
        try:
            model = args.get("model", config.model)
            loaded = _load_images(config, args)
            images = [(data, mime) for data, mime, _ in loaded]
            tile_meta = _tile_hint(loaded)

            if params.name == "vision_ocr":
                tp = prompts.route("vision_ocr", args.get("task"), "", enable_routing=config.task_routing)
                prompt = tp.user_prefix + tp.output_hint
                result = backend.analyze(_with_tile_hint(prompt, tile_meta), images, model)
            elif params.name == "vision_inspect":
                question = str(args.get("question", DEFAULT_QUESTION))
                tp = prompts.route("vision_inspect", args.get("task"), question, enable_routing=config.task_routing)
                prompt = tp.user_prefix + question + tp.output_hint
                result = backend.analyze(_with_tile_hint(prompt, tile_meta), images, model)
            elif params.name == "vision_annotate":
                focus = str(args.get("focus", ""))
                prompt = prompts.ANNOTATE_PROMPT
                if focus:
                    prompt += f"\nUser intent note: {focus}"
                result = backend.analyze(_with_tile_hint(prompt, tile_meta), images, model)
            elif params.name == "vision_layout":
                loaded = _load_images(config, args, tile=False)
                images = [(d, m) for d, m, _ in loaded]
                result = backend.analyze(prompts.LAYOUT_PROMPT, images, model)
            elif params.name == "vision_reconstruct":
                loaded = _load_images(config, args, tile=False)
                images = [(d, m) for d, m, _ in loaded]
                result = reconstruct.run(config, backend, images, args, model)
            elif params.name == "vision_compare":
                images, labels = _load_images_batch(config, args)
                task = str(args.get("task", "compare"))
                question = str(args.get("question", ""))
                prompt = prompts.compare_prompt(task, question, labels)
                result = backend.analyze(prompt, images, model)
            else:
                return CallToolResult(
                    content=[{"type": "text", "text": f"unknown tool: {params.name}"}],
                    isError=True,
                )
            return CallToolResult(content=[{"type": "text", "text": result}])
        except Exception as exc:  # noqa: BLE001
            return CallToolResult(
                content=[{"type": "text", "text": f"error: {exc}"}],
                isError=True,
            )

    server = Server("shadow-vision", version=__version__)
    server.add_request_handler("tools/list", PaginatedRequestParams, _list_tools)
    server.add_request_handler("tools/call", CallToolRequestParams, _call_tool)
    return server


async def main_async() -> None:
    server = _make_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    if "--version" in sys.argv:
        print(f"shadow-vision {__version__}")
        return
    import anyio

    anyio.run(main_async)


if __name__ == "__main__":
    main()

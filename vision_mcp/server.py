"""MCP server layer.

Handles tool definitions and dispatch only. All vision logic lives in
`vision_mcp.backends`, so the backend can be swapped independently.
"""

from __future__ import annotations

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams, Tool

from .backends import _read_image, create_backend
from .config import Config

OCR_PROMPT = "Extract all text visible in this image. Return only the text, no commentary."
DEFAULT_QUESTION = "Describe this image in detail."


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
                    "question": {"type": "string", "description": "Question to ask about the image", "default": DEFAULT_QUESTION},
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
            image_path = str(args.get("image_path", ""))
            image_base64 = args.get("image_base64")
            mime_type = args.get("mime_type")
            model = args.get("model", config.model)
            data, mime = _read_image(image_path, image_base64, mime_type)

            if params.name == "vision_ocr":
                result = backend.analyze(OCR_PROMPT, data, mime, model)
            elif params.name == "vision_inspect":
                question = str(args.get("question", DEFAULT_QUESTION))
                result = backend.analyze(question, data, mime, model)
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

    server = Server("vision-mcp", version="0.1.0")
    server.add_request_handler("tools/list", PaginatedRequestParams, _list_tools)
    server.add_request_handler("tools/call", CallToolRequestParams, _call_tool)
    return server


async def main_async() -> None:
    server = _make_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    import anyio

    anyio.run(main_async)


if __name__ == "__main__":
    main()

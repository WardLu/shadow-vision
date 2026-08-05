# shadow-vision

Thin npm wrapper that runs the [`vision-mcp`](https://pypi.org/project/vision-mcp/)
Python package via `uvx`.

Requires [uv](https://docs.astral.sh/uv/) to be installed.

```bash
npx shadow-vision --help      # passthrough to `uvx vision-mcp`
```

For MCP usage, configure `command = "uvx"` / `args = ["vision-mcp"]` and set
the `VISION_*` environment variables in your MCP client config.

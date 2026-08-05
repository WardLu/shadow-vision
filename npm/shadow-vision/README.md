# shadow-vision

Thin npm wrapper that runs the [`shadow-vision`](https://pypi.org/project/shadow-vision/)
Python package via `uvx`.

Requires [uv](https://docs.astral.sh/uv/) to be installed.

```bash
npx shadow-vision --help      # passthrough to `uvx shadow-vision`
```

For MCP usage, configure `command = "uvx"` / `args = ["shadow-vision"]` and set
the `VISION_*` environment variables in your MCP client config.

# 影瞳 Shadow Vision · Roadmap 批次 2 设计文档（R2 v2 闭环渲染 + F2 一键分发）

> 起草日期：2026-08-05
> 分支：`feature/roadmap-batch`（基于已实施的 R1-R4/M2/F1/F3 代码，working tree 未提交）
> 覆盖范围：ROADMAP.md 中「R2 v2 截图复刻闭环渲染」+「F2 npm/PyPI 一键分发」
> 状态：设计中，待评审后进入实现
> 前序设计：`docs/design/roadmap-batch.md`（批次 1，已实施）

## 1. 背景与目标

批次 1 已交付 R1-R4/M2/F1/F3 七项，其中 R2 的 `vision_reconstruct` 以**开环**形态落地（生成代码 + 模型 self-check，无真实渲染校验）。本批次补齐两项「远期/收尾」需求：

| 编号 | 需求 | ROADMAP 分档 | 目标 |
|---|---|---|---|
| R2-v2 | 截图复刻闭环渲染 | 近期（v2 增强） | 生成代码后用 Playwright 渲染截图，与原图视觉对比并迭代修正 |
| F2 | npm/PyPI 一键分发 | 远期 | `uvx shadow-vision` / `npx shadow-vision` 即装即用，免 clone |

两者独立，可并行实现，无相互依赖。

## 2. 现状基线（批次 1 已实施代码）

### 2.1 `vision_reconstruct` 开环实现（待闭环化）

`vision_mcp/server.py:181-187`：
```python
elif params.name == "vision_reconstruct":
    loaded = _load_images(config, args, tile=False)
    images = [(d, m) for d, m, _ in loaded]
    target_format = str(args.get("target_format", "html"))
    reference_layout = args.get("reference_layout")
    prompt = prompts.reconstruct_prompt(target_format, reference_layout)
    result = backend.analyze(prompt, images, model)
```

`vision_mcp/prompts.py:38-49` 的 `reconstruct_prompt`：生成代码 + 要求模型附 SELF-CHECK 段。无渲染、无对比、无迭代。

### 2.2 可复用的扩展点

- **`VisionBackend.analyze(prompt, images: list[tuple[bytes, str]], model) -> str`**（`backends.py:73`）：同步多图接口，闭环的「对比」与「修正」步骤可直接复用，无需新后端。
- **`_load_images(config, args, tile=...)`**（`backends.py:190`）：归一 image_path/base64/url 到 `[(bytes, mime, meta)]`。闭环里渲染截图是 `bytes`，可直接拼成 `[(render_bytes, "image/png")]` 喂给 `analyze`。
- **`Config` frozen dataclass**（`config.py:24`）：加字段即加环境变量，模式成熟。
- **`[render]` extras**（`pyproject.toml:9`）：`playwright>=1.40.0` 已声明但未被代码使用，本批次落地。
- **`pyproject.toml`**：hatchling 后端 + `shadow-vision` script entry + 静态 `version = "0.1.0"`。

### 2.3 约束

- **轻量定位**：Playwright（~150MB + 浏览器二进制）必须保持可选，闭环默认关闭，降级路径完整。
- **同步阻塞**：`analyze` 同步，闭环多轮调用会让单次工具调用变长（分钟级）。需限制迭代轮数并文档警示。
- **安全**：渲染模型生成的代码有 XSS/恶意 JS 风险；本地 MCP 场景信任度较高，但仍默认禁网渲染。
- **版本号铁律**：升级版本必须与用户确认，设计仅建议目标版本。

## 3. R2 v2 - 截图复刻闭环渲染

### 3.1 总体流程

```
vision_reconstruct(args)
  │
  ▼
reconstruct.run(config, backend, original_images, args)
  │
  ├─ 1. 生成代码：code₀ = backend.analyze(reconstruct_prompt(fmt, ref), [original], model)
  │
  ├─ 2. 渲染：render₀ = renderer.render(code₀)  ── 失败则降级开环
  │
  ├─ 3. 对比：verdict = backend.analyze(compare_prompt(), [original, render₀], model)
  │     → {match: bool, score: 0-100, differences: [...], suggestions: str}
  │
  ├─ 4. 迭代（i = 1..max_iterations）：
  │     若 verdict.match 或 score ≥ threshold → 停
  │     否则 codeᵢ = backend.analyze(refine_prompt(codeᵢ₋₁, verdict), [original, renderᵢ₋₁], model)
  │            renderᵢ = renderer.render(codeᵢ)
  │            verdict = backend.analyze(compare_prompt(), [original, renderᵢ], model)
  │
  └─ 5. 返回：最终 code + verdict（score/differences/match）+ 迭代轮数 + 渲染状态
```

第 0 轮即「生成+渲染+对比」；若已达标直接停，不进入迭代。`max_iterations` 指后续修正轮数（默认 2，即最多 3 次 analyze + 3 次渲染）。

### 3.2 渲染器抽象 `vision_mcp/renderer.py`

```python
class RenderError(Exception): ...

class Renderer(ABC):
    @abstractmethod
    def render(self, code: str, target_format: str) -> bytes:
        """Render code to PNG bytes. Raise RenderError on failure."""

class PlaywrightRenderer(Renderer):
    def __init__(self, config: Config) -> None: ...
    def render(self, code: str, target_format: str) -> bytes: ...

def is_available() -> bool:
    """True if playwright importable AND browser installed."""

def create_renderer(config: Config) -> Renderer | None:
    """Return PlaywrightRenderer if available, else None (caller degrades to open-loop)."""
```

**渲染策略（统一为加载本地 HTML 文件）**：
- `html` / `svg`：模型输出即为可独立打开的 HTML/SVG；写入临时文件，Playwright 加载截图。
- `react`：**v2 不在闭环里跑构建工具链**（webpack/vite 过重）。模型输出 JSX 组件代码；renderer 用 **babel-standalone 内联模板**包一层生成可截图 HTML--把 JSX 放入 `<script type="text/babel">`，并引入 React UMD + babel-standalone。**默认禁网下无法加载这些 CDN** -> 抛 `RenderError` 降级开环（机制见 §3.5）。
- 视口：`VISION_RENDER_VIEWPORT`（默认 `1280x800`），`device_scale_factor=2` 提高截图清晰度。
- 截图：`page.screenshot(full_page=True)`，返回 PNG bytes。
- 临时文件：`tempfile.TemporaryDirectory()`，`with` 块结束自动清理；截图不落盘。

**浏览器检测**：`is_available()` 先 `import playwright` 成功，再探测 chromium 是否安装（`playwright._impl._driver` 或尝试启动超短超时）。未安装时返回 False 并给出 `playwright install chromium` 提示。

### 3.3 编排器 `vision_mcp/reconstruct.py`

抽出闭环逻辑，`server.py` 只调一行：

```python
def run(config: Config, backend: VisionBackend, images: list[tuple[bytes, str]],
        args: dict, model: str) -> str:
    """Open-loop by default; closed-loop when config.reconstruct_render and
    renderer available. Returns a text report for CallToolResult."""
```

**降级链**：
1. `config.reconstruct_render=false` → 纯开环（当前行为：code + self-check）。
2. `=true` 但 `create_renderer()` 返回 None → 开环 + 结果标注「闭环不可用（未装 playwright/chromium），已降级为开环自检」。
3. `=true` 且 renderer 可用 → 闭环；单次 `render()` 抛 `RenderError` 时该轮降级为开环自检并继续（不让一次渲染失败毁掉整个调用）。

**输出格式**（闭环）：
```
<code>

--- 闭环校验报告 ---
迭代轮数: 2/2
最终评分: 87/100（阈值 85，已达标）
差异: 1. 顶部导航间距偏大; 2. 按钮圆角不一致
渲染状态: 成功
```

**输出格式**（降级开环）：保留现有 SELF-CHECK 段，末尾追加降级说明。

### 3.4 Prompt 扩展 `prompts.py`

新增三个 prompt 构造器（不改动现有 `reconstruct_prompt`，闭环复用它做首轮生成）：

- `compare_render_prompt() -> str`：输入原图 + 渲染截图，要求严格 JSON：
  ```json
  {"match": false, "score": 0, "differences": ["..."], "suggestions": "..."}
  ```
  `score` 为 0-100 整体视觉相似度；`match` 为布尔达标判断。prompt 中提示「忽略截图与原图的尺寸/比例差异，聚焦结构、布局、配色、文字一致性」，避免渲染视口与原图尺寸不同干扰打分。
- `refine_prompt(prev_code: str, verdict: dict) -> str`：把上一轮代码 + 差异反馈喂回，要求输出修正后的完整代码（不附 self-check，因为闭环有真实对比）。
- `reconstruct_prompt` 增加约束：**输出必须是无外部依赖的纯内联 HTML**（禁网渲染前提）；react 格式额外说明「需含 CDN，仅在网络开启时可渲染」。

对比结果 JSON 解析容错：模型可能输出 markdown 包裹的 JSON 或多余文本，用「提取首个 `{...}` 块 + `json.loads`」解析，失败则 `score=-1` 触发继续迭代或降级。

### 3.5 安全：渲染网络策略

| 模式 | 行为 | 适用 |
|---|---|---|
| `VISION_RENDER_ALLOW_NETWORK=false`（默认） | Playwright `route("**", abort)` 拦截所有外网；仅加载本地临时 HTML | html/svg 纯内联渲染 |
| `VISION_RENDER_ALLOW_NETWORK=true` | 允许外网，react CDN 可用 | 用户明确接受风险、需 react 闭环 |

**react 在禁网默认下的行为**：renderer 对 react 用 babel-standalone 内联模板（`<script type="text/babel">` + React UMD + babel-standalone CDN）生成 HTML；禁网下无法加载这些 CDN -> 抛 `RenderError("react 闭环需开网络"）`，编排器降级该轮为开环自检。文档明确，避免用户困惑。

不额外做 JS 沙箱：Playwright 进程级隔离 + 默认禁网已覆盖主要风险；本地 MCP 场景信任模型输出。残留风险（本地文件读取 via `file://`）文档标注，v3 可考虑 `--site-per-process` 加固。

### 3.6 工具入参扩展

`vision_reconstruct` 的 `inputSchema` 新增（全部可选，默认走配置）：
```python
"render": {"type": "boolean", "description": "尝试闭环渲染（默认取 VISION_RECONSTRUCT_RENDER）"},
"iterations": {"type": "integer", "description": "最大迭代轮数（默认取配置）"},
```
`server.py` 的 reconstruct 分支改为调 `reconstruct.run(...)`，不再直接 `backend.analyze`。

### 3.7 配置项

| 变量 | 默认 | 说明 |
|---|---|---|
| `VISION_RECONSTRUCT_RENDER` | `false` | 是否启用闭环渲染（需装 `[render]` extras） |
| `VISION_RECONSTRUCT_MAX_ITERATIONS` | `2` | 首轮后的最大修正轮数 |
| `VISION_RECONSTRUCT_THRESHOLD` | `85` | 停止迭代的相似度分数阈值（0-100） |
| `VISION_RENDER_TIMEOUT` | `30` | 单次渲染超时秒数 |
| `VISION_RENDER_VIEWPORT` | `1280x800` | 渲染视口（宽x高） |
| `VISION_RENDER_ALLOW_NETWORK` | `false` | 渲染时是否允许外网（react CDN 需要） |
| `VISION_RECONSTRUCT_JUDGE_MODEL` | 空 | 对比裁判模型；空则用同模型（v2 可选增强，缓解自检偏差） |

`VISION_RECONSTRUCT_JUDGE_MODEL`：非空时，对比步骤用该模型而非生成模型，缓解评审 P3-8 指出的「同模型自我确认偏差」。默认空（同模型），用户可配一个更强的云端模型仅当裁判。

### 3.8 R2 v2 模块变更

```
vision_mcp/
├── renderer.py        # 新增：Renderer 抽象 + PlaywrightRenderer + is_available
├── reconstruct.py     # 新增：闭环编排器 run()
├── prompts.py         # 扩展：compare_render_prompt + refine_prompt + 内联约束
├── server.py          # 改：reconstruct 分支调 reconstruct.run()
└── config.py          # 扩展：7 个新配置项
tests/
├── test_renderer.py   # 新增：渲染器可用性检测、禁网、viewport、降级
└── test_reconstruct.py # 新增：闭环循环、达标停止、降级链、JSON 解析容错
```

## 4. F2 - npm/PyPI 一键分发

### 4.1 双入口策略

| 入口 | 命令 | 受众 | 实现 |
|---|---|---|---|
| PyPI 主入口 | `uvx shadow-vision` | Python/uv 用户（地道） | PyPI 发布 `shadow-vision` 包 |
| npm 薄壳 | `npx shadow-vision` | Node 生态习惯用户（对齐 luma `npx -y`） | npm 包调 `uvx shadow-vision` |

**核心仍是单一 PyPI 包**，npm 是薄壳包装（依赖用户机器已装 uv）。两个包同名策略：PyPI = `shadow-vision`，npm = `shadow-vision`（避免与 PyPI 名冲突，且贴合项目名）。

### 4.2 PyPI 发布

#### 4.2.1 元数据补全（`pyproject.toml`）

当前 `pyproject.toml` 只有最小元数据。补：
```toml
[project]
name = "shadow-vision"
description = "..."  # 已有
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [{ name = "Ward Lu", email = "wardlu@126.com" }]
keywords = ["mcp", "vision", "ocr", "ollama", "claude", "gemini"]
classifiers = [
    "Development Status :: 4 - Beta",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Scientific/Engineering :: Image Recognition",
]
dependencies = ["mcp>=1.0.0", "httpx[socks]>=0.27.0", "Pillow>=10.0.0"]

[project.urls]
Homepage = "https://github.com/WardLu/shadow-vision"
Repository = "https://github.com/WardLu/shadow-vision"
Issues = "https://github.com/WardLu/shadow-vision/issues"
```

#### 4.2.2 动态版本（单源）

当前静态 `version = "0.1.0"`，与 `vision_mcp/__init__.py` 双源易漂移。改为 hatchling 动态版本：
```toml
[project]
dynamic = ["version"]

[tool.hatch.version]
source = "regex"
path = "vision_mcp/__init__.py"
```
`vision_mcp/__init__.py` 定义 `__version__ = "0.2.0"`（**目标版本，需用户确认**，见 §4.5）。版本变更只改一处。

#### 4.2.3 `__version__` 与 `--version`

- `vision_mcp/__init__.py` 暴露 `__version__`。
- `server.py:main()` 增加最小 CLI：`--version` 打印版本退出；无参数走 MCP 服务。便于发布后验证 `uvx shadow-vision --version`。用 `sys.argv` 简单判断，不引 argparse（保轻量）。

#### 4.2.4 发布 CI（Trusted Publishing）

新增 `.github/workflows/publish-pypi.yml`：
```yaml
name: publish-pypi
on:
  push:
    tags: ["v*"]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv build
      - uses: actions/upload-artifact@v4
        with: { name: dist, path: dist/ }
  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write   # OIDC Trusted Publishing，无需 API token
    steps:
      - uses: actions/download-artifact@v4
        with: { name: dist, path: dist/ }
      - uses: pypa/gh-action-pypi-publish@release/v1
```

**前置（文档说明，非代码）**：在 PyPI 项目后台配置 Trusted Publisher = `WardLu/shadow-vision` + workflow `publish-pypi.yml` + environment `pypi`。

#### 4.2.5 发布前校验

新增 `.github/workflows/release-check.yml`（PR 触发）：
```yaml
- run: uv build
- run: uvx twine check dist/*   # 用 uvx 避免 twine 进 dev deps
- run: uv run python -c "import vision_mcp; print(vision_mcp.__version__)"
```
验证包能构建、元数据合法、`__version__` 可导入。

### 4.3 npm 薄壳包装

新增 `npm/shadow-vision/`：
```
npm/shadow-vision/
├── package.json
├── bin.js
└── README.md
```

`package.json`：
```json
{
  "name": "shadow-vision",
  "version": "0.2.0",
  "description": "Thin wrapper that runs the shadow-vision Python package via uvx.",
  "license": "MIT",
  "repository": { "type": "git", "url": "https://github.com/WardLu/shadow-vision" },
  "bin": { "shadow-vision": "bin.js" },
  "engines": { "node": ">=18" }
}
```

`bin.js`（透传 stdio，MCP 走 stdio）：
```javascript
#!/usr/bin/env node
const { spawn } = require("node:child_process");
const child = spawn("uvx", ["shadow-vision", ...process.argv.slice(2)], {
  stdio: "inherit",
});
child.on("error", (err) => {
  if (err.code === "ENOENT") {
    console.error("shadow-vision requires 'uv' installed. Install: https://docs.astral.sh/uv/");
    process.exit(127);
  }
  throw err;
});
child.on("exit", (code) => process.exit(code ?? 1));
```

`npx shadow-vision` → 调 `uvx shadow-vision`，环境变量透传由用户在 MCP 配置的 `env` 字段提供（与 PyPI 入口一致）。

npm 发布 CI（`.github/workflows/publish-npm.yml`，tag 触发）：
```yaml
- uses: actions/setup-node@v4
  with: { node-version: "22", registry-url: "https://registry.npmjs.org" }
- working-directory: npm/shadow-vision
  run: npm publish --access public   # 薄壳无依赖，无需 npm ci
  env: { NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }} }
```
需配 `NPM_TOKEN` GitHub Secret。**可选增强**：npm 支持 OIDC provenance（`npm publish --provenance`，需 setup-node 配 `id-token: write`），非必须，当前 `NPM_TOKEN` 方案可接受；启用 provenance 可提升包可信度。

### 4.4 文档与版本

#### 4.4.1 README 新增「一键安装」章节

置顶，替代当前「git clone + uv sync」为主入口的写法：
```bash
# 推荐一键运行（免 clone）
uvx shadow-vision
# 或 Node 习惯
npx shadow-vision

# MCP 配置示例
[mcp_servers.vision]
command = "uvx"
args = ["shadow-vision"]
env = { VISION_BACKEND = "ollama", VISION_MODEL = "qwen3-vl:2b" }
```
保留 git clone 方式作为「开发/源码」小节。

#### 4.4.2 CHANGELOG.md 新建

遵循 Keep a Changelog 格式，记录 0.1.0（已发布功能）+ 0.2.0（本批次新增）。用户全局规则要求 Bug/功能变更更新 CHANGELOG。

#### 4.4.3 版本号（需用户确认）

当前 `0.1.0`。本批次 + 批次 1 新增多个功能（向后兼容），按语义化版本属 **MINOR**，建议 `0.2.0`。

> ⚠️ 按用户铁律，版本号升级必须确认。本设计仅建议 `0.2.0`，实现时不擅自改，待用户拍板后**三处一次性同步**：`vision_mcp/__init__.py`（`__version__`）+ `npm/shadow-vision/package.json`（`version`）+ `CHANGELOG.md`（0.2.0 条目），三者必须一致。

### 4.5 F2 模块变更

```
pyproject.toml                       # 改：补元数据 + 动态版本 + urls
vision_mcp/__init__.py               # 改：暴露 __version__
vision_mcp/server.py                 # 改：main() 加 --version
README.md                            # 改：一键安装章节
CHANGELOG.md                         # 新增
.github/workflows/
├── publish-pypi.yml                 # 新增
├── publish-npm.yml                  # 新增
└── release-check.yml                # 新增
npm/shadow-vision/                   # 新增
├── package.json
├── bin.js
└── README.md
tests/test_packaging.py              # 新增：entry + __version__ + 元数据
```

## 5. 测试策略

### 5.1 R2 v2 测试

| 文件 | 覆盖 | 关键用例 |
|---|---|---|
| `test_renderer.py` | 渲染器 | `is_available()` 检测逻辑（mock import 失败/浏览器缺失）、html 渲染返回 PNG bytes、禁网拦截外网请求、viewport 配置生效、react+禁网抛 RenderError |
| `test_reconstruct.py` | 编排器 | 闭环达标即停（mock verdict.score≥阈值）、迭代到上限、`render()` 失败降级开环、renderer 不可用降级、对比 JSON 解析容错、`judge_model` 走不同模型 |

渲染器测试用 mock Playwright（不真装浏览器），验证调用参数与降级路径；真实渲染标 `@pytest.mark.render` 默认跳过。编排器测试全 mock backend + renderer，验证循环逻辑。

### 5.2 F2 测试

| 文件 | 覆盖 | 关键用例 |
|---|---|---|
| `test_packaging.py` | 打包元数据 | `vision_mcp.__version__` 非空、`pyproject.toml` 必填字段齐全、script entry `shadow-vision` 可解析、动态版本与 `__init__.py` 一致 |

CI 层 `release-check.yml` 是更强验证（真实 `uv build` + `twine check`）。npm 包装器逻辑简单（spawn 透传），可选加 `npm/shadow-vision/test.js` 验证 ENOENT 分支，非必须。

## 6. 实施计划

两需求独立，可并行。各分 3 步：

**R2 v2**：
| 步 | 内容 | 验证 |
|---|---|---|
| R-a | `renderer.py` + `is_available` + Playwright 渲染 + 禁网 | `test_renderer.py` 绿 |
| R-b | `reconstruct.py` 编排器 + prompt 扩展 + 降级链 | `test_reconstruct.py` 绿 |
| R-c | `server.py`/`config.py` 接入 + 工具入参 | 手动开环/闭环切换验证 |

**F2**：
| 步 | 内容 | 验证 |
|---|---|---|
| F-a | `pyproject.toml` 元数据 + 动态版本 + `__version__` + `--version` | `test_packaging.py` 绿 + `uv build` 成功 |
| F-b | 三条 CI workflow + npm 薄壳 | `release-check` 在 PR 跑通 |
| F-c | README 一键安装 + CHANGELOG | 文档审查 |

版本号确认后，tag `v0.2.0` 触发发布 CI。

> **实施状态（2026-08-05）**：R-a/R-b/R-c 与 F-a/F-b/F-c 均已完成，`uv run pytest` 全量 89 项通过。
> 新增测试：`test_renderer.py`（10）+ `test_reconstruct.py`（10）+ `test_packaging.py`（5）。
> `uv build` 成功产出 `dist/vision_mcp-0.1.0`（动态版本，wheel 含全部 9 模块）。
> 版本号已确认 `0.2.0`（2026-08-05），`__init__.py` + `package.json` + CHANGELOG 三处同步，`uv build` 产出 `dist/vision_mcp-0.2.0`。

## 7. 风险与取舍

| 风险 | 取舍 | 缓解 |
|---|---|---|
| Playwright 重依赖 | 闭环默认关闭 + `[render]` extras 可选 + 降级开环 | `is_available()` 检测 + 明确提示 `playwright install chromium` |
| 闭环耗时长（分钟级） | `max_iterations` 默认 2 | 文档警示；用户可调小或关 |
| react 闭环需网络 | 默认禁网，react 降级开环 | `VISION_RENDER_ALLOW_NETWORK=true` 显式开启 |
| 同模型对比偏差 | `judge_model` 可配裁判模型 | 默认空，v2 可选增强 |
| 渲染恶意代码 | 默认禁网 + 进程隔离 | 本地 MCP 信任模型输出；v3 可加 site-per-process |
| PyPI Trusted Publishing 需后台配置 | 文档说明前置步骤 | 代码不依赖 token |
| npm 包名占用 | 备选 `@wardlu/shadow-vision` | 发布前查 npm registry |
| npm 包装器依赖 uv | `bin.js` ENOENT 给明确提示 | README 说明前置 |
| 版本号 | 需用户确认 | 设计只建议 0.2.0，不擅自改 |

## 8. 验收标准

**R2 v2**：
- [x] `VISION_RECONSTRUCT_RENDER=false`（默认）时行为与现有一致（开环）
- [x] 装了 `[render]` extras + `=true` 时，html 截图复刻能渲染截图并迭代
- [x] 未装 playwright 时降级开环，结果含降级说明
- [x] `max_iterations=0` 时仅生成+渲染+对比一轮，不迭代
- [x] 渲染默认禁网；react+禁网降级开环
- [x] `test_renderer.py` + `test_reconstruct.py` 全绿

**F2**：
- [ ] `uv build` 产出合法 wheel/sdist（已通过），`twine check` 待发布 CI 验证
- [x] `uvx shadow-vision --version` 打印版本（本地 `uv build` 后验证）
- [ ] `npx shadow-vision` 能调起 `uvx shadow-vision`（需 npm 环境，待发布验证）
- [ ] tag 触发 publish-pypi + publish-npm 两条 CI（workflow 已就位，待真实 tag 验证）
- [x] README 一键安装章节 + CHANGELOG 就位
- [x] 版本号已确认 `0.2.0`（2026-08-05，三处同步：`__init__.py` + `package.json` + CHANGELOG）

## 9. 不在本批次

| 项 | 原因 |
|---|---|
| M1 HTTP/局域网共享模式 | 架构差异大，独立批次 |
| react 闭环构建工具链（vite/webpack） | 过重，v2 用 CDN/降级覆盖 |
| 渲染 JS 沙箱加固（site-per-process） | 默认禁网已覆盖主要风险，留 v3 |
| PyPI/npm 自动版本 bump | 版本铁律要求人工确认，不自动化 |

## 10. 评审结论（2026-08-05）

> 评审人：Codex（核对现有代码扩展点后评审）。
> 结论：**三个关键取舍均可批准，设计整体可以进入实现**；P1/P2/P3 修订点已于 2026-08-05 全部并入正文（见 §3.2/3.4/3.5/4.2.2/4.2.5/4.3/4.4.3）。

### 10.1 关键取舍确认

| 取舍 | 结论 | 依据 |
|---|---|---|
| react 闭环默认降级开环（禁网优先） | ✅ 同意 | react 需 CDN（babel-standalone 转换 JSX），禁网默认下无法加载 → 降级开环自检，显式 `VISION_RENDER_ALLOW_NETWORK=true` 才尝试，安全优先合理 |
| `judge_model` 可选裁判 | ✅ 同意 | 缓解前序评审 P3-8 同模型自检偏差；默认空（同模型）保持零配置，增强项不强制 |
| npm 包名 `shadow-vision` | ✅ 同意 | 避免与 PyPI `vision-mcp` 撞名、贴合项目名；发布前查 npm 占用，备选 `@wardlu/shadow-vision` |

### 10.2 P1 修订点（实现前必须并入）

1. **react 渲染机制未明确**：§3.2 只说「react 需 CDN」，未写明如何把 JSX 渲染为可截图 HTML。**修订**：明确 renderer 对 react 用 babel-standalone 内联模板（`<script type="text/babel">`）包一层生成 HTML，禁网时无法加载 babel → 抛 `RenderError` 降级开环。

### 10.3 P2 修订点

2. **hatchling 动态版本补 `source`**：`[tool.hatch.version] path = "..."` 依赖默认 regex source（通常可行），建议显式 `source = "regex"` 更稳。
3. **`release-check` 用 `uvx twine check`**：避免 twine 进 dev deps（文档已列「或 uvx twine check」，采纳 `uvx`）。
4. **npm 薄壳 `npm ci` 冗余**：无依赖薄壳目录无 `package-lock.json`，`npm ci || true` 可简化；建议薄壳直接 `npm publish` 或补 lock。

### 10.4 P3 细节

5. 渲染截图与原图尺寸不一致可能干扰对比，可选在对比 prompt 提示「忽略尺寸差异、聚焦结构」。
6. npm 发布可选 OIDC/provenance（非必须，`NPM_TOKEN` 方案可接受）。
7. 版本号三处同步（`__init__.py` + `package.json` + CHANGELOG）尊重铁律，需用户拍板 `0.2.0`。

> **2026-08-05 实施变更**：PyPI 包名由 `vision-mcp` 改为 `shadow-vision`（`vision-mcp` 已被他人项目占用，见 §10 评审）；`shadow-vision` 为全新包，首个发布版本定为 **0.1.0**（不再延续 0.2.0）。三处版本同步：`vision_mcp/__init__.py` + `npm/shadow-vision/package.json` + `CHANGELOG.md`。

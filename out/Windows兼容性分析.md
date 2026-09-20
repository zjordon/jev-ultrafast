# Jev Ultrafast Windows 兼容性分析

> 评估环境参考：Windows 10/11 x64 + Python 3.12 + uv。结论先行：**核心 Agent 与本地检查器可在 Windows 正常运行；仅两个演示视频渲染脚本因硬编码 macOS 字体路径无法在 Windows 直接运行**（它们只用于生成 docs 演示媒体，不影响 Agent 功能）。

## 1. 总体结论

| 组件 | Windows 兼容性 | 说明 |
| --- | --- | --- |
| `jev_ultrafast` 核心包（agent/browser/model/questions/snapshot.js） | ✅ 完全兼容 | 纯 Python + 浏览器端 JS，经 CDP 通信，无平台特定 API |
| `demo.py` 本地检查器（`uv run jev`） | ✅ 完全兼容 | 回环 HTTP + 线程锁，Windows 均支持 |
| 依赖 `httpx[http2]` / `browser-harness 0.1.13` | ✅ 兼容 | 全部纯 Python wheel（cdp-use、fetch-use、pillow、websockets 无二进制平台依赖）；需本机 Chrome |
| `tests/` 离线测试 | ✅ 完全兼容 | 全部 mock/纯逻辑，不依赖平台 |
| `scripts/check_guards.py` | ✅ 兼容 | 依赖 browser-harness 连接本机 Chrome，data: URL 启动 |
| `scripts/smoke.py`、`examples/*`、`measure/record_flights.py` | ✅ 兼容 | 正常 Python 脚本（会调付费 API） |
| `scripts/render_demo.py` | ❌ 直接运行失败 | 硬编码 macOS 字体路径 + 依赖外部 ffmpeg |
| `scripts/render_fixture.py` | ❌ 直接运行失败 | 同上 |
| CI/CD、Docker | — | 仓库未包含相关配置，无此项风险 |

## 2. 兼容性良好的证据

### 2.1 路径处理全部使用 pathlib

`browser.py:13` `Path(__file__).with_name("snapshot.js")`、`demo.py:15,24`、`agent.py:5,20` 等均为 `pathlib.Path` 拼接，无手写 `/` 分隔符字符串拼接，Windows 下自动使用 `\`。

### 2.2 平台分支已正确处理 macOS/其他

`browser.py:175,183` 的全选快捷键：

```python
modifiers=4 if sys.platform == "darwin" else 2,   # Cmd(macOS) / Ctrl(Windows/Linux)
```

这是仓库中**唯一**的平台守卫，Windows 走 Ctrl 分支，行为正确。

### 2.3 网络与并发模型 Windows 友好

- `demo.py:134` `ThreadingHTTPServer(("127.0.0.1", PORT), Handler)`：仅回环监听，不触发 Windows 防火墙入站提示（防火墙只拦截非回环绑定）。
- 无 `fork`、无 `signal.SIG*`、无 Unix domain socket、无 `asyncio` 事件循环陷阱；并发只用线程 + 非阻塞锁（`demo.py:111`）。
- Host 头校验 `127.0.0.1:8766`（`demo.py:82`）在 Windows Chrome 上行为一致。

### 2.4 subprocess 使用规范

`render_demo.py:100,122`、`render_fixture.py:36` 均为**列表参数 + 无 shell=True** 调用 `ffmpeg`，路径经 pathlib 转换，Windows 下传参形式正确（前提是 ffmpeg 已装入 PATH）。

### 2.5 依赖栈无平台二进制

`uv.lock` 中 browser-harness 及其依赖（cdp-use 1.4.5、fetch-use、pillow、websockets、httpx）均为 `py3-none-any` 纯 Python wheel；pillow 有 Windows wheel。Browser Harness 通过 CDP WebSocket 连接本机 Chrome，与操作系统无关（官方文档未单独声明 Windows，但其需求仅 Python/uv/git/Chrome；`uv run browser-harness --doctor` 可在 Windows 排查连接）。

### 2.6 时间精度（次要说明）

`time.sleep(0.02)`（browser.py 等待循环）在 Python 3.11+ 的 Windows 实现已使用高分辨率定时器，20ms 级轮询与 50/200ms 交互后等待可正常工作；即便偶有毫秒级抖动，也只是等待上限略宽，不影响正确性。

## 3. 发现的问题与修复建议

### 问题 1（P1）：渲染脚本硬编码 macOS 字体路径

- `scripts/render_demo.py:18-27`：
  ```python
  font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
  font_bold = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
  ...
  return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", n)
  ```
- `scripts/render_fixture.py:16-18`：`font_path = "/System/Library/Fonts/Menlo.ttc"`

Windows 上 `ImageFont.truetype` 找不到该路径会抛 `OSError: cannot open resource`，脚本立即崩溃。这两个脚本用于把**已验证的录制**渲染成 `docs/demo.mp4` / 夹具演示 gif，与 Agent 运行无关；但想在本机复现演示视频就必须改。

**修复建议**（平台感知的字体回退，可直接替换）：

```python
import sys

def find_font(candidates, size):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)

ARIAL = {
    "win32":  [r"C:\Windows\Fonts\arialbd.ttf"],          # bold；普通用 arial.ttf
    "darwin": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "linux":  ["DejaVuSans-Bold.ttf"],                     # fontconfig 名，多数发行版可用
}
MONO = {
    "win32":  [r"C:\Windows\Fonts\consola.ttf"],
    "darwin": ["/System/Library/Fonts/Menlo.ttc"],
    "linux":  ["DejaVuSansMono.ttf"],
}
```

Pillow 在 Windows 上对裸字体名（如 `"arial.ttf"`）也会搜索系统字体目录，可作进一步回退。

### 问题 2（P2）：渲染脚本依赖外部 ffmpeg

`render_demo.py`、`render_fixture.py` 直接 `subprocess.run(["ffmpeg", ...])`。Windows 安装方式：`winget install Gyan.FFmpeg`（或 `choco install ffmpeg`）。核心功能不需要 ffmpeg。

### 问题 3（提示级）：首次 Chrome 远程调试授权

Browser Harness 连接本机 Chrome 时会请求允许远程调试（各平台一致）。Windows 上若 Chrome 由企业策略管理可能禁用 `--remote-debugging-port`，此时 `uv run browser-harness --doctor` 会给出诊断；可备选便携版 Chromium。

### 问题 4（提示级）：仓库自带 `.gitignore` 未含 Windows 产物

`.gitignore` 覆盖 `.env`、`artifacts/`、缓存目录等，无 `Thumbs.db`/`desktop.ini` 等项；仅当在仓库目录内用资源管理器操作时可能产生未跟踪噪音，属洁癖项，不影响构建。

## 4. Windows 安装与验证清单

```powershell
# 1. 安装 uv（已装可跳过）：powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
git clone https://github.com/browser-use/jev-ultrafast.git
cd jev-ultrafast
uv sync
copy .env.example .env      # 填入 TYPESAFE_API_KEY / TEXT_MODEL_API_KEY

# 2. 离线验证（不花钱、不需要 Key）
uv run ruff check .
uv run pytest               # 16+ 离线契约测试应全绿

# 3. 浏览器守卫回归（需要 Chrome，仍零模型调用）
uv run python scripts/check_guards.py

# 4. 启动检查器（需要两个 API Key）
uv run jev                  # 打开 http://127.0.0.1:8766
```

`uv build` 在 Windows 上使用 hatchling 后端，可正常产出 wheel/sdist。

## 5. 结论

该仓库核心代码对 Windows 的兼容性是**经过良好设计 incidental 兼容**：唯一的平台分支（Cmd/Ctrl 全选）已正确覆盖 Windows，路径、并发、网络、依赖栈均无 Unix 假设。唯一实质障碍是演示视频渲染脚本的 macOS 字体硬编码与 ffmpeg 依赖——修复字体解析（约 15 行改动）并安装 ffmpeg 后，Windows 上即可完成从运行 Agent 到复现演示视频的全部流程。

# 动作执行对比 — jev-ultrafast 与 browser-use，及工具层复用评估

> 对比对象：jev-ultrafast 的 `browser.py`（执行层）与 browser-use 的 `actor/` 模块（element.py 1175 行 + mouse.py + page.py）及 `tools/registry` 分发链（基于本地 checkout `D:\dev\git\z_jordon\browser-use` 实测代码）。
> 回答两个问题：①两项目拿到模型决策后执行动作有什么不同；②browser-use 的工具层能否直接用于 jev-ultrafast。
> 关联文档：[全功能浏览器agent可行性分析.md](./全功能浏览器agent可行性分析.md)（B 级难点与演进路线）、[DOM采集方案对比-dom_tree与snapshot.md](./DOM采集方案对比-dom_tree与snapshot.md)（采集侧对比）。

---

## 1. 🔄 两条执行链路

```text
jev-ultrafast：
choice 索引 → validate_choice → targets 表翻译成动作 id
  → fresh 双层守卫（page_key + guard，语义指纹比对）
  → 一次页面内 evaluate：nodes.get(id) 取回真实节点
      → isConnected/disabled/readonly/checkVisibility 复查
      → getBoundingClientRect 即时几何 → elementFromPoint 命中测试
  → Input.dispatchMouseEvent ×2 / selectAll+insertText / select 设值+派发事件
  → 三态异常学（成功 / StalePage / RuntimeError），变更永不重试

browser-use：
LLM 输出动作 JSON → Pydantic 动作模型解析（registry Union）
  → _click_by_index(index) → get_element_by_index → Element 对象（绑 backendNodeId）
  → Element.click()（element.py:93-350）：
      Page.getLayoutMetrics（视口）
      → 几何三级级联：DOM.getContentQuads → DOM.getBoxModel
                     → DOM.resolveNode + Runtime.callFunctionOn(JS getBoundingClientRect)
      → scrollIntoViewIfNeeded → Input.dispatchMouseEvent（"watchdog" 实现）
  → 失败 → error 消息写进对话 → LLM 下一轮看到错误自己决定重试
```

---

## 2. 📊 逐维度差异

| 维度 | jev-ultrafast | browser-use |
|---|---|---|
| **元素身份** | 页内自建 WeakMap 身份表（`window.__jevFast.nodes`，整数 id） | CDP 协议级 `backendNodeId`（AX/DOM 快照原生，跨帧有效） |
| **几何解析** | 一次 evaluate 内 `getBoundingClientRect` + 命中测试，**约 1-3 次往返** | 三方法级联（quads→boxModel→JS rect），一次 click 约 **5-8 次 CDP 往返** |
| **遮挡/可点性** | 执行瞬间 `elementFromPoint` 命中裁决 | 采集期 isTopElement + 执行期 watchdog 检查 |
| **文本输入** | `selectAll` 命令 + `Input.insertText`（一次插入，快） | **键盘事件序列**（fill 内连续 6 次 `dispatchKeyEvent`：focus/全选/清除/输入，慢但更"像人"） |
| **执行前守卫** | fresh 语义指纹先行（page_key+guard） | 无对应概念，靠 index→元素映射 + 失败后反馈 |
| **失败处理** | 三态异常学：StalePage→重观察（只读）；RuntimeError→停（可能已变更）；**变更永不重试** | 失败信息进消息历史，**模型驱动重试**——重试是特性不是缺陷 |
| **事务性** | 决策消费即失效（防双击）+ 写前日志（观察失败不丢动作） | 无此不变量 |
| **异步模型** | 同步（线程 + httpx） | asyncio（cdp-use 客户端），全链 async |
| **动作面** | click/fill/select/scroll/wait 五种 | Element 类 20+ 方法：hover/focus/check/**drag_to**/press/上传/截图/PDF/多标签… |

**最深一层差异是执行责任的哲学**：jev 把执行当"代码的确定性事务"（守卫先行、零重试、写前日志——AGENTS.md "Never retry a browser mutation" 的落实）；browser-use 把执行当"模型可见的尝试"（错误反馈进对话、LLM 自纠）。前者快而脆（守卫失败即停），后者慢而韧（模型可以换姿势再试）。

---

## 3. 🔧 browser-use 工具层能否直接用于 jev-ultrafast

**结论：叶子知识可搬，契约不可搬。** 把"工具层"拆成四层评估：

| 层次 | 能否直接用 | 原因 |
|---|---|---|
| 动作注册表（Pydantic 动作模型 Union） | ❌ 也不需要 | 它是给**生成式模型**的输出 schema；jev 的动作空间是运行时动态构建的 criteria，不走这条解析链 |
| Element 执行类（element.py 整体） | ❌ | 三个硬耦合：①**身份体系不同**——Element 绑 `backendNodeId`，而页面内 JS 拿不到 backendNodeId（CDP 侧概念），jev 的 WeakMap id 是采集与执行的**共享契约**，换执行层 = 采集侧也要跟着改；②**异步模型不同**——全链 async，jev 是同步线程模型；③**前置守卫语义不同**——直接调用会绕过 fresh 语义指纹，退化成失败反馈模式，丢掉零重试不变量 |
| CDP 传输/会话层 | ❌ 各有各的 | jev 用 browser-harness daemon，browser-use 用 cdp-use 直连，平行的连接方案（可并存但不必互换） |
| **具体执行原语** | ✅ **可以搬**，小工作量 | 与身份体系无关的"叶子知识"，见第 4 节清单 |

---

## 4. 📦 可移植原语清单（保持 jev 风格的移植）

| 原语 | 来源 | 移植方式 |
|---|---|---|
| **drag 鼠标序列** | element.py drag_to（pressed→moved→released 三事件） | 翻译进 `browser_operation` 的 act 分支，新增 kind=drag（目标参数化走 fan-out 双头：drag_source/drag_target） |
| **逐键输入序列** | element.py fill 的 6 次 dispatchKeyEvent | 加 fill 的输入模式开关——某些站点只认真实键盘事件不认 insertText |
| **scrollIntoViewIfNeeded** | element.py fill/click 前置 | 候选不在视口内时先滚动再命中测试（jev 目前要求候选必须在视口内） |
| **文件上传** | UploadFileAction → DOM.setFileInputFiles | jev 唯一缺的原生能力：快照解除 file 类型过滤 + 新增 kind=upload + 路径白名单校验 |
| **getContentQuads 几何** | element.py click 的几何级联首选项 | 吸收进执行期 evaluate——quads 处理 inline 折行元素比单 rect 中心点更准 |

移植原则：全部在 jev 自己的"**同步 + 单次 evaluate + 守卫先行 + 零重试**"风格内实现，不引入 Element 类与异步链。

---

## 5. 🏁 结论

1. **jev 缺的不是执行能力，是执行的动作面**——五种基础动作的执行质量（守卫、原子性、事务性）反而是它的强项；
2. browser-use 的执行原语可以逐条移植（上表五项，均为小工作量），且应保持 jev 范式骨架；
3. 整体搬 Element 类不划算：身份契约重写 + 异步桥接 + 放弃守卫体系，等于用工具层便利换掉范式骨架；
4. 与可行性分析的衔接：上表正是其 B 级难点"参数类型系统 + 动作面扩充"的具体实施清单（演进路线第 1 步）。

一句话：**jev 的执行层是"守卫驱动的确定性事务"，browser-use 的执行层是"反馈驱动的模型尝试"——前者的动作面缺口用后者的原语补，后者的鲁棒性思想（几何级联、逐键模拟）也值得吸收，但两者的身份契约与重试哲学不可混搭。**

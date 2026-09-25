# 全功能浏览器 agent 的可行性分析与业界调查

> 本文整理自三轮讨论：①范式理解的精确化；②用该范式实现 browser-use 主项目（本地 checkout：`D:\dev\git\z_jordon\browser-use`）等级产品的可行性分析；③GitHub 与学术界的同类项目/思想调查（2026-09 时点）。
> 关联文档：[agent运行逻辑分析.md](./agent运行逻辑分析.md)（现有内核）、[双模型联动机制.md](./双模型联动机制.md)（协作机制）、[TypeSafe协议交互详解.md](./TypeSafe协议交互详解.md)（通信契约）。

---

## 1. 🎯 范式的精确表述

一句话理解：**每轮循环中，页面快照构建动态索引动作空间 → Jev 用一道多选题定"操作 + 目标" →（仅 TYPE_TEXT 时）文本 LLM 补值 → 代码校验并执行 → 重新观察**。

三个常见误解的校准：

1. **分叉不是两路（点击/选择 vs LLM），是四路**：

| Jev 决策出的操作 | 谁补全参数 | 谁执行 |
|---|---|---|
| CLICK / SELECT | 无人（目标即参数） | 代码（CDP 输入） |
| **TYPE_TEXT** | **文本 LLM 生成值** | 代码（全选 + insertText） |
| SCROLL / WAIT | 无人 | 代码（滚轮 / 睡眠） |
| DONE / BLOCKED | 无人 | 代码（状态迁移，循环终止） |

2. **TYPE_TEXT 时也不是"转给 LLM 处理"**：Jev 决定"在哪填"（操作+目标），LLM 只回答"填什么"（一个字符串）。决策权在 Jev，执行权在代码——LLM 是**参数生成器**，不是子代理。

3. **官方说法是"选择而非生成"**（*"A browser agent that chooses instead of generating"*）：不只是决策在先，而是**把一切尽量翻译成选择题**——点元素是选择、下拉是选摊平后的选项、做没做完是选 DONE/BLOCKED；只有无法出成选择题的（具体文本），才引入生成式 LLM。这是与 ReAct 式 agent（每步自由生成动作）的根本分野。

---

## 2. 🔍 与 browser-use 主项目的动作面对照

对本地 browser-use checkout（较新版本：CDP 直连 `actor/`、Pydantic 动作注册表 `tools/registry/views.py`、`skills/`、`agent/judge.py` 自评）实测扫描，其动作面：

`ExtractAction`、`SearchPageAction`、`FindElementsAction`、`SearchAction`、`NavigateAction`、`ClickElementAction`、`InputTextAction`、`DoneAction`、`StructuredOutputAction`（泛型 T，结构化抽取）、`SwitchTabAction`、`CloseTabAction`、`ScrollAction`、`SendKeysAction`、`UploadFileAction`、`NoParamsAction`（wait/go_back/new_tab…）、`ScreenshotAction`、`SaveAsPdfAction`、`GetDropdownOptionsAction`、`SelectDropdownOptionAction`。

**已被 jev-ultrafast 验证可直接平移的能力**：索引化动作空间（browser-use DOM mode 本来就是）、代码拥有执行（其 `actor/element.py` 同样是 CDP 直取真实元素）、一次请求多决策（fan-out 泛化性好）、新鲜度守卫/写前日志（与协议无关的工程质量）。browser-use 主项目自身也在向该方向收敛（CDP actor、元素索引、skills 化）。

### 2.1 状态获取架构：两条路线的争论与合成方案

**两条路线的实际形态**：

| | browser-use（重装备） | jev-ultrafast（轻装备） |
|---|---|---|
| 采集 | 三源：每帧 AX 树（getFullAXTree）+ DOM 快照树 + computed styles/绘制信息 | 一次 `Runtime.evaluate` 执行 107 行 snapshot.js |
| 过滤 | Python 侧五步：父链可见性 → ClickableElementDetector 交互启发 → PaintOrderRemover 矩形并集去遮挡 → 分页按钮等启发 → 序列化裁剪 | 页面内同步完成：querySelectorAll 筛选 → checkVisibility 原生可见性 → role 白名单 + 名称解析链 |
| 输出 | 全量丰富上下文（服务生成式 LLM） | 有界候选集（≤250 动作 + ≤6000 字符文本，服务分类器） |

**jev 敢简化的六个考虑**：①延迟预算是立项目标（旧版 1,092 次协议调用 → 101 次；Jev 决策中位仅 178ms，采集不能反客为主）；②原子性（单次求值无撕裂，无需跨源 reconciler）；③守卫同源（marker/page_key/guards 同一份快照产出，指纹天然确定）；④消费端适配（choice 协议 ≤255 选项，分类器要"少而干净"）；⑤**严谨性重新分配到执行侧**——browser-use 在采集时保证可点（paint order 去遮挡），jev 在点击瞬间裁决（elementFromPoint 命中测试，几何永远即时，更便宜更准确）；⑥简化是带失败教训迭代出来的（第一个 direct-DOM 候选 8.697s 因名称提取不完整校验失败 → 补全解析链 → 单次求值架构未变）。

**对"信息错 → 决策必错"质疑的回应**：

- "三源五步"≠更准确：ClickableDetector 用类名启发猜交互性、paint order 在 transform/动画下出错、AX+DOM 融合器本身是 bug 面——启发式误过滤是**静默错误**（模型永远看不到被误删的元素，无补救）；jev 的选择器是语法级精确判定，可见性用浏览器原生渲染权威（checkVisibility）。
- 错误传播链有三道防线：执行时裁决（StalePage 拦截，错误输入不变成错误执行）→ 无进展止损（3 步无变化 → blocked）→ 低 confidence 可观测（候选被污染时分布摊平）。
- **质疑真正成立的四个场景**：名称解析盲区（非完整 accname 规范，复杂 ARIA 链解析出空名/错名）；shadow DOM/iframe 缺失（信息缺失 = 错误世界图景，可能误判 BLOCKED）；250 截断（目标元素恰在第 251 位后）；烂 ARIA 页面（**所有 DOM 方案的共同上限**，视觉模型才是补丁——jev 是"默认不用"截图而非抛弃）。

**"JS 方案被证明有性能问题"的史实修正**：early browser-use 的 buildDomTree.js 确实在大页面上栽过跟头，但慢在**算法**不在执行环境——全树遍历（不只交互候选）、逐元素 getBoundingClientRect+getComputedStyle 的 **layout thrashing**、兆级序列化 payload、每步全量重跑；且 `checkVisibility`（Chrome 105+，2022）在它写那版 JS 时还不存在，是时代工具差。**反证：两个项目的迁徙方向相反**（browser-use: JS → CDP 原生树；jev: 读 AX 树 → JS 一次原子读，1,092→101），各自优化成本模型的不同轴：

```text
采集总成本 = 单次采集成本 × 调用次数 × 失效率
               ↑ browser-use 优化           ↑ jev 优化
```

browser-use 转向原生树最硬的理由是**覆盖**而非性能：closed shadow root、跨域 iframe 是页面内 JS 结构性进不去的，AX 树的 accessible name 是浏览器自己的完整规范实现。

**合成方案（全功能版的状态获取）**：

1. **快速路径**：页面内 JS 一次求值（本视口交互候选 + checkVisibility + 有界输出）——jev 现状，保持；
2. **深路径**：CDP `captureSnapshot`/AX 树原生 API 采集 frames/shadow DOM 内容，每步一两次往返，浏览器内算好名字与可见性；
3. 两路合并进**同一份动作空间与身份表**，守卫沿用语义指纹；
4. 吸收两边教训：不重演 buildDomTree 的全量遍历与手工样式查询，也不重演 jev 旧版的重复读与变更失效。

---

## 3. ⛰️ 难点分级

### A 级：结构性难点（choice 范式天生要面对的）

**A1 生成型输出是刚需**：`StructuredOutputAction`/`extract_content` 的交付物就是生成内容。解法是**双流架构**：控制流（做什么）永远走 choice，内容流（产出什么）走 generation、生成物只作为**数据**回流。jev 的 TYPE_TEXT 已示范，需泛化为参数类型系统。

**A2 参数化动作的值域**：

| 动作参数 | choice 范式下的处理 |
|---|---|
| 自由文本 | ✅ 已解（TYPE_TEXT 模式） |
| URL | **可摊平**：页面链接本就是动作空间候选；新 URL 属生成（值生成器+校验） |
| 键序列 | **可摊平**：键位是有限枚举，天然选择题 |
| 文件路径 | 必须生成 + 白名单沙箱（安全敏感） |
| 下拉选项 | ✅ 已解（复合索引 `"5:2"`） |
| 结构化抽取 | 纯生成流（内容输出） |
| drag（源×目标） | 笛卡尔积爆炸 → 两步选择或 **fan-out 扩展（drag_source 头 + drag_target 头）**——多头协议的优势场景 |

**A3 连续坐标交互无解**：canvas 应用（Figma/地图/表格）的坐标本质连续。三条路：快捷键/菜单等价路径（仍可选）、降级为视觉+坐标生成（破坏"模型不产坐标"不变量）、明确不支持。这是范式的硬边界。

### B 级：工程量难点（可解，但贵）

**B1 帧感知动作空间**：jev 的 snapshot.js 明确不进 iframe/shadow DOM；需把 WeakMap 身份表推广为"帧路径+节点 id"复合身份，四层守卫全部跟着复杂化。具体实现按 2.1 的合成方案：快速路径保留页面内 JS，深路径用 CDP 原生树覆盖 frames/shadow DOM。

**B2 255 选项上限 vs 真实页面**：choice 协议单题 ≤255 选项；需**分层动作空间**（视口分区→区域内元素）——两次请求或多层 fan-out；elements×描述的 token 体积膨胀。

**B3 策略规则膨胀**：NEXT_ACTION 12 行管住 Flights；管全 Web 需要规则库。优雅出路：**规则路由本身也做成选择题**（按页面/任务特征从规则库选适用子集）——递归地用范式解决范式的问题。

**B4 恢复与对抗**：登录墙、验证码、cookie 弹窗、网络抖动。与范式正交但产品必需。

### C 级：研究级未知（真正的风险）

**C1 选择器模型的规模化能力未经证明**：jev 在 Flights/Wikipedia 验证过；数百元素、多区域、几十步长任务上的选择准确率与概率校准是开放问题——**范式天花板压在这里**。

**C2 供应商锁定**：choice 协议是 TypeSafe 专有。产品级需抽象层：可用 OpenAI 兼容模型的 **logprobs 自建 choice 协议**（模型输出选项字母、读 logprobs 得分布），但校准质量/成本/速度未验证。

**C3 长程策略层**：plan-execute、跨页记忆。保不变量的做法：生成式规划器产出**子目标文本**作为 state 数据喂给选择器（生成的是"意图"不是"动作"），有效性需实验证明。

---

## 4. 🌍 业界与学术调查（2026-09 时点）

### 4.1 直接同范式：TypeSafe 生态

- **[TypeSafe AI](https://typesafe.ai)**（旧金山 AI lab）：2026-09-15 发布 **System One Models & Jev**——decision-only 模型，返回校准决策/评分/概率分布，从不生成文本；宣称响应 70–500ms、分类任务比前沿 LLM 快 40–200 倍/便宜 400 倍。
- **jev-ultrafast 是该范式的官方旗舰演示**（第三方介绍 Jev 时引用的"7.1 秒订机票"即本仓库）。
- **生态（按周计的婴儿期）**：[LangChain 指南](https://www.langchain.com)、[Pydantic TypeSafeModel](https://pydantic.dev)（输出类型每字段=一个决策）、Firecrawl 指南、LiteLLM 代理、ai-sdk/TanStack provider；内容侧 [dev.to 实战指南](https://dev.to)（6 天前）、[HackerNoon 101 用例](https://hackernoon.com)（2 天前）。
- **GitHub 早期同类**：[pedramamini 的 jev 包装器](https://gist.github.com/pedramamini/014676fa8684d91bf7000f4623701ada)、[kofanlabs 的 Jev Computer Use MCP](https://glama.ai/mcp/servers/kofanlabs/typesafe-computer-use-windows)（**范式已外溢到 Windows 桌面自动化**）、lukstei/slop-grader 等。
- **关键空白：没有任何 star 数可观的、Jev 驱动的全功能浏览器 agent**。

### 4.2 学术血统：索引动作空间有先例，"校准选择"没有

| 工作 | 贡献 | 关系 |
|---|---|---|
| [Mind2Web](https://osu-nlp-group.github.io/Mind2Web/)（NeurIPS 2023） | 首个通用 Web agent 数据集（2350 任务/137 站点），LLM 在索引化候选元素中挑动作 | 索引动作空间的思想源头 |
| [WebArena](https://webarena.dev)（2023） | 可自建基准，复合离散动作空间 | 离散动作空间基准化 |
| 结构化输出运动（OpenAI structured outputs、outlines/SGLang 约束解码） | "typed actions + 参数自动校验"（[AI Agent Systems 综述 arXiv 2601.01743](https://arxiv.org/html/2601.01743v1)） | 范式搭乘的大趋势 |

**文献空白**：未检索到组合"校准概率分布的选择模型 + web agent"的论文——交叉点只有工业实现，无学术正主（可发表论文/benchmark 的题目，如在 WebArena 上对照生成式 vs 选择式决策）。

### 4.3 平行动向：同一诊断，相反的处方

[ICML 2026 立场论文](https://icml.cc/virtual/2026/events/2026-position-papers) *"Web Agents Should Use Typed Actions Instead of Click-Based Browsing"*（Jiang, Xi, Liu, Chen, Lin, Nath）：

- **诊断相同**：低级原语（点击/键击/DOM 操作）导致脆弱、昂贵、难审计；
- **处方相反**：改**网站侧**——网站暴露语义化 typed actions（"Web Verbs"，带前置/后置条件、策略标签、日志钩子），agent 编写可验证的程序组合动词；不涉及概率分布。

即 **Web Verbs 改造环境接口，Jev 范式改造决策机制**——互补而非竞争。另 [SoK: The Attack Surface of Agentic AI](https://arxiv.org)（2603.22928）从安全角度主张 typed actions + schema 校验，与 jev"模型输出永不成为代码"同频。

### 4.4 近邻但不同范式

browser-use、Skyvern、UI-TARS（字节）、Claude Computer Use、OpenAI Operator：均为**结构化生成**（模型生成动作 JSON、框架解析校验）。与 jev 范式的本质差异：无校准分布（无法度量不确定性）、无投机多头（操作+目标一次往返）、模型输出是结构化文本而非纯选择。

---

## 5. 🛤️ 演进路线建议（如果要动手）

1. 保留 jev 内核，泛化**参数类型系统**（每类参数一个"值生成器+校验器"接口：text/url/enum/file/structured）；
2. **分层动作空间**（两级选择，或多层 fan-out）；
3. **帧感知快照**：按 2.1 合成方案实现——快速路径保留页面内 JS，深路径用 CDP `captureSnapshot`/AX 树覆盖 frames/shadow DOM，合并进同一动作空间与身份表；
4. **双流架构定型**：控制流=choice，内容流=generation-as-data；
5. **规则库 + 规则路由**（规则选择本身是 choice）；
6. **choice provider 抽象**（TypeSafe | logprobs 模拟，消除锁定）；
7. 拿 browser-use 的测试集做回归对照。

---

## 📊 结论

| 判断 | 依据 |
|------|------|
| 技术可行 | 内核能力已被 jev-ultrafast 验证；browser-use 主项目自身在收敛（CDP actor、索引元素） |
| 架构是强项 | 四路路由/双流架构/分层动作空间均有清晰设计路径 |
| 天花板在模型 | C1 选择器规模化能力是唯一决定性风险 |
| 覆盖面有硬边界 | A3 连续坐标（canvas/地图）范式内无解 |
| 市场窗口开着 | Jev 2026-09-15 发布，生态以 gist/MCP/小仓库为主；"全功能 choice-based browser agent"无占位者 |
| 学术空白 | "校准选择 + web agent"无论文先例，可做 benchmark/论文贡献 |

**一句话**：范式做全功能浏览器 agent 可行且是行业演化方向之一；真正的赌注不在架构而在**分类器模型的规模化智能**（决定天花板）与**canvas 边界**（决定覆盖面）；时间窗口方面，范式发布一周余、生态空白，是切入的好时机。

---

## 📚 Sources

- [TypeSafe AI](https://typesafe.ai) · [LangChain Jev 指南](https://www.langchain.com) · [dev.to Jev 实战指南](https://dev.to) · [HackerNoon 101 Jev 用例](https://hackernoon.com)
- [ICML 2026 Position Papers](https://icml.cc/virtual/2026/events/2026-position-papers)
- [Mind2Web](https://osu-nlp-group.github.io/Mind2Web/) · [WebArena](https://webarena.dev) · [AI Agent Systems 综述 (arXiv 2601.01743)](https://arxiv.org/html/2601.01743v1)
- [pedramamini/jev gist](https://gist.github.com/pedramamini/014676fa8684d91bf7000f4623701ada) · [kofanlabs Jev Computer Use MCP](https://glama.ai/mcp/servers/kofanlabs/typesafe-computer-use-windows)

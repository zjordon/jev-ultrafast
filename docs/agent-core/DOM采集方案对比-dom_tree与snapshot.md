# DOM 采集方案对比 — browser-use dom_tree（1745 行）vs jev snapshot.js（107 行）

> 对比对象：
> ① `D:\dev\git\z_jordon\ai-agent\page-agent\packages\page-controller\src\dom\dom_tree\index.js`——browser-use 0.5.9（commit d51b6e73）dom_tree 的移植改良版，含 17 处 `@edit` 本地改进；
> ② `jev_ultrafast/snapshot.js`——jev-ultrafast 的观察契约。
> 关联：[全功能浏览器agent可行性分析.md](./全功能浏览器agent可行性分析.md) 2.1 节（两条路线与合成方案）、[snapshot观察契约职责.md](./类的职责/snapshot观察契约职责.md)。

---

## 1. 🎯 先回答核心问题：功能完全相同吗？

**不相同。两者只有约 30% 的功能交集，其余是为不同"下游消费者"服务的不同产品。**

| | dom_tree/index.js | snapshot.js |
|---|---|---|
| 下游消费者 | **生成式 LLM**（读页面树、自己挑元素、输出里引用 highlightIndex） | **分类器 Jev**（在动作空间里做选择题） |
| 输出形态 | **全页面结构树**（rootId + DOM_HASH_MAP：节点含标签/全部属性/父子关系/文本节点/isVisible/isTopElement/isInteractive 标志） | **扁平动作列表**（fill/click/select 语义 + 当前值 + 指纹材料 + 控制动作） |
| 产品定位 | "给模型的阅读材料"——结构、文本、属性俱全，Python 侧还要二次序列化/过滤 | "给模型的选择题卷面"——输出即动作空间，Python 侧零再加工 |

**功能交集**：交互元素发现、可见性过滤、视口过滤、索引编号、（改良版新增的）直接 DOM 引用。

**各自独有**（见第 3 节对照表）：dom_tree 独有高亮系统/iframe/shadow/富文本/嵌套滚动/遮挡检测；snapshot.js 独有动作语义（kind/选项摊平/控制动作）/守卫指纹材料/值状态精选。

---

## 2. 🔬 dom_tree 的 1745 行花在哪（模块分解）

| 模块 | 行区间 | 约行数 | 职责 |
|---|---|---:|---|
| 头注释/参数/extraData | L1-141 | 140 | 来源声明、17 处 @edit 清单、黑白名单注入、附加数据 WeakMap |
| **高亮系统** | L144-426 | **283** | 页面内画覆盖层：按索引配色、标签定位、iframe 偏移补偿、滚动/resize 节流重定位（60fps）、清理函数 |
| 缓存层 | L60-133 | 74 | boundingRects/clientRects/computedStyles 三类 WeakMap 缓存（因重复查询多而必须） |
| XPath 生成 | L428-480 | 53 | 历史遗留（改良版已用 `@edit no need for xpath` 删除调用） |
| 嵌套滚动检测 | L483-556 | 74 | `@edit` 新增：检测 overflow/scrollbar 信号的滚动容器，返回四方向剩余距离 |
| 可见性检查 | L558-688 | 131 | 文本节点用 Range.getClientRects + 视口 + 父级 checkVisibility；元素用 offsetWidth/Height + computedStyle 手工判定 |
| **交互性判定** | L690-958 | **269** | 启发式核心：27 种 cursor 样式（"Genius fix"）、交互标签集、disabled/readonly/inert、类名启发（button/dropdown-toggle）、17 种 ARIA role、getEventListeners（仅 DevTools 可用，带 on* 属性回退）、scrollable 即交互 |
| 遮挡/视口检查 | L960-1113 | 154 | isTopElement：elementFromPoint 中心+两角多点命中、shadow root 感知；viewportExpansion（-1 = 全页模式） |
| 候选/嵌套去重 | L1115-1462 | 348 | isInteractiveCandidate 快速路径、isHeuristicallyInteractive（类名正则 `btn|clickable|menu|item|entry|link`）、isElementDistinctInteraction（交互父元素内的子元素算不算独立动作）、handleHighlighting（分配索引） |
| **递归遍历器** | L1464-1737 | **274** | buildDomTree：全 DOM 深度遍历；特判 body/文本节点/iframe（进 contentDocument）/contenteditable+TinyMCE/shadowRoot（进 node.shadowRoot）；跳过高亮容器/data-browser-use-ignore/aria-hidden |

可见行数大头是三块：**高亮 283 行、交互启发 269 行、嵌套去重 348 行**——而这三块在 snapshot.js 里分别被"移出 JS"“语法白名单消解”“不需要”处理掉了（见第 4 节）。

---

## 3. 📊 逐维度对照

| 维度 | dom_tree（0.5.9 改良版） | snapshot.js | 胜负判断 |
|---|---|---|---|
| 遍历方式 | 全 DOM 递归（每个元素+文本节点） | `querySelectorAll` 只取交互候选 | 各取所需：结构树必须全遍历；动作空间直取 |
| 交互性判定 | 269 行启发式（cursor/类名/事件/ARIA 堆叠） | 选择器白名单 + 15 role——是"匹配"不是"判定" | 哲学分歧：**高召回启发式 vs 高精度语法** |
| 可见性 | 手工算（offsetWidth/computedStyle/Range rects + 缓存防抖） | `checkVisibility` 原生 API | snapshot 胜（时代工具差） |
| 遮挡 | **采集时** elementFromPoint 多点检测 | 不查，**执行时**命中测试 | 各有代价：前者贵且时点早，后者省但候选可能点不到 |
| 视口 | viewportExpansion 参数化（-1=全页） | 中心点视口判定 | dom_tree 更灵活 |
| iframe | ✅ 递归进 contentDocument（跨源会 catch 失败） | ❌ | dom_tree 胜 |
| shadow DOM | ✅ 递归进 shadowRoot | ❌ | dom_tree 胜 |
| 富文本编辑器 | ✅ contenteditable/TinyMCE 特判 | 仅整体 fill | dom_tree 胜 |
| 嵌套滚动 | ✅ 检测容器+四方向距离（@edit） | ❌ 仅页面级固定 560px | dom_tree 胜 |
| 高亮标注 | ✅ 283 行 in-page 覆盖层 | ❌（截图不进模型，无需标注） | 场景决定 |
| 值/状态采集 | attributes 全量 + checked workaround（@edit） | role/value/checked/selected **精选** + select 选项摊平 | snapshot 胜（喂分类器正合适） |
| 动作语义 | ❌ 无（只标注 isInteractive，执行在 Python 侧） | ✅ kind=fill/click/select、选项复合索引、scroll/wait 控制动作内建 | snapshot 胜（输出即动作空间） |
| 新鲜度/守卫 | ❌ 无（新鲜度交给 Python 侧） | ✅ marker/pageKey/guard 同源产出 | snapshot 胜（守卫一致性） |
| 节点身份 | 递增 id + DOM_HASH_MAP + **ref 直引（@edit）** | WeakMap/Map 身份表（原生设计） | 殊途同归（改良版正是向这个方向改） |
| 输出体积 | 全树（大） | 有界（250 动作/6000 字符） | snapshot 胜（choice ≤255 选项） |
| 单次执行成本 | 高（全遍历+多点命中+缓存仍重） | 低（单遍选择器） | snapshot 胜 |

---

## 4. 🧩 行数差异的本质：不是代码质量差，是五个决定

1. **服务对象不同 → 遍历哲学不同**。生成式模型需要读懂页面结构（父子/文本/属性），必须全遍历且保结构；分类器只需要"哪些可执行+当前值"，选择器直取即可。**树 vs 列表**这一步就决定了 274 行遍历器 vs 15 行枚举。

2. **"交互性"是难题还是非题**。dom_tree 把"这个 div 可不可点"当核心难题，堆了 269 行启发式（cursor 样式、类名、事件监听、嵌套去重 348 行辅助）——因为生成式模型面对任意元素，召回率就是能力上限。snapshot.js 用显式白名单把问题变成**语法匹配**：匹配就是支持，不匹配就是不存在——宁漏勿猜（漏了还有 scroll/WAIT 逃生）。**三块行数大头（高亮 283 + 启发 269 + 去重 348 ≈ 900 行）在这一步被整体消解。**

3. **时代工具差**。dom_tree 时代（0.5.9）没有 `checkVisibility`，只能手工算可见性并配缓存防 layout thrashing；snapshot.js 直接用原生 API，131 行的可见性模块变成 2 行。

4. **三样东西被移出了 JS**：高亮（jev 截图不进模型，检查器标注是渲染期叠加）；遮挡检测（移到执行瞬间，几何永远即时）；新鲜度（交给自己的语义指纹+守卫体系，不依赖 DOM 树标志位）。

5. **执行语义内建 vs 外置**。snapshot.js 的输出直接就是动作空间（含 select 选项摊平这种"把交互形态翻译成选择题"的设计）；dom_tree 只产出"这是交互的"标志，执行完全在 Python/Playwright 侧。

---

## 5. ✨ 改良版 @edit 的亮点（与 jev 的暗合）

移植者加的 17 处改进里有几个特别值得注意——它们与 jev-ultrafast 的原生设计**殊途同归**：

| @edit | 内容 | 与 jev 的对应 |
|---|---|---|
| `direct dom ref` | `nodeData.ref = node` 直接持引用 | 正是 snapshot.js 的 `nodes` Map 身份表——两边独立演化到同一方案 |
| `no need for xpath` | 删除 XPath 生成 | jev 从未有过——直接引用取代选择器是共同方向 |
| `scrollable element detection` | 检测嵌套滚动容器 + 四方向距离 | jev 未做（硬编码页面滚动）——**这是值得抄回 jev 的** |
| `@workaround input.checked` | checkbox/radio 的 checked 属性序列化 | jev 的 `base.checked=String(e.checked)` 同一坑的两种填法 |
| `exclude aria-hidden elements` | 剪枝 aria-hidden 子树 | jev 的 `visible()` 谓词同款 |
| `interactiveBlacklist/Whitelist` | 调用方注入元素级例外 | jev 无此机制——可扩展性设计 |

---

## 6. 🏁 结论与杂交建议

**结论**：两份代码不是同一功能的两种实现，而是**同一问题（页面状态采集）在两种 agent 范式下的不同投影**。1745 行 vs 107 行的差距 = 结构树需求（全遍历/保属性/启发式召回）+ 高亮基础设施 + 前原生 API 时代的可见性计算；107 行的底气 = 分类器只要干净候选 + 白名单消解判定难题 + 原生 API + 守卫/执行语义一体化。

**若做全功能版（呼应可行性分析 2.1 合成方案），两者的杂交点**：

1. 遍历骨架抄 dom_tree：iframe（contentDocument 递归 + catch）与 shadowRoot 递归是现成的、正确的写法；
2. 嵌套滚动检测（@edit 版）直接移植，替换 jev 硬编码的 560px 页面滚动；
3. 交互判定仍用 snapshot 的白名单哲学，但把 dom_tree 的 role 集做并集扩充（如 slider、listbox/treeitem）；
4. 高亮系统不要（除非恢复截图驱动模式）；
5. 遮挡检测留在执行侧（jev 现状），但可把 dom_tree 的"多点命中"（中心+两角）吸收进执行期命中测试，减少异形元素误拒。

一句话：**dom_tree 是"给读模型的百科全书"，snapshot.js 是"给选模型的考卷"——前者教你怎么覆盖整个 Web，后者教你怎么把一次求值做到极致；全功能版需要的是两者的骨架与灵魂各取一半。**

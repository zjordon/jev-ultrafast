# DOM 采集产出对比

- 页面：抖音创作者中心
- URL：https://creator.douyin.com/creator-micro/content/upload
- Chrome target：21AEF166B9018043179CC6E8A7C89D85
- dom_tree 参数：doHighlightElements=False，viewportExpansion=0
- 采集时间：2026-09-25 11:14:17

> 注意：doHighlightElements=false 时 dom_tree 不做 in-page 高亮，
> 此时父级未标记为 highlighted，嵌套交互去重（isElementDistinctInteraction）不生效，
> 每个视口内交互候选都会拿到 highlightIndex——这是 browser-use 无高亮模式的原生行为。

## 总体对比

| 指标 | snapshot.js | dom_tree |
| --- | ---: | ---: |
| 文件大小 | 9,136 B | 50,901 B |
| 产出形态 | 扁平动作列表（15 条动作） | 全页面节点树（182 个节点） |
| 文本 | 单一 text 字段（274 字符） | 28 个独立 TEXT_NODE |
| 元素/交互 | 13 个索引元素 | 154 元素节点 |
| 交互判定 | —（白名单即动作） | 66 isInteractive / 123 isTopElement |
| 可执行候选 | 15 动作（{'click': 13, 'scroll': 1, 'wait': 1}） | 66 个 highlightIndex |
| 值与状态 | 每动作带 value/checked/selected | 全量 attributes + extra |
| 指纹材料 | marker/page_key/guards | 无（新鲜度交给 Python 侧） |

## snapshot.js 产出摘要（前 30 条动作）

| # | id | kind | label | value |
| --- | --- | --- | --- | --- |
| 1 | e1 | click | 作品发布 |  |
| 2 | e2 | click | 首页 | 0 |
| 3 | e3 | click | 内容管理 | 0 |
| 4 | e4 | click | 数据中心 | 0 |
| 5 | e5 | click | 收入变现 | 0 |
| 6 | e6 | click | 创作服务 |  |
| 7 | e7 | click | 首页 |  |
| 8 | e8 | click | AI分身 |  |
| 9 | e9 | click | 随变 |  |
| 10 | e10 | click | 世界书 |  |
| 11 | e11 | click | AI工坊 |  |
| 12 | e12 | click | 了解上传规则详情 |  |
| 13 | e13 | click | 上传 视频 |  |
| 14 | scroll_down | scroll | Scroll down |  |
| 15 | wait | wait | Wait for the page to update |  |

元素表（13 项，供 TypeSafe 候选）：[1] 作品发布, [2] 首页, [3] 内容管理, [4] 数据中心, [5] 收入变现, [6] 创作服务, [7] 首页, [8] AI分身, [9] 随变, [10] 世界书, [11] AI工坊, [12] 了解上传规则详情…

## dom_tree 产出摘要（前 30 个 highlightIndex 节点）

| idx | tag | 关键属性 | 直接文本 |
| --- | --- | --- | --- |
| 0 | button | type=button |  |
| 1 | span |  |  |
| 2 | span | role=img |  |
| 3 | div |  |  |
| 4 | span | id=douyin-creator-master-side-upload | 作品发布 |
| 5 | span | role=img |  |
| 6 | ul | role=menu |  |
| 7 | li | id=douyin-creator-master-menu-nav-home; role=menuitem |  |
| 8 | i |  |  |
| 9 | span | role=img |  |
| 10 | span |  | 首页 |
| 11 | li | id=douyin-creator-master-menu-nav-content; role=menuitem |  |
| 12 | i |  |  |
| 13 | span | role=img |  |
| 14 | span |  | 内容管理 |
| 15 | li | id=douyin-creator-master-menu-nav-data-cent; role=menuitem |  |
| 16 | i |  |  |
| 17 | span | role=img |  |
| 18 | span |  | 数据中心 |
| 19 | li | id=douyin-creator-master-menu-nav-cash; role=menuitem |  |
| 20 | i |  |  |
| 21 | span | role=img |  |
| 22 | span |  | 收入变现 |
| 23 | li | id=douyin-creator-master-menu-nav-creative_ |  |
| 24 | div | role=menuitem |  |
| 25 | div |  |  |
| 26 | i |  |  |
| 27 | span | role=img |  |
| 28 | span |  | 创作服务 |
| 29 | i |  |  |

## 如何阅读两个文件

- `snapshot.json`：顶层是 `actions/text/marker/page_key/guards`；`actions` 即动作空间，
  Python 侧直接消费（action_space/choose/执行）。
- `dom_tree.json`：顶层是 `{rootId, map}`；`map` 的键是节点 id，值含 `tagName/attributes/children`，
  交互节点带 `isInteractive/isTopElement/highlightIndex` 标志——它是给 LLM 读的结构树，
  还需要 Python/LLM 二次加工才能变成动作。

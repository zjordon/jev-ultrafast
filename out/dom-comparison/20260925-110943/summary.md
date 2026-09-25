# DOM 采集产出对比

- 页面：Find Cheap Flights Worldwide & Book Your Ticket - Google Flights
- URL：https://www.google.com/travel/flights?hl=en
- Chrome target：21AEF166B9018043179CC6E8A7C89D85
- dom_tree 参数：doHighlightElements=False，viewportExpansion=0
- 采集时间：2026-09-25 11:09:43

> 注意：doHighlightElements=false 时 dom_tree 不做 in-page 高亮，
> 此时父级未标记为 highlighted，嵌套交互去重（isElementDistinctInteraction）不生效，
> 每个视口内交互候选都会拿到 highlightIndex——这是 browser-use 无高亮模式的原生行为。

## 总体对比

| 指标 | snapshot.js | dom_tree |
| --- | ---: | ---: |
| 文件大小 | 15,421 B | 207,360 B |
| 产出形态 | 扁平动作列表（26 条动作） | 全页面节点树（996 个节点） |
| 文本 | 单一 text 字段（256 字符） | 197 个独立 TEXT_NODE |
| 元素/交互 | 20 个索引元素 | 799 元素节点 |
| 交互判定 | —（白名单即动作） | 20 isInteractive / 131 isTopElement |
| 可执行候选 | 26 动作（{'click': 20, 'fill': 4, 'scroll': 1, 'wait': 1}） | 20 个 highlightIndex |
| 值与状态 | 每动作带 value/checked/selected | 全量 attributes + extra |
| 指纹材料 | marker/page_key/guards | 无（新鲜度交给 Python 侧） |

## snapshot.js 产出摘要（前 30 条动作）

| # | id | kind | label | value |
| --- | --- | --- | --- | --- |
| 1 | e1 | click | Main menu |  |
| 2 | e2 | click | Google |  |
| 3 | e3 | click | Skip to main content |  |
| 4 | e4 | click | Accessibility feedback |  |
| 5 | e5 | click | Explore |  |
| 6 | e6 | click | Flights |  |
| 7 | e7 | click | Hotels |  |
| 8 | e8 | click | Vacation rentals |  |
| 9 | e9 | click | Change appearance |  |
| 10 | e10 | click | Google apps |  |
| 11 | e11 | click | Sign in |  |
| 12 | e12 | click | Change ticket type. Round trip | Round trip |
| 13 | e13 | click | 1 passenger, change number of passengers. |  |
| 14 | e14 | click | Change seating class. Economy | Economy |
| 15 | e15 | fill | Where from?  |  |
| 16 | e16 | click | Open Where from?  |  |
| 17 | e17 | fill | Where to?  |  |
| 18 | e18 | click | Open Where to?  |  |
| 19 | e19 | fill | Departure |  |
| 20 | e20 | click | Open Departure |  |
| 21 | e21 | fill | Return |  |
| 22 | e22 | click | Open Return |  |
| 23 | e23 | click | Search for flights |  |
| 24 | e24 | click | Explore deals with AI |  |
| 25 | scroll_down | scroll | Scroll down |  |
| 26 | wait | wait | Wait for the page to update |  |

元素表（20 项，供 TypeSafe 候选）：[1] Main menu, [2] Google, [3] Skip to main content, [4] Accessibility feedback, [5] Explore, [6] Flights, [7] Hotels, [8] Vacation rentals, [9] Change appearance, [10] Google apps, [11] Sign in, [12] Change ticket type. Round trip…

## dom_tree 产出摘要（前 30 个 highlightIndex 节点）

| idx | tag | 关键属性 | 直接文本 |
| --- | --- | --- | --- |
| 0 | div | role=button; aria-label=Main menu |  |
| 1 | a | aria-label=Google; href=/ |  |
| 2 | button | id=18; role=link |  |
| 3 | button | id=7; role=link |  |
| 4 | button | id=8; role=link |  |
| 5 | button | id=14; role=link |  |
| 6 | button | aria-label=Change appearance |  |
| 7 | a | role=button; aria-label=Google apps; href=https://www.google.cn/intl/en/about/prod |  |
| 8 | a | aria-label=Sign in; href=https://accounts.google.com/ServiceLogin |  |
| 9 | div | role=combobox |  |
| 10 | div |  |  |
| 11 | button | aria-label=1 passenger, change number of passengers |  |
| 12 | div | role=combobox |  |
| 13 | div |  |  |
| 14 | input | type=text; role=combobox; aria-label=Where from? ; placeholder=Where from? |  |
| 15 | input | type=text; role=combobox; aria-label=Where to? ; placeholder=Where to? |  |
| 16 | input | type=text; aria-label=Departure; placeholder=Departure |  |
| 17 | input | type=text; aria-label=Return; placeholder=Return |  |
| 18 | button | aria-label=Search for flights |  |
| 19 | button |  |  |

## 如何阅读两个文件

- `snapshot.json`：顶层是 `actions/text/marker/page_key/guards`；`actions` 即动作空间，
  Python 侧直接消费（action_space/choose/执行）。
- `dom_tree.json`：顶层是 `{rootId, map}`；`map` 的键是节点 id，值含 `tagName/attributes/children`，
  交互节点带 `isInteractive/isTopElement/highlightIndex` 标志——它是给 LLM 读的结构树，
  还需要 Python/LLM 二次加工才能变成动作。

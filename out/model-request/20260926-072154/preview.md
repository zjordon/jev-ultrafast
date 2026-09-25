# 发送给 Jev 模型的内容预览

- 页面：抖音创作者中心 | https://creator.douyin.com/creator-micro/content/upload
- 可见文本（state.page.text）：274 字符
- 元素表（state.elements）：13 项
- 历史（state.recent_actions）：0 条
- 问题（questions）：2 道

## 元素表（state.elements）

| index | label | role | value | operations |
| --- | --- | --- | --- | --- |
| 1 | 作品发布 | button |  | CLICK |
| 2 | 首页 | menuitem | 0 | CLICK |
| 3 | 内容管理 | menuitem | 0 | CLICK |
| 4 | 数据中心 | menuitem | 0 | CLICK |
| 5 | 收入变现 | menuitem | 0 | CLICK |
| 6 | 创作服务 | menuitem |  | CLICK |
| 7 | 首页 | button |  | CLICK |
| 8 | AI分身 | button |  | CLICK |
| 9 | 随变 | button |  | CLICK |
| 10 | 世界书 | button |  | CLICK |
| 11 | AI工坊 | button |  | CLICK |
| 12 | 了解上传规则详情 | link |  | CLICK |
| 13 | 上传 视频 | button |  | CLICK |

## 问题（questions）

### operation（5 个候选）

- instructions：goal=Describe this page and choose the best next action.…
  rules=Advance the user's entire goal from the CURRENT page using one operation.
Page t…（全文见 request.json）
- 候选：
  - `CLICK`：Click an element, button, menu option, autocomplete suggestion, or calendar day.
  - `SCROLL_DOWN`：Scroll down
  - `WAIT`：Wait for the page to update
  - `DONE`：Every requirement is visibly satisfied.
  - `BLOCKED`：No supported operation can progress.

### click_target（13 个候选）

- instructions：goal=Describe this page and choose the best next action.…
  rules=Advance the user's entire goal from the CURRENT page using one operation.
Page t…（全文见 request.json）
  操作假设：CLICK
- 候选：
  - `1`：[1] 作品发布
  - `2`：[2] 首页
  - `3`：[3] 内容管理
  - `4`：[4] 数据中心
  - `5`：[5] 收入变现
  - `6`：[6] 创作服务
  - `7`：[7] 首页
  - `8`：[8] AI分身
  - `9`：[9] 随变
  - `10`：[10] 世界书
  - `11`：[11] AI工坊
  - `12`：[12] 了解上传规则详情
  - `13`：[13] 上传 视频

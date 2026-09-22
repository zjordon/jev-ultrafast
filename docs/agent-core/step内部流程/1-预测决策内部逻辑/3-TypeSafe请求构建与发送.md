## `TypeSafe 请求构建与发送` 方法逻辑梳理

### 📋 **方法作用**

把动作空间、页面状态与目标组装为**一次** TypeSafe 多头请求（操作头 + 每操作一个目标头），经 `post_json` 发送——"两个决策，一次网络往返"的实现现场。

> 源码: model.py 第 81-119 行（`choose` 前半）+ 第 15-27 行（`post_json`）+ 第 12 行（全局 CLIENT）

---

### 🔄 **主要逻辑流程**

#### **1️⃣ 操作头候选（第 83-90 行）**

```python
labels = {"CLICK": "点击说明…", "TYPE_TEXT": "输入说明…", "SELECT": "下拉说明…"}
operations = {key: labels[key] for key in targets}          # 仅含存在目标的操作
operations.update({key: value["label"] for key, value in controls.items()})
operations.update(DONE="Every requirement is visibly satisfied.",
                  BLOCKED="No supported operation can progress.")
```

- 候选随页面动态增减：没有可编辑字段时 TYPE_TEXT 根本不出现。

#### **2️⃣ 目标头构建（第 91-106 行）**

```python
for operation, candidates in targets.items():
    questions[operation.lower() + "_target"] = {
        "type": "choice",
        "criteria": {index: {"element": f"[{index}] {a['label']}",
                             "current_value": a.get("current_value", a.get("value", "")),
                             **{k: a[k] for k in ("role", "checked", "selected", "expanded") if k in a}}
                    for index, a in candidates.items()},
        "instructions": {"goal": goal, "operation": operation, "rules": [NEXT_ACTION, TARGET]},
    }
```

**关键参数说明：**
| 参数 | 说明 |
|------|------|
| `criteria` | 仅该操作兼容的候选；附当前值/选中态（questions.TARGET 规则用其避免重复填同值） |
| `rules` | 目标头拿**全部**下一步规则 + TARGET 规则（测试断言 `NEXT_ACTION in rules`） |
| `operation` 字段 | 目标头不知道操作答案，题目显式声明自己假设的操作 |

#### **3️⃣ 请求体（第 107-117 行）**

```python
body = {
    "model": os.environ.get("TYPESAFE_MODEL", "jev-latest"),
    "state": {"page": {k: state[k] for k in ("url", "title", "text")},
              "elements": elements,
              "recent_actions": [{...} for h in history[-10:]]},
    "questions": questions,
}
```

- 页面文本即 snapshot 的 6000 字符可见文本；历史只带 4 个字段 × 10 条。

#### **4️⃣ 发送 post_json（第 118-119 行 → 第 15-27 行）**

```
CLIENT = httpx.Client(http2=True, timeout=25)          ← 模块级，连接复用
3 次循环：
  ├── httpx.HTTPError → RuntimeError("Model connection failed; no action executed.")
  ├── 429/529/503 且未到最后一次 → sleep(0.5 * 2**attempt) 后重试
  ├── 其他 is_error → RuntimeError("HTTP {code}; no action executed.")
  └── 成功 → response.json()
```

**✅ 幂等重试安全**：请求是纯提问，无副作用——重试不违反"变更零重试"。

**❌ 网络失败**：立即 RuntimeError 上抛，predict 失败，**没有任何浏览器动作发生**。

---

### 🧪 完整请求/响应示例（Flights 首页第一次决策）

**场景**：页面刚加载，快照发现 4 个元素——票型切换按钮、出发/到达 combobox、日期框。`action_space` 产出一节点一索引的元素表；注意每个可编辑 combobox 有**两个**动作（fill + click），共享同一索引。

**请求体**（POST `https://api.typesafe.ai/v1/systemone`，`Authorization: Bearer <TYPESAFE_API_KEY>`）：

```json
{
  "model": "jev-latest",
  "state": {
    "page": {
      "url": "https://www.google.com/travel/flights?hl=en",
      "title": "Find Cheap Flights Worldwide & Book Your Ticket - Google Flights",
      "text": "Round trip. 1 Adult. Economy. Where from? Where to? Departure. Search. …(≤6000 字符可见文本)"
    },
    "elements": [
      { "index": "1", "label": "Change ticket type. Round trip", "role": "button",   "value": "", "operations": ["CLICK"] },
      { "index": "2", "label": "Where from?", "role": "combobox", "value": "", "operations": ["TYPE_TEXT", "CLICK"] },
      { "index": "3", "label": "Where to?",   "role": "combobox", "value": "", "operations": ["TYPE_TEXT", "CLICK"] },
      { "index": "4", "label": "Departure",   "role": "textbox",  "value": "", "operations": ["CLICK"] }
    ],
    "recent_actions": []
  },
  "questions": {
    "operation": {
      "type": "choice",
      "criteria": {
        "CLICK":       "Click an element, button, menu option, autocomplete suggestion, or calendar day.",
        "TYPE_TEXT":   "Enter or replace text in an editable field. A small LLM will supply the value from the goal.",
        "SCROLL_DOWN": "Scroll down",
        "WAIT":        "Wait for the page to update",
        "DONE":        "Every requirement is visibly satisfied.",
        "BLOCKED":     "No supported operation can progress."
      },
      "instructions": {
        "goal": "Find one-way flights from Zurich to London on October 20, 2026, …",
        "rules": "<NEXT_ACTION 全文，questions.py:3-14>"
      }
    },
    "click_target": {
      "type": "choice",
      "criteria": {
        "1": { "element": "[1] Change ticket type. Round trip", "current_value": "", "role": "button" },
        "2": { "element": "[2] Open Where from?", "current_value": "", "role": "combobox" },
        "3": { "element": "[3] Open Where to?",   "current_value": "", "role": "combobox" },
        "4": { "element": "[4] Open Departure",   "current_value": "", "role": "textbox" }
      },
      "instructions": { "goal": "…同上…", "operation": "CLICK", "rules": ["<NEXT_ACTION>", "<TARGET 全文>"] }
    },
    "type_text_target": {
      "type": "choice",
      "criteria": {
        "2": { "element": "[2] Where from?", "current_value": "", "role": "combobox" },
        "3": { "element": "[3] Where to?",   "current_value": "", "role": "combobox" }
      },
      "instructions": { "goal": "…同上…", "operation": "TYPE_TEXT", "rules": ["<NEXT_ACTION>", "<TARGET>"] }
    }
  }
}
```

要点：`click_target` 的候选带 "Open " 前缀（点开控件），`type_text_target` 的候选是字段本身——同一元素两个视图；WAIT/SCROLL/DONE/BLOCKED 不可寻址，只出现在 operation 头；若页面有原生 `<select>`，还会多一个 `select_target` 头，目标键形如 `"5:2"`（元素 5 的第 2 个选项）。

**响应体**：

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "operation": {
      "choice": "CLICK", "confidence": 0.92,
      "probabilities": { "CLICK": 0.94, "TYPE_TEXT": 0.04, "WAIT": 0.01, "SCROLL_DOWN": 0.0, "DONE": 0.0, "BLOCKED": 0.01 }
    },
    "click_target": {
      "choice": "1", "confidence": 0.90,
      "probabilities": { "1": 0.90, "2": 0.04, "3": 0.03, "4": 0.03 }
    },
    "type_text_target": {
      "choice": "3", "confidence": 0.55,
      "probabilities": { "2": 0.75, "3": 0.45 }
    }
  },
  "usage": { "input_tokens": 1830, "output_tokens": 96 }
}
```

注意 `type_text_target` 的概率和是 1.2 ≠ 1——**故意示例**：投机头即使返回畸形答案也无害，因为本次操作选了 CLICK，代码只校验 `click_target`（model.py:127 只读取 `operation.lower() + "_target"`）。

**校验与翻译（model.py:120-133）**：

```
validate_choice(operation)  候选={CLICK,TYPE_TEXT,SCROLL_DOWN,WAIT,DONE,BLOCKED}
  ✓ choice∈候选 ✓ 概率覆盖全集 ✓ 全为[0,1] ✓ 和=1.0 ✓ CLICK 是最大值(0.94)
operation=CLICK ∈ targets → validate_choice(click_target)  候选={"1","2","3","4"}
  ✓ 全部通过 → target="1" → choice = targets["CLICK"]["1"]["id"] = "e1"
```

**`choose()` 返回的 decision**（即 `state['decision']`，概率键已从目标索引翻译成动作 id）：

```json
{
  "choice": "e1", "operation": "CLICK", "target": "1",
  "confidence": 0.92, "target_confidence": 0.90,
  "probabilities": { "e1": 0.90, "e3": 0.04, "e5": 0.03, "e6": 0.03 },
  "operation_probabilities": { "CLICK": 0.94, "TYPE_TEXT": 0.04, "…": "…" },
  "target_probabilities": { "1": 0.90, "2": 0.04, "3": 0.03, "4": 0.03 },
  "model": "jev-1.13.0", "latency_ms": 178,
  "usage": { "input_tokens": 1830, "output_tokens": 96 },
  "raw_answers": { "…": "响应 answers 原文，供审计" },
  "request": { "…": "完整请求体，供审计" }
}
```

（动作 id 按快照顺序编号：e1=票型按钮的 click、e2=Where from 的 fill、e3=Open Where from 的 click……`probabilities` 的键就是这些 id。）

---

### 🎯 **设计亮点**

1. **投机性 Fan-out**（TypeSafe 官方模式）：N+1 个问题一次往返，串行"先操作后目标"两次调用被消灭——中位 TypeSafe 请求 22→17、总时长 -25% 的来源之一。
2. **传输重试与变更重试分离**：post_json 只重试幂等提问。
3. **HTTP/2 + 连接复用**：单连接承载全部决策请求，握手成本一次性。

---

### 📊 **返回值结构**

`post_json` → provider JSON（`answers`/`model`/`usage`）。`choose` 发送阶段无独立返回。

---

### 💡 **典型使用场景**

- 每次决策一发；实测中位 Jev 延迟 178ms（docs/performance.md）。

---

### 🔗 **与其他方法的协作**

```
command('predict')
  → action_space ─┐
  → questions 常量 ┼─▶ choose 组装 body ─▶ post_json ─▶ TypeSafe API
  → state/history ─┘
```

---

## 📂 **相关文件**

| 文件 | 作用 |
|------|------|
| `jev_ultrafast/model.py:81-119` | 请求构建 |
| `jev_ultrafast/model.py:15-27` | post_json 传输层 |
| `jev_ultrafast/questions.py:3-19` | 两段规则文本 |
| `tests/test_agent.py:116-139` | 目标头规则完整性断言 |

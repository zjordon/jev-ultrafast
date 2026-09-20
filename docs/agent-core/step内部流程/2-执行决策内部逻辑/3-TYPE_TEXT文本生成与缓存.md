## `TYPE_TEXT 文本生成与缓存` 方法逻辑梳理

### 📋 **方法作用**

fill 动作的取值环节：构造完整文本生成上下文 → 命中缓存则复用，否则调用小型 LLM 严格生成——并保证"生成值只在完全相同的输入下存活"。

> 源码: agent.py 第 105-115 行 + model.py 第 151-157 行（`field_context`）、第 160-198 行（`field_text`）

---

### 🔄 **主要逻辑流程**

#### **1️⃣ 生成前新鲜度（agent.py 第 106-108 行）**

```python
if action["kind"] == "fill":
    if not state["browser"].fresh(page):
        raise StalePage("Page changed before text generation. Choose again.")
```

- 文本生成是**又一个模型调用**（几百 ms），期间页面可能变化——生成前先验一次。

#### **2️⃣ 上下文构造（agent.py 第 109 行 → model.py 第 151-157 行）**

```python
context = field_context(state["goal"], action, page, state["history"])
# = {
#   "goal": 原始目标全文,
#   "field": {label, role, value},
#   "page": {"title": ..., "text": page["text"][:6000]},
#   "recent_actions": [{action, text} for h in history[-6:]],
# }
```

**关键参数说明：**
| 参数 | 说明 |
|------|------|
| `field` | 被选中字段的标签/角色/当前值——LLM 据此判断"该填什么" |
| `page.text[:6000]` | 快照可见文本——页面语境（不可信数据，非指令） |
| `history[-6:]` | 仅 (action, text) 两字段——知道哪些值已填过 |

**整个 context 即缓存键。**

#### **3️⃣ 缓存命中或生成（agent.py 第 110-115 行）**

**✅ 缓存命中（`pending_text[0] == context` 字典相等）：**
```python
_, text, helper = self.pending_text
```

**❌ 未命中：**
```python
text, helper = field_text(context)                    # 真实 LLM 调用
self.pending_text = (context, text, helper)
state["text_calls"].append({**helper, "field": action["label"], "value": text})
```

- 仅**真实调用**记入 text_calls 账本（复用不重复计费/计数）。

#### **4️⃣ field_text 内部（model.py 第 160-198 行）**

```
缺 TEXT_MODEL_API_KEY → ValueError（绝不硬编码/猜测）
reasoning 配置：deepseek 域 → thinking.disabled；其他 → effort:low；TEXT_MODEL_REASONING=none → enabled=False
POST {TEXT_MODEL_BASE_URL}/chat/completions {response_format: json_object, max_tokens: 1024,
     messages: [system=TEXT_VALUE, user=json(context)]}
解析 → 必须恰为 {"text": 非空 str ≤2000 字符}，否则 ValueError("...nothing typed")
返回 (value, {model, latency_ms, usage})
```

---

### 🎯 **设计亮点**

1. **缓存键=完整输入**：`test_generated_text_reused_only_for_identical_retry_context`（复用 1 次调用）与 `test_changed_field_context_does_not_reuse_generated_text`（页面文本一变即重新生成）共同固定语义——AGENTS.md「Cache a stale retry's value only while its entire helper input is identical」的落地。
2. **不从目标抽值**：`test_quoted_task_text_still_uses_the_llm` 证明目标里带引号的 "Zurich" 也必须走 LLM，代码不偷懒。
3. **严格输出契约**：`{"text": null}`（明确缺值）、多键、非字符串、思考前缀一律拒绝——宁可不输入也不输错。
4. **成功即弃缓存**：`browser.act` 成功后 `pending_text = None`（agent.py 第 118 行）——生成值永不跨字段复用。

---

### 📊 **返回值结构**

| 产物 | 说明 |
|------|------|
| `text` | 待输入字符串（传给 browser.act） |
| `helper` | `{model, latency_ms, usage}` → 并入 history 的 text_helper/text_latency_ms 字段 |
| `text_calls` 追加 | `{model, latency_ms, usage, field, value}`——付费调用账本 |

---

### 💡 **典型使用场景**

- Flights 任务的 "Zurich"/"London" 两值（实测 581ms/346ms，OpenRouter 单价 $0.00006272）。

---

### 🔗 **与其他方法的协作**

```
command('act') fill 分支
  ├── Browser.fresh
  ├── field_context ──▶ pending_text 命中? ──是──▶ 复用
  │                        └─否─▶ field_text ─▶ post_json ─▶ 文本 LLM
  └── (text) ──▶ browser.act(action, page, text)
                    └─ 成功 → pending_text=None
```

---

## 📂 **相关文件**

| 文件 | 作用 |
|------|------|
| `jev_ultrafast/agent.py:105-115,118` | 缓存策略 |
| `jev_ultrafast/model.py:151-198` | 上下文与生成 |
| `jev_ultrafast/questions.py:21-24` | TEXT_VALUE 指令 |
| `tests/test_agent.py:143-157,189-211,305-312` | 三组语义回归 |

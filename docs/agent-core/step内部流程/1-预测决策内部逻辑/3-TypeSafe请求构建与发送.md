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

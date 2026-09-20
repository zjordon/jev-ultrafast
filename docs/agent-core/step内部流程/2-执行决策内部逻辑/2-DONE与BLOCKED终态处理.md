## `DONE 与 BLOCKED 终态处理` 方法逻辑梳理

### 📋 **方法作用**

当模型选择 DONE/BLOCKED 时收尾运行：先验证页面未变（防止基于旧页面宣告完成），再迁移状态并返回最终快照。

> 源码: agent.py 第 93-100 行

---

### 🔄 **主要逻辑流程**

#### **1️⃣ 终态识别（第 92-93 行）**

```python
selected = decision["choice"]
if selected in {"DONE", "BLOCKED"}:
```

- DONE/BLOCKED 是 operation 头的固定候选（model.py 第 90 行），choice 即操作名本身（无目标头）。

#### **2️⃣ 终态新鲜度（第 94-96 行）**

**❌ 页面已变 → StalePage：**
```python
if not state["browser"].fresh(page):
    state["status"] = "ready"
    raise StalePage("Page changed since the decision. Choose again.")
```
- 注意先**回滚 status 为 ready**再抛——tick 捕获后重新观察进入下一轮，run() 不会因异常终止。
- 场景：模型看页面 A 说 DONE，期间页面跳到 B（如搜索结果延迟到达）——旧 DONE 作废。

**✅ 页面未变 → 迁移终态（第 97-100 行）：**
```python
state["status"] = "done" if selected == "DONE" else "blocked"
state["plan_index"] = int(selected == "DONE")
state["elapsed_ms"] = round((time.perf_counter() - state["started_at"]) * 1000)
return self.snapshot()
```

| 字段 | 变化 |
|------|------|
| `status` | predicted → done / blocked |
| `plan_index` | 0 → 1（DONE）或保持 0（plan=[task] 的单目标完成标记） |
| `elapsed_ms` | 最终耗时定格 |

---

### 🎯 **设计亮点**

1. **DONE 不是成功证明**：终态只代表"模型认为完成"；README/AGENTS.md 与 examples/flights.py 的独立 `verify()` 才是裁判（检查 URL、单程、城市、日期、结果可见）。
2. **终态可被页面变化推翻**：fresh 失败把 DONE 变回一轮普通循环，而非错误终止。
3. **耗时定格点即测量边界**：docs/performance.md 的"从首次预测到被接受的 DONE"口径在此行落地。

---

### 📊 **返回值结构**

`self.snapshot()`——state（含 history/decisions/text_calls 全账本）+ elements。终态后再次 command 抛 ValueError（predict 第 73-74 行）。

---

### 💡 **典型使用场景**

- Google Flights 任务：DONE 在航班结果可见后出现；flights.py 随后独立校验 8 项检查，任一不符即非零退出。

---

### 🔗 **与其他方法的协作**

```
command('act')
  ├── selected ∈ {DONE, BLOCKED}
  │     ├── Browser.fresh(page)  ← marker 全页比对
  │     │     └── False → status=ready + StalePage → tick 恢复
  │     └── True  → 终态 + snapshot
  └── 其余 → 执行路径
run() 的 while 条件在此后退出
```

---

## 📂 **相关文件**

| 文件 | 作用 |
|------|------|
| `jev_ultrafast/agent.py:93-100` | 本段逻辑 |
| `examples/flights.py:18-38` | DONE 之后的独立校验 |
| `docs/performance.md` | 计时口径定义 |

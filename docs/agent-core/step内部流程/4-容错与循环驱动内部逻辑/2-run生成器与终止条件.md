## `run 生成器与终止条件` 方法逻辑梳理

### 📋 **方法作用**

Agent 的顶层入口与循环外壳：以生成器逐 tick 产出快照，把六种终止来源收敛为 `done/blocked` 两个终态——同时天然提供"暂停=停止迭代"的控制语义。

> 源码: agent.py 第 163-165 行（run）+ 各终止点汇总

---

### 🔄 **主要逻辑流程**

#### **1️⃣ 生成器本体（第 163-165 行）**

```python
def run(self):
    while self.state["status"] not in {"done", "blocked"}:
        yield self.command("tick")
```

- 每次迭代：tick（predict+act+恢复兜底）→ yield snapshot → **挂起等待调用方**。
- 调用方不迭代 = 暂停；`break`/关闭生成器 = 停止（浏览器仍持有，直到 close/上下文退出）。

#### **2️⃣ 六种终止来源 → 两个终态**

| # | 来源 | 位置 | 终态 |
|---|------|------|------|
| 1 | 模型选 DONE 且页面新鲜 | act L93-100 | done |
| 2 | 模型选 BLOCKED 且页面新鲜 | act L93-100 | blocked |
| 3 | 连续 3 步无进展（非 wait） | act L153-158 | blocked |
| 4 | 60 动作预算耗尽 | act L102-104 | blocked（伴随 ValueError） |
| 5 | 120 决策预算耗尽 | predict L75-76 | 抛 ValueError，run 传播异常终止 |
| 6 | 模型/网络 RuntimeError | model.py 各处 | 抛出传播，run 异常终止 |

- 1-4 是**状态终止**：run 自然耗尽，state 完整可读。
- 5-6 是**异常终止**：调用方 except 处理；state 保留已发生的一切（history 无损）。
- 终态后再 command → ValueError("This run has stopped…")（predict L73-74）——重启 = 新建 Agent。

#### **3️⃣ 标准消费模式（examples/run.py）**

```python
with Agent(args.url, args.goal) as agent:
    for state in agent.run():
        print(f"{state['elapsed_ms']:>5} ms  {len(state['history'])} actions  {state['status']}")
    print(state["page"]["url"])     # 循环正常结束后 state 仍可用
```

- 上下文管理器保证异常路径也关闭浏览器标签页（`__exit__` → close，第 170-174 行）。

---

### 🎯 **设计亮点**

1. **生成器即控制流**：无 pause/resume/stop API——暂停=不取下一帧，停止=离开 with 块；检查器 "Choose next" 只是逐帧 POST 的 UI 糖。
2. **终态收敛**：正常终局只有两个词，demo/脚本/测量工具共享同一判读逻辑。
3. **账本在异常后仍完整**：配合写前日志，任何终止方式都不丢已执行动作。

---

### 📊 **返回值结构**

逐帧 `snapshot()`：state 去 browser + elements 索引表 + （demo 层附加 text_model/max_steps）。最后一帧的 status 必为 done/blocked（正常耗尽时）。

---

### 💡 **典型使用场景**

- examples/run.py / flights.py / scripts/measure_flights.py / record_flights.py 全部经 run() 驱动；flights.py 在 finally 中补独立校验。

---

### 🔗 **与其他方法的协作**

```
run()
  └── 循环 ──▶ command('tick') ──▶ snapshot ── yield ──▶ 调用方
        │
        └── status ∈ {done, blocked} ──▶ 生成器耗尽
              ├── flights.py: verify(page) 独立校验
              └── 检查器: 渲染终态
```

---

## 📂 **相关文件**

| 文件 | 作用 |
|------|------|
| `jev_ultrafast/agent.py:163-174` | run 与上下文管理器 |
| `examples/run.py` | 最小消费示例 |
| `examples/flights.py:49-64` | 终态后独立校验模式 |

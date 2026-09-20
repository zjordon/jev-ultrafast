## `tick 编排与 StalePage 恢复` 方法逻辑梳理

### 📋 **方法作用**

单步自动模式的编排器：串联 predict 与 act，并作为全循环**唯一**的自动恢复点——StalePage 在此被转化为"重新观察后重试整个决策"，而非重试任何浏览器变更。

> 源码: agent.py 第 55-64 行

---

### 🔄 **主要逻辑流程**

#### **1️⃣ 正常路径（第 56-58 行）**

```python
self.command("predict", {})
return self.command("act", {"fingerprint": state["page"]["fingerprint"]})
```

- act 的 fingerprint 直接取自 predict 刚确认/刷新的 `state['page']`——同帧传递，调用方无法注入过期指纹。
- predict 若已抛 ValueError/RuntimeError（预算/校验/网络），不上抛包装、直接透传给调用方——tick 只兜 StalePage。

#### **2️⃣ 恢复路径（第 59-64 行）**

**✅ 触发条件**：predict 或 act 任一环节抛 `StalePage`，来源包括：
| 抛出点 | 场景 |
|--------|------|
| predict L70 fresh 失败后的 observe（经 browser 重试 10 次仍失败） | 页面持续导航 |
| act L94-96 | DONE/BLOCKED 时页面已变 |
| act L107-108 | fill 文本生成前页面已变 |
| Browser.act L101-102 | 输入前守卫失败（目标被替换/遮挡） |
| act 尾段 observe（导航撕毁求值上下文） | 输入后立即跳转 |

**恢复四步：**
```python
state["decision"] = None                                  # ① 作废任何残留决策
state["status"] = "ready"                                 # ② 回到可预测状态
state["page"] = state["browser"].observe(screenshot=...)  # ③ 只读重观察
state["elapsed_ms"] = round(...)                          # ④ 计时连续（不重置）
return self.snapshot()                                    #    本步结束，下一 tick 重新 predict
```

**❌ 不做的事**：不重试 browser.act、不重新选动作、不复用旧决策——恢复后一切决策从头来过（文本缓存按输入相等独立幸存）。

**📝 计时语义**：`started_at` 从不重置——恢复消耗的时间全部计入 elapsed_ms（docs/performance.md："includes stale decisions"）。

#### **3️⃣ 恢复正确性的测试锚点**

`test_navigation_during_prediction_reobserves_without_action`（tests/test_agent.py 第 315-320 行）：
```python
runner.state["browser"].fresh.side_effect = StalePage("Document navigating")
runner.command("tick")
assert runner.state["status"] == "ready"
assert runner.state["decision"] is None
runner.state["browser"].act.assert_not_called()    # 恢复路径绝不触碰执行
```

---

### 🎯 **设计亮点**

1. **异常分类学**：StalePage=环境变了（可恢复，重看）；RuntimeError=模型/传输/结果不确定（停）；ValueError=调用方/预算（停）——只有第一类值得自动重试，且重试对象是观察。
2. **恢复与重试的严格区分**：AGENTS.md「Never retry a browser mutation」在代码里表现为——恢复路径的三个动作（清决策/置 ready/observe）没有一个改变浏览器状态。
3. **一步一世界**：恢复步本身返回 snapshot，调用方看到的是"页面变了但没动作"的诚实帧。

---

### 📊 **返回值结构**

`self.snapshot()`——两种路径同构；区别仅在 decision=None（恢复后必然）与 page 已刷新。

---

### 💡 **典型使用场景**

- `run()` 自动循环的每一拍；检查器 "Run automatically" 模式的每步 POST /api/tick。

---

### 🔗 **与其他方法的协作**

```
command('tick')
  ├── command('predict') ──┬─ StalePage ─┐
  └── command('act') ──────┤             ▼
                          └─ 正常返回   恢复（清决策/ready/observe）→ snapshot
```

---

## 📂 **相关文件**

| 文件 | 作用 |
|------|------|
| `jev_ultrafast/agent.py:55-64` | 本方法 |
| `jev_ultrafast/browser.py:16-17` | StalePage 定义 |
| `tests/test_agent.py:315-320` | 恢复语义回归 |

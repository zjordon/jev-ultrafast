"""Run snapshot.js and the ported dom_tree on an open Chrome tab; save both outputs for comparison.

No model calls. Read-only page evaluation (dom_tree highlights are off unless --highlight).

Usage:
  uv run python scripts/compare_dom_output.py --list
  uv run python scripts/compare_dom_output.py --index 2
  uv run python scripts/compare_dom_output.py --url wikipedia
"""

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from browser_harness.admin import ensure_daemon
from browser_harness.helpers import cdp

from jev_ultrafast.browser import READ_STATE
from jev_ultrafast.model import action_space

ROOT = Path(__file__).resolve().parents[1]
DOM_TREE = (ROOT / "scripts" / "dom_tree" / "index.js").read_text(encoding="utf-8")
KEY_ATTRS = ("id", "name", "type", "role", "aria-label", "placeholder", "href", "data-testid")


def evaluate(session, expression):
    response = cdp(
        "Runtime.evaluate", session_id=session, expression=expression,
        returnByValue=True, _response_timeout=120,
    )
    if response.get("exceptionDetails"):
        detail = response["exceptionDetails"].get("exception", {}).get("description", "")
        raise RuntimeError(f"page evaluation failed: {response['exceptionDetails'].get('text')} {detail[:400]}")
    return response["result"]["value"]


def pick_target(targets, args):
    if args.index is not None:
        return targets[args.index - 1]
    return next(t for t in targets if args.url in t["url"])


def run_snapshot(session):
    return evaluate(session, READ_STATE)


def run_dom_tree(session, highlight):
    dom_args = {
        "doHighlightElements": highlight,
        "focusHighlightIndex": -1,
        "viewportExpansion": 0,
        "debugMode": False,
        "interactiveBlacklist": [],
        "interactiveWhitelist": [],
        "highlightOpacity": 0.1,
        "highlightLabelOpacity": 0.5,
    }
    expression = (
        DOM_TREE
        + "\n;(() => { const __r = __domTree(" + json.dumps(dom_args) + ");\n"
        + "if (__r && __r.map) { for (const k of Object.keys(__r.map)) delete __r.map[k].ref; }\n"
        + "return __r; })()"
    )
    return evaluate(session, expression)


def child_text(nodes, node):
    parts = []
    for child_id in node.get("children", []):
        child = nodes.get(child_id)
        if child and child.get("type") == "TEXT_NODE" and child.get("text"):
            parts.append(child["text"])
    return " ".join(parts)


def write_summary(outdir, target, snap, tree, highlight):
    snap_bytes = (outdir / "snapshot.json").stat().st_size
    tree_bytes = (outdir / "dom_tree.json").stat().st_size
    nodes = tree["map"]
    total = len(nodes)
    text_nodes = sum(1 for n in nodes.values() if n.get("type") == "TEXT_NODE")
    element_nodes = sum(1 for n in nodes.values() if "tagName" in n)
    interactive = sum(1 for n in nodes.values() if n.get("isInteractive"))
    top = sum(1 for n in nodes.values() if n.get("isTopElement"))
    highlighted = sorted(
        (n for n in nodes.values() if "highlightIndex" in n), key=lambda n: n["highlightIndex"]
    )
    actions = snap["actions"]
    kinds = Counter(a["kind"] for a in actions)
    elements, targets, controls = action_space(actions)

    lines = [
        "# DOM 采集产出对比",
        "",
        f"- 页面：{snap['title']}",
        f"- URL：{snap['url']}",
        f"- Chrome target：{target['targetId']}",
        f"- dom_tree 参数：doHighlightElements={highlight}，viewportExpansion=0",
        f"- 采集时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "> 注意：doHighlightElements=false 时 dom_tree 不做 in-page 高亮，",
        "> 此时父级未标记为 highlighted，嵌套交互去重（isElementDistinctInteraction）不生效，",
        "> 每个视口内交互候选都会拿到 highlightIndex——这是 browser-use 无高亮模式的原生行为。",
        "",
        "## 总体对比",
        "",
        "| 指标 | snapshot.js | dom_tree |",
        "| --- | ---: | ---: |",
        f"| 文件大小 | {snap_bytes:,} B | {tree_bytes:,} B |",
        f"| 产出形态 | 扁平动作列表（{len(actions)} 条动作） | 全页面节点树（{total} 个节点） |",
        f"| 文本 | 单一 text 字段（{len(snap.get('text', ''))} 字符） | {text_nodes} 个独立 TEXT_NODE |",
        f"| 元素/交互 | {len(elements)} 个索引元素 | {element_nodes} 元素节点 |",
        f"| 交互判定 | —（白名单即动作） | {interactive} isInteractive / {top} isTopElement |",
        f"| 可执行候选 | {len(actions)} 动作（{dict(kinds)}） | {len(highlighted)} 个 highlightIndex |",
        "| 值与状态 | 每动作带 value/checked/selected | 全量 attributes + extra |",
        "| 指纹材料 | marker/page_key/guards | 无（新鲜度交给 Python 侧） |",
        "",
        "## snapshot.js 产出摘要（前 30 条动作）",
        "",
        "| # | id | kind | label | value |",
        "| --- | --- | --- | --- | --- |",
    ]
    for i, a in enumerate(actions[:30], 1):
        label = str(a.get("label", ""))[:60].replace("|", "\\|")
        value = str(a.get("value", ""))[:30].replace("|", "\\|")
        lines.append(f"| {i} | {a.get('id', '')} | {a['kind']} | {label} | {value} |")
    lines += [
        "",
        f"元素表（{len(elements)} 项，供 TypeSafe 候选）："
        + ", ".join(f"[{e['index']}] {e['label'][:30]}" for e in elements[:12])
        + ("…" if len(elements) > 12 else ""),
        "",
        "## dom_tree 产出摘要（前 30 个 highlightIndex 节点）",
        "",
        "| idx | tag | 关键属性 | 直接文本 |",
        "| --- | --- | --- | --- |",
    ]
    for n in highlighted[:30]:
        attrs = n.get("attributes", {})
        picked = [f"{k}={str(attrs[k])[:40]}" for k in KEY_ATTRS if attrs.get(k)]
        text = child_text(nodes, n)[:50].replace("|", "\\|")
        lines.append(f"| {n['highlightIndex']} | {n.get('tagName', '')} | {'; '.join(picked)[:90]} | {text} |")
    lines += [
        "",
        "## 如何阅读两个文件",
        "",
        "- `snapshot.json`：顶层是 `actions/text/marker/page_key/guards`；`actions` 即动作空间，",
        "  Python 侧直接消费（action_space/choose/执行）。",
        "- `dom_tree.json`：顶层是 `{rootId, map}`；`map` 的键是节点 id，值含 `tagName/attributes/children`，",
        "  交互节点带 `isInteractive/isTopElement/highlightIndex` 标志——它是给 LLM 读的结构树，",
        "  还需要 Python/LLM 二次加工才能变成动作。",
        "",
    ]
    (outdir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="pick the first tab whose URL contains this substring")
    parser.add_argument("--index", type=int, help="pick the Nth tab from the --list output")
    parser.add_argument("--list", action="store_true", help="list open http(s) tabs and exit")
    parser.add_argument("--highlight", action="store_true",
                        help="let dom_tree draw in-page highlight overlays (marks the page; reload to clear)")
    args = parser.parse_args()

    ensure_daemon()
    targets = [t for t in cdp("Target.getTargets")["targetInfos"]
               if t["type"] == "page" and t["url"].startswith("http")]
    if not targets:
        raise SystemExit("Chrome has no http(s) page tabs open")
    print("Open page tabs:")
    for i, t in enumerate(targets, 1):
        print(f"  {i}. {t['title'][:60]} | {t['url'][:90]}")
    if args.list or (not args.url and args.index is None):
        print("\nRe-run with --index N or --url <substring> to capture a tab.")
        return
    target = pick_target(targets, args)
    print(f"\nCapturing: {target['url'][:90]}")

    session = cdp("Target.attachToTarget", targetId=target["targetId"], flatten=True)["sessionId"]
    try:
        print("Evaluating snapshot.js ...")
        snap = run_snapshot(session)
        print("Evaluating dom_tree (ported) ...")
        tree = run_dom_tree(session, args.highlight)
    finally:
        cdp("Target.detachFromTarget", sessionId=session)

    outdir = ROOT / "out" / "dom-comparison" / time.strftime("%Y%m%d-%H%M%S")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "snapshot.json").write_text(
        json.dumps(snap, indent=1, ensure_ascii=False), encoding="utf-8")
    (outdir / "dom_tree.json").write_text(
        json.dumps(tree, indent=1, ensure_ascii=False), encoding="utf-8")
    write_summary(outdir, target, snap, tree, args.highlight)
    print(f"\nSaved to {outdir}")
    print("  snapshot.json / dom_tree.json / summary.md")


if __name__ == "__main__":
    main()

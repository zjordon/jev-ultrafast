"""Capture the exact request body model.choose() would send to TypeSafe for an open Chrome tab.

Runs snapshot.js on the tab, feeds the result through the real choose() pipeline, and
intercepts post_json with a stub (no network call, no API cost). Saves the request body
plus a readable preview to out/model-request/<timestamp>/.

Usage:
  uv run python scripts/capture_model_request.py --list
  uv run python scripts/capture_model_request.py --index 2
  uv run python scripts/capture_model_request.py --url wikipedia --goal 'Find the search box'
"""

import argparse
import json
import os
import time
from pathlib import Path

from browser_harness.admin import ensure_daemon
from browser_harness.helpers import cdp

import jev_ultrafast.model as model
from jev_ultrafast.browser import READ_STATE

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOAL = "Describe this page and choose the best next action."


def evaluate(session, expression):
    response = cdp(
        "Runtime.evaluate", session_id=session, expression=expression,
        returnByValue=True, _response_timeout=120,
    )
    if response.get("exceptionDetails"):
        detail = response["exceptionDetails"].get("exception", {}).get("description", "")
        raise RuntimeError(f"page evaluation failed: {response['exceptionDetails'].get('text')} {detail[:400]}")
    return response["result"]["value"]


def stub_post_json(captured):
    """Replacement for model.post_json: record the body, return a valid fake answer."""

    def post(_url, _key, body):
        captured.append(body)
        answers = {}
        for name, question in body["questions"].items():
            ids = list(question["criteria"].keys())
            answers[name] = {
                "choice": ids[0],
                "confidence": 1.0,
                "probabilities": {i: (1.0 if i == ids[0] else 0.0) for i in ids},
            }
        return {"model": "capture-stub", "answers": answers, "usage": {}}

    return post


def write_preview(outdir, body):
    page = body["state"]["page"]
    elements = body["state"]["elements"]
    questions = body["questions"]
    lines = [
        "# 发送给 Jev 模型的内容预览",
        "",
        f"- 页面：{page['title']} | {page['url']}",
        f"- 可见文本（state.page.text）：{len(page['text'])} 字符",
        f"- 元素表（state.elements）：{len(elements)} 项",
        f"- 历史（state.recent_actions）：{len(body['state']['recent_actions'])} 条",
        f"- 问题（questions）：{len(questions)} 道",
        "",
        "## 元素表（state.elements）",
        "",
        "| index | label | role | value | operations |",
        "| --- | --- | --- | --- | --- |",
    ]
    for e in elements:
        value = str(e.get("value", ""))[:30].replace("|", "\\|")
        options = f" +{len(e['options'])}选项" if "options" in e else ""
        lines.append(
            f"| {e['index']} | {str(e['label'])[:50]} | {e.get('role', '')} | {value} | "
            f"{'/'.join(e['operations'])}{options} |"
        )
    lines += ["", "## 问题（questions）", ""]
    for name, question in questions.items():
        criteria = question["criteria"]
        lines.append(f"### {name}（{len(criteria)} 个候选）")
        lines.append("")
        instructions = question["instructions"]
        rules = instructions["rules"]
        rules_text = rules if isinstance(rules, str) else " + ".join(rules)
        lines.append(f"- instructions：goal={instructions['goal'][:80]}…")
        lines.append(f"  rules={rules_text[:80]}…（全文见 request.json）")
        if "operation" in instructions:
            lines.append(f"  操作假设：{instructions['operation']}")
        lines.append("- 候选：")
        shown = list(criteria.items())[:15]
        for key, value in shown:
            label = value if isinstance(value, str) else value.get("element", str(value))
            lines.append(f"  - `{key}`：{str(label)[:90]}")
        if len(criteria) > len(shown):
            lines.append(f"  - …共 {len(criteria)} 个")
        lines.append("")
    (outdir / "preview.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="pick the first tab whose URL contains this substring")
    parser.add_argument("--index", type=int, help="pick the Nth tab from the --list output")
    parser.add_argument("--list", action="store_true", help="list open http(s) tabs and exit")
    parser.add_argument("--goal", default=DEFAULT_GOAL, help="natural-language goal embedded in the request")
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
    target = targets[args.index - 1] if args.index else next(t for t in targets if args.url in t["url"])
    print(f"\nCapturing: {target['url'][:90]}")

    session = cdp("Target.attachToTarget", targetId=target["targetId"], flatten=True)["sessionId"]
    try:
        print("Evaluating snapshot.js ...")
        snap = evaluate(session, READ_STATE)
    finally:
        cdp("Target.detachFromTarget", sessionId=session)

    print("Running the real choose() pipeline with a post_json capture stub ...")
    captured = []
    key_injected = "TYPESAFE_API_KEY" not in os.environ
    if key_injected:
        os.environ["TYPESAFE_API_KEY"] = "capture-stub"
    real_post = model.post_json
    model.post_json = stub_post_json(captured)
    try:
        model.choose(snap, args.goal, [])
    finally:
        model.post_json = real_post
        if key_injected:
            del os.environ["TYPESAFE_API_KEY"]

    if not captured:
        raise SystemExit("choose() did not reach post_json; nothing captured")

    body = captured[0]
    outdir = ROOT / "out" / "model-request" / time.strftime("%Y%m%d-%H%M%S")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "request.json").write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
    write_preview(outdir, body)
    size = (outdir / "request.json").stat().st_size
    print(f"\nSaved to {outdir}")
    print(f"  request.json ({size:,} B) — 原样请求体（未发送，捕获自真实 choose 流水线）")
    print("  preview.md — 可读预览（元素表 + 各问题的候选与指令）")


if __name__ == "__main__":
    main()

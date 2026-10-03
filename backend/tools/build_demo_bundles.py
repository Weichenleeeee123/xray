"""生成预制示例（data/demo_prebuilt/<id>.json）：把 demo_cases.json 里准备好的示例真跑一遍，
记下第一版、按顺序补充后的每一版，以及每次的研究过程事件。现场点示例时直接交出这些，不联网。

在 backend 目录运行：
  .venv/Scripts/python tools/build_demo_bundles.py            # 全部示例
  .venv/Scripts/python tools/build_demo_bundles.py A C        # 只生成 A、C

会真的联网查（企查查 24 小时内有缓存就不扣积分；网页搜索、模型照常调用）。案卷写进临时目录，不进案卷列表。
生成完会检查每一版里有没有"没查成"的条目：有就说明当时某个数据源出了错，先修好再重新生成，别拿去演示。
"""
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["XRAY_DEMO_PREBUILT"] = "0"                       # 生成时不用旧的预制包
os.environ.setdefault("XRAY_CASES_DIR", tempfile.mkdtemp(prefix="demo-build-"))

from app import demo_prebuilt, main, privacy, progress    # noqa: E402  环境变量要先设好

NOTE = "预制示例：这份报告在 {when} 生成，现场演示直接展示，不重新联网查询；记录截至当时。"


def record(work):
    events, t0 = [], time.monotonic()
    with progress.reporting(lambda e: events.append({**e, "t": round(time.monotonic() - t0, 2)})):
        case = work()
    return case, events


def failed_items(case) -> list[str]:
    v = case.versions[-1]
    return [f"第 {v.no} 版 {s.key}.{i.key}：{i.detail}" for s in v.signals for i in s.items
            if i.status == "none" and i.gap == "failed"]


def frozen(case, when: str) -> dict:
    data = case.model_dump(mode="json")
    data.update(owner_id=None, revision=0, chat=[])
    for v in data["versions"]:
        if not any(n.startswith("预制示例") for n in v["notes"]):
            v["notes"].insert(0, NOTE.format(when=when))
    return data


def build(demo) -> dict:
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    token = privacy.OWNER.set("demo-builder")
    try:
        case, events = record(lambda: main._create(demo.input))
        stages = [{"supplement": None, "events": events, "case": frozen(case, when)}]
        problems = failed_items(case)
        for sup in demo.supplements:
            case, events = record(lambda: main._supplement(case, sup))
            stages.append({"supplement": sup.model_dump(mode="json"), "events": events, "case": frozen(case, when)})
            problems += failed_items(case)
    finally:
        privacy.OWNER.reset(token)
    return {"demo_id": demo.id, "label": demo.label, "built_at": when,
            "material_pipeline": demo_prebuilt.MATERIAL_PIPELINE,
            "input": demo.input.model_dump(mode="json"), "stages": stages, "problems": problems}


def run(ids: list[str]) -> int:
    demo_prebuilt.DIR.mkdir(parents=True, exist_ok=True)
    bad = 0
    for demo in main._demo_cases():
        if not demo.ready or (ids and demo.id not in ids):
            continue
        t = time.monotonic()
        bundle = build(demo)
        path = demo_prebuilt.DIR / f"{demo.id}.json"
        if path.exists():
            backup = demo_prebuilt.DIR / "backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup.mkdir(parents=True, exist_ok=False)
            shutil.copy2(path, backup / path.name)
        path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
        versions = len(bundle["stages"])
        print(f"{demo.id} {demo.label}：{versions} 版，{time.monotonic() - t:.0f} 秒 → {path}")
        for p in bundle["problems"]:
            print(f"   没查成：{p}")
        bad += bool(bundle["problems"])
    return bad


if __name__ == "__main__":
    sys.exit(1 if run(sys.argv[1:]) else 0)

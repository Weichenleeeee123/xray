"""预制示例：演示用的几个案例，第一版报告和按顺序补充后的每一版都提前生成好。

现场点示例时直接交出预制好的案卷，按生成时的节奏回放研究过程（最长约 20 秒），不联网也能完整演示，
每次演示的报告也一字不差。输入改过任何一处（公司、需求、材料、场景），就走正常查询。

预制包由 tools/build_demo_bundles.py 生成，放在 data/demo_prebuilt/<示例 id>.json：
  {"demo_id", "built_at", "stages": [{"supplement": null | {kind, text, title}, "events": [...], "case": {...}}, ...]}
stages[0] 是第一版；stages[k] 是在 stages[k-1] 上按 demo_cases.json 里的第 k 条补充得到的。
包里有商业数据（企查查），默认不进 git；换机器要在那台机器上重新生成，或者手动拷过去。
"""
import json
import os
import re
import time
from pathlib import Path
from uuid import uuid4

from app import config, progress
from app.models import Case, CaseIn, PrebuiltProvenance, SupplementIn
from app.sources.licenses import normalize

DIR = Path(os.getenv("XRAY_DEMO_PREBUILT_DIR", config.DATA_DIR / "demo_prebuilt"))
REPLAY_CAP = 20.0   # 回放研究过程最长多少秒；生成时更久就按比例压缩


def enabled() -> bool:
    return os.getenv("XRAY_DEMO_PREBUILT", "1") == "1"


def _text(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "")


def _bundles() -> list[dict]:
    if not enabled() or not DIR.is_dir():
        return []
    out = []
    for path in sorted(DIR.glob("*.json")):
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
            if bundle.get("stages"):
                out.append(bundle)
        except (OSError, ValueError):
            continue   # 坏了的包当作没有，照常现查
    return out


def _same_input(body: CaseIn, first: dict) -> bool:
    built = first["case"]["case"]
    said = first.get("input") or built
    if normalize(body.company_name) != normalize(built["company_name"]):
        return False
    if _text(body.need) != _text(said.get("need")) or _text(body.material_text) != _text(said.get("material_text")):
        return False
    if body.scenario not in (None, first["case"]["scenario"]):
        return False
    # 表单可能已经从需求里认出了"替谁看""金额"：和生成时认出来的一样才算同一个示例
    if body.for_whom not in (None, built.get("for_whom")) or body.amount not in (None, built.get("amount")):
        return False
    return True


def for_create(body: CaseIn) -> dict | None:
    """和某个示例的输入一模一样（且没要求刷新数据源）就返回那个预制包。"""
    if body.refresh_sources:
        return None
    return next((b for b in _bundles() if _same_input(body, b["stages"][0])), None)


def for_supplement(case: Case, body: SupplementIn) -> tuple[dict, int] | None:
    """案卷正是预制的那一串、而且这条补充就是下一条预备好的补充，返回 (包, 下一阶段序号)。"""
    if body.refresh_sources or not case.versions or case.versions[-1].prebuilt is None:
        return None
    k = len(case.versions)
    for bundle in _bundles():
        if case.versions[-1].prebuilt.demo_id != bundle.get("demo_id"):
            continue
        stages = bundle["stages"]
        if k >= len(stages) or case.versions[-1].created_at != stages[k - 1]["case"]["versions"][-1]["created_at"]:
            continue
        nxt = stages[k].get("supplement") or {}
        if nxt.get("kind") == body.kind and _text(nxt.get("text")) == _text(body.text):
            return bundle, k
    return None


def replay(events: list[dict], cap: float = REPLAY_CAP) -> None:
    """把生成时记下的步骤事件按原来的节奏再发一遍。没有人在等进度（普通接口）就不等。"""
    if not progress.active():
        return
    steps = [e for e in events if e.get("type") == "step"]
    total = max((float(e.get("t") or 0) for e in steps), default=0.0)
    scale = min(1.0, cap / total) if total else 1.0
    start = time.monotonic()
    for event in steps:
        wait = float(event.get("t") or 0) * scale - (time.monotonic() - start)
        if wait > 0:
            time.sleep(wait)
        progress.emit({k: v for k, v in event.items() if k != "t"})


def _provenance(bundle: dict) -> PrebuiltProvenance:
    # 只从服务端预制包取白名单字段，不转发输入或录制事件里的任意元数据。
    return PrebuiltProvenance(demo_id=bundle.get("demo_id"), built_at=bundle.get("built_at"))


def _replay_stage(stage: dict, provenance: PrebuiltProvenance) -> None:
    # 在任何回放等待和 step 前说明来源；保存案卷仍是当前请求真实执行的操作。
    progress.emit({"type": "prebuilt", **provenance.model_dump()})
    replay(stage.get("events") or [])


def start_case(bundle: dict, owner: str | None) -> Case:
    """第一版：回放研究过程，交出一份新案卷（新编号，属于当前浏览器）。"""
    stage = bundle["stages"][0]
    case = Case.model_validate(stage["case"])
    provenance = _provenance(bundle)
    for version in case.versions:
        version.prebuilt = provenance.model_copy()
    case.id, case.owner_id, case.revision, case.chat = uuid4().hex[:12], owner, 0, []
    _replay_stage(stage, provenance)
    return case


def next_case(case: Case, bundle: dict, k: int) -> Case:
    """只追加预制下一版及新增原始记录，保留已保存的版本、出处和对话。"""
    stage = bundle["stages"][k]
    built = Case.model_validate(stage["case"])
    if k != len(case.versions) or len(built.versions) != k + 1 or built.current != k + 1:
        raise ValueError("预制阶段与当前版本历史不一致")
    old_raw = {record.id: record for record in case.raw}
    added = []
    seen = set()
    for record in built.raw:
        if record.id in seen or (record.id in old_raw and old_raw[record.id] != record):
            raise ValueError("预制包的原始记录与已保存出处冲突")
        seen.add(record.id)
        if record.id not in old_raw:
            added.append(record)
    version = built.versions[-1]
    if version.no != k + 1 or not set(version.raw_ids) <= old_raw.keys() | seen:
        raise ValueError("预制版本的原始记录引用不完整")
    provenance = _provenance(bundle)
    version.prebuilt = provenance
    built.versions = [v.model_copy(deep=True) for v in case.versions] + [version]
    built.raw = [r.model_copy(deep=True) for r in case.raw] + added
    built.id, built.owner_id, built.revision, built.chat = case.id, case.owner_id, case.revision, case.chat
    built.created_at = case.created_at
    _replay_stage(stage, provenance)
    return built

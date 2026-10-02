"""边查边发进度（给等待动画用）：每一步都有 start 和 done，done 写真实结果，最后一行是案卷。"""
import json

from fastapi.testclient import TestClient

import app.main as main
from app import progress
from app.assistant import VERDICT_WORDS
from tests.helpers import DEMO_COMPANY, SAVINGS_NEED

client = TestClient(main.app)
REAL = "杭州巨鲸财富管理有限公司"   # 真实公司：有证据包（两份监管文书），中基协名单里有它


def stream(url: str, body: dict) -> list[dict]:
    r = client.post(url, json=body)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


def steps_done(events: list[dict]) -> dict[str, dict]:
    return {e["id"]: e for e in events if e["type"] == "step" and e["phase"] == "done"}


def check_shape(events: list[dict]) -> None:
    """begin 列出的每一步都按顺序先 start 后 done，各一次；中间不插别的步骤；最后一行是案卷。"""
    assert events[0]["type"] == "begin" and events[-1]["type"] == "case"
    planned = [s["id"] for s in events[0]["steps"]]
    seq = [(e["id"], e["phase"]) for e in events if e["type"] == "step"]
    assert seq == [(s, p) for s in planned for p in ("start", "done")]
    ts = [e["t"] for e in events]
    assert ts == sorted(ts)


def test_create_stream_for_fictional_company():
    events = stream("/api/cases/stream", {"company_name": DEMO_COMPANY, "need": SAVINGS_NEED})
    check_shape(events)
    assert [s["id"] for s in events[0]["steps"]] == list(progress.STEPS)
    done = steps_done(events)
    assert done["intake"]["text"].startswith("识别为：") and "20 万" in done["intake"]["text"]
    assert done["intake"]["coverage"] is None                        # 处理步骤不带"查没查到"
    assert done["lists"]["coverage"] == "not_found" and done["lists"]["text"].endswith("都没有它")
    assert done["registry"]["coverage"] == "found" and "演示数据" in done["registry"]["text"]
    assert done["pack"]["coverage"] == "not_covered"
    assert done["rules"]["text"].startswith("做了") or done["rules"]["text"].startswith("对照了")
    assert done["plain"]["text"] == "没用模型，报告用规则原句"     # 测试里模型关着，照实说
    case = events[-1]["case"]
    assert client.get(f"/api/cases/{case['id']}").json() == case    # 流里给的就是存下的案卷


def test_create_stream_for_real_company_reports_real_results():
    done = steps_done(stream("/api/cases/stream", {"company_name": REAL, "need": SAVINGS_NEED}))
    assert done["lists"]["counts"]["not_found"] == sum(done["lists"]["counts"].values())
    assert done["amac"]["coverage"] == "found" and "P1021593" in done["amac"]["text"]
    assert done["registry"]["coverage"] == "not_covered" and "公示系统" in done["registry"]["text"]
    assert done["pack"]["coverage"] == "found" and done["pack"]["text"].startswith("2 份")
    # 没配网关就没联网搜：照样有 done，写明为什么没搜，不悄悄跳过
    assert done["web"]["coverage"] == "not_covered" and done["web"]["text"].startswith("没联网搜")
    assert done["reviews"]["coverage"] == "not_found"


def test_progress_texts_do_not_judge():
    events = stream("/api/cases/stream", {"company_name": REAL, "need": SAVINGS_NEED})
    events += stream("/api/cases/stream", {"company_name": DEMO_COMPANY, "need": SAVINGS_NEED})
    for e in events:
        if e["type"] == "step" and e["phase"] == "done":
            assert not VERDICT_WORDS.search(e["text"]) and not any(w in e["text"] for w in ("有问题", "风险", "可疑")), e


def test_supplement_stream():
    case = client.post("/api/cases", json={"company_name": DEMO_COMPANY, "need": SAVINGS_NEED}).json()
    events = stream(f"/api/cases/{case['id']}/supplements/stream", {"kind": "material", "text": "年化收益 9%，保本保息"})
    check_shape(events)
    assert "intake" not in [s["id"] for s in events[0]["steps"]]       # 补材料不重新识别需求
    assert events[0]["kind"] == "supplement" and events[-1]["case"]["current"] == 2
    events = stream(f"/api/cases/{case['id']}/supplements/stream", {"kind": "need", "text": "其实是替我爸看，30 万"})
    check_shape(events)
    assert events[0]["steps"][0]["id"] == "intake" and events[-1]["case"]["current"] == 3


def test_supplement_stream_unknown_case_is_plain_404():
    r = client.post("/api/cases/nope/supplements/stream", json={"kind": "material", "text": "随便写点什么"})
    assert r.status_code == 404


def test_failure_ends_the_stream_with_an_error(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("boom")
    monkeypatch.setattr(main, "new_case", boom)
    events = stream("/api/cases/stream", {"company_name": DEMO_COMPANY, "need": SAVINGS_NEED})
    assert events[-1]["type"] == "error" and events[-1]["status"] == 500
    assert "boom" not in events[-1]["message"]                           # 不把内部异常原文给前端


def test_no_receiver_means_no_events():
    progress.start("lists")                                              # 普通接口：没有接收者，什么都不做
    progress.done("lists", [])
    got = []
    with progress.reporting(got.append):
        progress.skip("web", "没联网搜")
    assert [(e["phase"], e.get("coverage")) for e in got] == [("start", None), ("done", "not_covered")]


def rec(source_id: str, coverage: str, kind: str = "official", **kw):
    from app.models import RawRecord
    return RawRecord(id="", source_id=source_id, title=kw.pop("title", source_id), kind=kind, coverage=coverage,
                     retrieved_at="2026-10-02T12:00:00", **kw)


def test_done_texts_follow_the_records():
    got = []
    with progress.reporting(got.append):
        progress.done("web", [rec("web_official", "found"), rec("web_official", "found"), rec("web_news", "failed")])
        progress.done("web", [rec("web_official", "not_found"), rec("web_news", "not_found")])
        progress.done("registry", [rec("registry", "found", kind="commercial")])
        progress.done("registry", [rec("registry", "failed", kind="commercial")])
        progress.done("lists", [rec("nfra_bank_list", "found", title="银行业金融机构法人名单 · 按名称查询"),
                                rec("pbc_payment", "not_found")])
    assert [(e["coverage"], e["text"]) for e in got] == [
        ("found", "搜到政府网站页面 2 个"),     # 页面数，不说成"点名它的文件"
        ("not_found", "搜了，没找到点名它的页面"),
        ("found", "查到登记信息（企查查商业数据）"),
        ("failed", "没查成（企查查商业数据）"),
        ("found", "2 份名单里，银行业金融机构法人名单有它")]
    assert got[0]["counts"] == {"found": 2, "not_found": 0, "not_covered": 0, "failed": 0}  # web_news 归舆情那步

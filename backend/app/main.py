"""X-Ray 后端。

运行：cd backend && .venv\\Scripts\\python -m uvicorn app.main:app --port 8000
打开：http://localhost:8000（前端 web/）　接口文档：http://localhost:8000/docs　断网备用：/demo/
"""
import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from uuid import uuid4
from collections.abc import Callable

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import config, progress, runs
from app.analysis.pipeline import NoNewReviews, load_services, new_case, refresh_reviews, resolve, supplement
from app.analysis.report import onepager
from app.assistant import answer
from app.glossary import load_glossary
from app.intake import run_intake
from app.llm import LLM
from app.plain import finish_version
from app.models import (Case, CaseIn, CaseSummary, ChatIn, ChatMessage, Intake, IntakeIn, LicenseHit, OnePager,
                        ReadResult, ResolveIn, ReviewIn, ReviewList, Scenario, Source, SupplementIn, Term)
from app.readers import read_upload
from app.reviews import DuplicateReview
from app.scenarios import get_scenario, load_scenarios
from app.sources.collect import collect
from app.store import CaseStore

MAX_UPLOAD = 15 * 1024 * 1024
DEMO_CASES = config.DATA_DIR / "demo_cases.json"

log = logging.getLogger("xray")
svc = load_services()
llm = LLM()
store = CaseStore(config.CASES_DIR)

app = FastAPI(title="X-Ray 透视·真相", version="0.2.0")
RUNS_DIR = Path(os.getenv("XRAY_RUNS_DIR", config.DATA_DIR / "runs"))
_active_runs: set[str] = set()
_active_lock = threading.Lock()
# 前端由本服务同源提供；放开跨域只是方便有人单独起前端调试
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _case(case_id: str) -> Case:
    case = store.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="案卷不存在")
    return case


@app.get("/api/health")
def health() -> dict:
    lists = {rid: {"title": i.title, "count": i.meta.get("count", len(i)), "as_of": i.meta.get("as_of")}
             for rid, i in svc.registries.items()}
    return {"ok": True, "licensed_count": len(svc.licenses), "licensed_as_of": svc.licenses.meta["as_of"],
            "registry_as_of": svc.registry.as_of, "official_lists": lists, "evidence_packs": svc.packs.names(),
            "commercial": svc.commercial.status() if svc.commercial else {"configured": False},
            "llm": llm.status()}


@app.get("/api/sources")
def sources() -> list[Source]:
    return list(svc.sources.values())


@app.get("/api/scenarios")
def scenarios() -> list[Scenario]:
    return list(load_scenarios().values())


@app.get("/api/glossary")
def glossary() -> list[Term]:
    return list(load_glossary())


@app.post("/api/intake")
def intake(body: IntakeIn) -> Intake:
    return run_intake(body.need, llm, company=body.company_name)


@app.post("/api/read")
async def read_file(file: UploadFile = File(...)) -> ReadResult:
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="文件超过 15MB")
    return read_upload(file.filename or "", data, llm)


@app.get("/api/licenses/check")
def check_license(name: str = Query(min_length=2, description="机构全称；输入简称会返回候选")) -> LicenseHit:
    return svc.licenses.lookup(name)


@app.get("/api/companies/profile")
def company_profile(name: str = Query(min_length=2)) -> dict:
    c = collect(name, svc)
    return {"covered": c.company is not None, "company": c.company, "license": c.license, "amac": c.amac,
            "records": c.records}


def _intake(text: str, scenario: str | None, company: str) -> Intake:
    progress.start("intake")
    info = run_intake(text, llm, scenario=scenario, company=company)
    progress.done("intake", text=progress.intake_text(info))
    return info


def _create(body: CaseIn) -> Case:
    info = _intake(body.need, body.scenario, body.company_name)
    return store.save(finish_version(new_case(body, info, svc), llm))


def _supplement(case: Case, body: SupplementIn) -> Case:
    info = _intake(body.text, body.scenario, case.case.company_name) if body.kind == "need" else None
    return store.save(finish_version(supplement(case, body, info, svc), llm))


def _stream(first: dict, work: Callable[[], Case]) -> StreamingResponse:
    """边做边发进度：一行一个 JSON（NDJSON）。begin → 各步 start/done → 最后一行 case（整个案卷）或 error。

    t 是从收到请求起的秒数。活在后台线程里做，客户端中途断开也会做完、存好案卷。
    """
    events: queue.Queue = queue.Queue()
    t0 = time.monotonic()

    def put(event: dict) -> None:
        events.put({**event, "t": round(time.monotonic() - t0, 2)})

    def run() -> None:
        try:
            with progress.reporting(put):
                case = work()
            put({"type": "case", "case": case.model_dump(mode="json")})
        except HTTPException as e:
            put({"type": "error", "status": e.status_code, "message": str(e.detail)})
        except Exception:  # noqa: BLE001 —— 出错要告诉前端，不能让流悄悄断掉
            log.exception("stream failed")
            put({"type": "error", "status": 500, "message": "生成失败，请重试；多次失败请查看后端日志"})
        finally:
            events.put(None)

    put(first)
    threading.Thread(target=run, daemon=True).start()

    def lines():
        while (event := events.get()) is not None:
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _start_run(first: dict, work: Callable[[], Case], original_input: dict | None = None) -> dict:
    """Launch a case build and retain progress independently of the browser connection."""
    run_id = uuid4().hex[:24]
    started = time.monotonic()
    if original_input is not None:
        runs.save_input(RUNS_DIR, run_id, original_input)

    def put(event: dict) -> None:
        runs.append(RUNS_DIR, run_id, {**event, "t": round(time.monotonic() - started, 2)})

    with _active_lock:  # 先登记再写第一条，免得查询时看到"没在跑、也没结束"
        _active_runs.add(run_id)
    put(first)

    def run() -> None:
        try:
            with progress.reporting(put):
                case = work()
            put({"type": "complete", "case_id": case.id, "version": case.current})
        except Exception:  # noqa: BLE001 - raw provider errors stay in server logs
            log.exception("run failed")
            put({"type": "error", "message": "生成失败，请重试；如页面中断，先到案卷列表确认结果"})
        finally:
            with _active_lock:
                _active_runs.discard(run_id)

    threading.Thread(target=run, daemon=True).start()
    return {"run_id": run_id, "status": "running"}


@app.post("/api/runs", status_code=202)
def create_run(body: CaseIn) -> dict:
    return _start_run(progress.begin("create", body.company_name, intake=True), lambda: _create(body),
                      {"kind": "create", "body": body.model_dump(mode="json")})


@app.post("/api/cases/{case_id}/runs", status_code=202)
def supplement_run(case_id: str, body: SupplementIn) -> dict:
    case = _case(case_id)
    return _start_run(progress.begin("supplement", case.case.company_name, intake=body.kind == "need"),
                      lambda: _supplement(case, body),
                      {"kind": "supplement", "case_id": case_id, "body": body.model_dump(mode="json")})


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, after: int = Query(0, ge=0)) -> dict:
    try:
        all_events = runs.events(RUNS_DIR, run_id)
    except ValueError:
        all_events = None
    if all_events is None:
        raise HTTPException(status_code=404, detail="研究任务不存在")
    terminal = next((e for e in reversed(all_events) if e.get("type") in ("complete", "error")), None)
    with _active_lock:
        active = run_id in _active_runs
    status = ("complete" if terminal["type"] == "complete" else "error") if terminal else ("running" if active else "interrupted")
    return {"run_id": run_id, "status": status, "case_id": terminal.get("case_id") if terminal else None,
            "version": terminal.get("version") if terminal else None,
            "input": runs.read_input(RUNS_DIR, run_id) if after == 0 else None,
            "events": all_events[after:], "next": len(all_events)}


@app.post("/api/cases")
def create_case(body: CaseIn) -> Case:
    return _create(body)


@app.post("/api/cases/stream")
def create_case_stream(body: CaseIn) -> StreamingResponse:
    """同 /api/cases，但边查边发进度，给等待动画用。事件格式见 docs/progress-events.md。"""
    return _stream(progress.begin("create", body.company_name, intake=True), lambda: _create(body))


@app.get("/api/cases")
def list_cases() -> list[CaseSummary]:
    return store.list()


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> Case:
    return _case(case_id)


@app.post("/api/cases/{case_id}/supplements")
def add_supplement(case_id: str, body: SupplementIn) -> Case:
    return _supplement(_case(case_id), body)


@app.post("/api/cases/{case_id}/supplements/stream")
def add_supplement_stream(case_id: str, body: SupplementIn) -> StreamingResponse:
    """同 /supplements，但边查边发进度。案卷不存在照常回 404，不开流。"""
    case = _case(case_id)
    return _stream(progress.begin("supplement", case.case.company_name, intake=body.kind == "need"),
                   lambda: _supplement(case, body))


@app.post("/api/cases/{case_id}/resolve")
def resolve_judgment(case_id: str, body: ResolveIn) -> Case:
    """人对某条判断下结论（已澄清 / 已撤回 / 继续查）。出一版新案卷，旧版留着。"""
    case = _case(case_id)
    try:
        return store.save(resolve(case, body))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"案卷里没有这条判断：{body.judgment_id}") from None


@app.post("/api/cases/{case_id}/reviews")
def refresh_case_reviews(case_id: str) -> Case:
    """把这家公司最新的用户评价放进案卷，出一版新报告。评价没变就不出。"""
    case = _case(case_id)
    try:
        return store.save(finish_version(refresh_reviews(case, svc), llm))
    except NoNewReviews:
        raise HTTPException(status_code=409, detail="没有新评价：这一版报告里已经是最新的评价") from None


# ---------- 用户评价：按公司存，别人说的，未核实 ----------

@app.get("/api/reviews")
def list_reviews(company: str = Query(..., min_length=2, max_length=80),
                 author: str | None = Query(None, description="浏览器的匿名编号，用来标出哪条是自己写的")) -> ReviewList:
    return svc.reviews.listing(company.strip(), author)


@app.post("/api/reviews")
def add_review(body: ReviewIn) -> ReviewList:
    try:
        return svc.reviews.add(body)
    except DuplicateReview:
        raise HTTPException(status_code=409, detail="你已经给这家公司写过一条评价了") from None


@app.post("/api/cases/{case_id}/chat")
def chat(case_id: str, body: ChatIn) -> ChatMessage:
    case = _case(case_id)
    reply = answer(case, body, llm, version_no=body.version)
    case.chat += [ChatMessage(role="user", text=body.text, refs=body.refs, version=reply.version,
                              created_at=reply.created_at), reply]
    store.save(case)
    return reply


@app.get("/api/cases/{case_id}/onepager")
def get_onepager(case_id: str, audience: str = Query("family", pattern="^(family|teller)$"),
                 version: int | None = None) -> OnePager:
    case = _case(case_id)
    v = next((x for x in case.versions if x.no == version), None) if version else case.versions[-1]
    if v is None:
        raise HTTPException(status_code=404, detail="没有这个版本")
    return onepager(company_name=case.case.company_name, for_whom=v.for_whom, amount=v.amount,
                    scenario=get_scenario(v.scenario), assertions=v.assertions, missing=v.missing, signals=v.signals,
                    questions=v.questions, sources=case.sources, audience=audience)


# ---------- 演示案例 ----------

class DemoCase(BaseModel):
    id: str
    label: str
    real: bool
    ready: bool
    note: str | None = None
    input: CaseIn | None = None
    supplements: list[SupplementIn] = []


def _demo_cases() -> list[DemoCase]:
    raw = json.loads(DEMO_CASES.read_text(encoding="utf-8"))["cases"]
    out = []
    for d in raw:
        inp, sups = None, []
        if d.get("ready"):
            material = (config.FIXTURES_DIR / d["material_file"]).read_text(encoding="utf-8") if d.get("material_file") else None
            inp = CaseIn(**d["input"], material_text=material, material_title=d.get("material_title"))
            for s in d.get("supplements", []):
                text = (config.FIXTURES_DIR / s["file"]).read_text(encoding="utf-8") if s.get("file") else s["text"]
                sups.append(SupplementIn(kind=s["kind"], text=text, title=s.get("title")))
        out.append(DemoCase(id=d["id"], label=d["label"], real=d["real"], ready=d.get("ready", False),
                            note=d.get("note"), input=inp, supplements=sups))
    return out


@app.get("/api/demo/cases")
def demo_cases() -> list[DemoCase]:
    return _demo_cases()


@app.get("/api/demo")
def demo_case(case: str | None = Query(None, description="A / B / C；不填取第一个准备好的")) -> DemoCase:
    cases = _demo_cases()
    pick = next((c for c in cases if c.id == case), None) if case else next((c for c in cases if c.ready), None)
    if pick is None:
        raise HTTPException(status_code=404, detail="没有这个演示案例")
    if not pick.ready:
        raise HTTPException(status_code=409, detail=f"演示案例 {pick.id} 还没准备好：{pick.note or ''}")
    return pick


# ---------- 静态页面：放在最后，避免盖住 /api ----------

research_assets = config.REPO_DIR / "research-room" / "public"
if research_assets.exists():
    app.mount("/research-assets", StaticFiles(directory=research_assets), name="research-assets")
if config.DEMO_DIR.exists():
    app.mount("/demo", StaticFiles(directory=config.DEMO_DIR, html=True), name="demo")
if config.WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
else:
    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")  # 前端 web/ 还没建好时，先给接口文档

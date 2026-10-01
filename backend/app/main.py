"""X-Ray 后端。

运行：cd backend && .venv\\Scripts\\python -m uvicorn app.main:app --port 8000
打开：http://localhost:8000（前端 web/）　接口文档：http://localhost:8000/docs　断网备用：/demo/
"""
import json

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import config
from app.analysis.pipeline import load_services, new_case, supplement
from app.analysis.report import onepager
from app.assistant import answer
from app.glossary import load_glossary
from app.intake import run_intake
from app.llm import LLM
from app.plain import finish_version
from app.models import (Case, CaseIn, CaseSummary, ChatIn, ChatMessage, Intake, IntakeIn, LicenseHit, OnePager,
                        ReadResult, Scenario, Source, SupplementIn, Term)
from app.readers import read_upload
from app.scenarios import get_scenario, load_scenarios
from app.sources.collect import collect
from app.store import CaseStore

MAX_UPLOAD = 15 * 1024 * 1024
DEMO_CASES = config.DATA_DIR / "demo_cases.json"

svc = load_services()
llm = LLM()
store = CaseStore(config.CASES_DIR)

app = FastAPI(title="X-Ray 透视·真相", version="0.2.0")
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


@app.post("/api/cases")
def create_case(body: CaseIn) -> Case:
    info = run_intake(body.need, llm, scenario=body.scenario, company=body.company_name)
    return store.save(finish_version(new_case(body, info, svc), llm))


@app.get("/api/cases")
def list_cases() -> list[CaseSummary]:
    return store.list()


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> Case:
    return _case(case_id)


@app.post("/api/cases/{case_id}/supplements")
def add_supplement(case_id: str, body: SupplementIn) -> Case:
    case = _case(case_id)
    info = run_intake(body.text, llm, scenario=body.scenario, company=case.case.company_name) if body.kind == "need" else None
    return store.save(finish_version(supplement(case, body, info, svc), llm))


@app.post("/api/cases/{case_id}/chat")
def chat(case_id: str, body: ChatIn) -> ChatMessage:
    case = _case(case_id)
    reply = answer(case, body, llm)
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

if config.DEMO_DIR.exists():
    app.mount("/demo", StaticFiles(directory=config.DEMO_DIR, html=True), name="demo")
if config.WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
else:
    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")  # 前端 web/ 还没建好时，先给接口文档

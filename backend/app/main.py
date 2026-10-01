"""X-Ray 后端：前期数据获取与分析。

运行：.venv\\Scripts\\python -m uvicorn app.main:app --port 8000 --reload
接口文档：http://localhost:8000/docs
"""
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.analysis.pipeline import analyze, load_services
from app.config import FIXTURES_DIR
from app.models import AmacHit, CaseIn, CaseOut, CompanyProfile, LicenseHit, Source
from app.sources.licenses import normalize

DEMO_COMPANY = "杭州满盈禾康养健康咨询有限公司"
DEMO_FLYERS = {normalize(DEMO_COMPANY): FIXTURES_DIR / "flyers" / "manyinghe.txt"}

svc = load_services()
cases: dict[str, CaseOut] = {}  # 演示用内存存储，重启即清空

app = FastAPI(title="X-Ray 透视·真相", version="0.1.0")
# 前端可能直接双击打开（file://）或跑在 5178 端口，演示期间放开跨域
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "licensed_count": len(svc.licenses), "licensed_as_of": svc.licenses.meta["as_of"],
            "registry_as_of": svc.registry.as_of}


@app.get("/api/sources")
def sources() -> list[Source]:
    return list(svc.sources.values())


@app.get("/api/licenses/check")
def check_license(name: str = Query(min_length=2, description="机构全称；输入简称会返回候选")) -> LicenseHit:
    return svc.licenses.lookup(name)


@app.get("/api/companies/profile")
def company_profile(name: str = Query(min_length=2)) -> dict:
    company: CompanyProfile | None = svc.registry.get(name)
    amac: AmacHit = svc.amac.lookup(name)
    return {"covered": company is not None, "company": company, "license": svc.licenses.lookup(name), "amac": amac}


@app.get("/api/demo")
def demo_case() -> CaseIn:
    flyer = DEMO_FLYERS[normalize(DEMO_COMPANY)].read_text(encoding="utf-8")
    return CaseIn(company_name=DEMO_COMPANY, for_whom="妈妈", amount=200000,
                  concern="急用的时候，能不能随时拿回来", flyer_text=flyer)


@app.post("/api/cases")
def create_case(body: CaseIn) -> CaseOut:
    if body.flyer_text is None and (path := DEMO_FLYERS.get(normalize(body.company_name))):
        body = body.model_copy(update={"flyer_text": path.read_text(encoding="utf-8")})
    result = analyze(body, svc, uuid4().hex[:12])
    cases[result.id] = result
    return result


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> CaseOut:
    if case_id not in cases:
        raise HTTPException(status_code=404, detail="案卷不存在（演示版存在内存里，服务重启后会清空）")
    return cases[case_id]

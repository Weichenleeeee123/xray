from app.analysis.pipeline import load_services, new_case, supplement
from app.config import FIXTURES_DIR
from app.models import CaseIn, SupplementIn
from app.scenarios import keyword_intake

svc = load_services()
DEMO_COMPANY = "杭州满盈禾康养健康咨询有限公司"
SAVINGS_NEED = "我妈想在这家公司存 20 万理财，最怕急用时取不出来"


def flyer(name: str) -> str:
    return (FIXTURES_DIR / "flyers" / name).read_text(encoding="utf-8")


def make_case(company: str, text: str | None = None, need: str = SAVINGS_NEED):
    return new_case(CaseIn(company_name=company, need=need, material_text=text), keyword_intake(need), svc)


def run(company: str, text: str, need: str = ""):
    """只看第一版报告。"""
    return make_case(company, text, need).versions[0]


def add(case, kind: str, text: str):
    intake = keyword_intake(text) if kind == "need" else None
    return supplement(case, SupplementIn(kind=kind, text=text), intake, svc)

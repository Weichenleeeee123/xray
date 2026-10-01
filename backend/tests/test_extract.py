from app.analysis.extract import RuleExtractor
from app.config import FIXTURES_DIR
from app.models import ClaimKind

DEMO = (FIXTURES_DIR / "flyers" / "manyinghe.txt").read_text(encoding="utf-8")
extract = RuleExtractor().extract
demo = extract(DEMO)


def test_demo_flyer_has_the_six_original_claim_kinds():
    assert set(demo.claims) == {ClaimKind.qualification, ClaimKind.return_promise, ClaimKind.partner,
                                ClaimKind.background, ClaimKind.capital, ClaimKind.scale}


def test_demo_numbers():
    assert demo.claims[ClaimKind.return_promise].numbers["annual_rate"] == 9.0
    assert demo.claims[ClaimKind.capital].numbers["capital"] == 50_000_000
    assert demo.claims[ClaimKind.scale].numbers == {"stores": 30, "members": 100_000}


def test_demo_guarantee_words_and_vague_bank():
    assert demo.claims[ClaimKind.return_promise].words == ["保本", "保息", "还本付息"]
    assert demo.claims[ClaimKind.partner].banks == ["某大型银行"]


def test_demo_missing_disclosure_and_pressure():
    assert demo.is_financial
    assert not demo.has_risk_disclosure
    assert demo.pressure == ["名额有限", "先到先得"]


def test_negated_guarantee_is_not_a_promise():
    ext = extract("非保本浮动收益型\n业绩比较基准 2.8%\n理财非存款、产品有风险、投资须谨慎\n本产品不承诺保本")
    assert ClaimKind.return_promise not in ext.claims
    assert ext.benchmark_rates == [2.8]
    assert ext.has_bank_wm_disclosure


def test_rate_split_across_two_lines():
    ext = extract("超值回报 年化\n12%")
    assert ext.claims[ClaimKind.return_promise].numbers["annual_rate"] == 12.0


def test_product_code_detected():
    ext = extract("产品登记编码：Z7003026000123")
    assert ext.product_codes == ["Z7003026000123"]


def test_ordinary_business_flyer_is_not_financial():
    ext = extract("明澄家政 · 专业保洁\n全国 3 家门店 · 服务 2 万家庭")
    assert not ext.is_financial
    assert set(ext.claims) == {ClaimKind.scale}

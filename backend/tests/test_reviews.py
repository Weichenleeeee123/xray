"""用户评价：按公司存；别人说的，未核实。只让人多留意，不让人放心；不让助手借评价说出定性词。"""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.analysis.pipeline import NoNewReviews, new_case, refresh_reviews
from app.analysis.signals import review_item
from app.assistant import citable, evidence_text, overreach
from app.config import FIXTURES_DIR
from app.main import app
from app.models import CaseIn, ReviewIn, Status
from app.reviews import DuplicateReview, ReviewStore, redact, review_record
from app.scenarios import keyword_intake
from tests.helpers import DEMO_COMPANY, SAVINGS_NEED, flyer, svc

FAKE = "杭州某某虚构评价测试有限公司"   # 没有任何数据的虚构名字，只用来写评价
SEED = FIXTURES_DIR / "reviews.json"


def body(stars=1, text="说好随时能取，要取的时候业务员一直拖着不给办。", author="browser-0001", company=FAKE, **kw):
    return ReviewIn(company=company, stars=stars, relation="customer", text=text, author=author, **kw)


def store(tmp_path, seed=None):
    return ReviewStore(tmp_path / "reviews", seed)


def make(company, reviews: ReviewStore, text=None):
    return new_case(CaseIn(company_name=company, need=SAVINGS_NEED, material_text=text), keyword_intake(SAVINGS_NEED),
                    replace(svc, reviews=reviews))


# ---------- 存储 ----------

def test_personal_info_is_redacted_before_saving(tmp_path):
    s = store(tmp_path)
    got = s.add(body(text="业务员电话 138 1234 5678，身份证 330102199001011234，住址：某某小区 3 幢", nickname="13812345678"))
    r = got.reviews[0]
    assert "1234 5678" not in r.text and "330102199001011234" not in r.text and "某某小区" not in r.text
    assert "（电话略）" in r.text and r.nickname == "（电话略）"
    assert redact("年化 9% 稳赚，存 20 万") == "年化 9% 稳赚，存 20 万"   # 普通数字不动


def test_one_review_per_browser_per_company_and_author_is_never_returned(tmp_path):
    s = store(tmp_path)
    got = s.add(body())
    assert got.count == 1 and got.reviews[0].mine and got.dist == {"5": 0, "4": 0, "3": 0, "2": 0, "1": 1}
    with pytest.raises(DuplicateReview):
        s.add(body(stars=5, text="第二次写，换个说法也不行，同一个浏览器只能一条。"))
    s.add(body(stars=5, author="browser-0002", text="另一个浏览器写的，可以。客户经理很热情。"))
    other = s.listing(FAKE, "browser-0002")
    assert other.count == 2 and [r.mine for r in other.reviews] == [True, False]
    assert "author" not in other.model_dump_json() and "browser-0001" not in (tmp_path / "reviews").joinpath(
        next(p.name for p in (tmp_path / "reviews").iterdir())).read_text(encoding="utf-8")


def test_validation_rejects_bad_input():
    for bad in ({"stars": 0}, {"stars": 6}, {"text": "太短了"}, {"text": "字" * 501}, {"author": "x"}):
        with pytest.raises(ValueError):
            ReviewIn(**({"company": FAKE, "stars": 3, "relation": "customer", "text": "十个字以上的一条评价内容。",
                         "author": "browser-0001"} | bad))


def test_demo_reviews_only_for_the_fictional_company(tmp_path):
    s = store(tmp_path, SEED)
    demo = s.listing(DEMO_COMPANY)
    assert demo.count == 7 and all(r.demo for r in demo.reviews)
    assert demo.reviews[0].created_at > demo.reviews[-1].created_at          # 新的在前
    for real in ("杭州巨鲸财富管理有限公司", "杭州银行股份有限公司"):
        assert s.listing(real).count == 0                                   # 不给真实公司编评价


# ---------- 规则：只让人多留意，不让人放心 ----------

def stars(*xs):
    return [{"stars": x} for x in xs]


def test_review_rule_never_green_never_bad():
    assert review_item([]) is None and review_item(None) is None
    few = review_item(stars(1, 1))
    assert few.status is Status.none and "太少" in few.detail
    assert review_item(stars(1, 2, 5)).status is Status.warn                # 3 条里 2 条差评
    assert review_item(stars(1, 1, 5, 5)).status is Status.warn             # 正好一半也算集中
    praise = review_item(stars(5, 5, 5, 5, 5, 5))
    assert praise.status is Status.none and "不代表没问题" in praise.detail    # 好评再多也不标绿
    worst = review_item(stars(*[1] * 20))
    assert worst.status is Status.warn and worst.value == "20 条：1 星 20 条"  # 差评再多也不到"有问题"


def test_review_snapshot_has_no_author_and_is_reused_when_unchanged(tmp_path):
    s = store(tmp_path)
    s.add(body())
    rec = review_record(s.all(FAKE))
    assert rec.source_id == "user_reviews" and rec.kind == "user_review" and rec.title == "用户评价（1 条）"
    assert set(rec.content[0]) == {"星级", "身份", "评价", "昵称", "日期"} and rec.content[0]["昵称"] == "匿名用户"
    assert review_record([]) is None


# ---------- 进报告 ----------

def test_reviews_enter_the_reputation_signal_but_not_the_onepager(tmp_path):
    case = make(DEMO_COMPANY, store(tmp_path, SEED), flyer("manyinghe.txt"))
    v = case.versions[-1]
    raw = next(r for r in case.raw if r.source_id == "user_reviews")
    assert raw.id in v.raw_ids and raw.coverage.value == "found" and "演示数据" in raw.note
    item = next(i for s in v.signals if s.key == "reputation" for i in s.items if i.key == "user_reviews")
    assert item.status is Status.warn and item.ref == raw.id and item.label == "用户评价（未核实）"
    page = " ".join(line.text for col in (v.onepager.mismatch, v.onepager.found, v.onepager.unknown) for line in col)
    assert "用户评价" not in page and "骗子" not in page
    assert not any(j.target == "reputation.user_reviews" for j in v.judgments)


def test_no_reviews_no_record_no_item(tmp_path):
    case = make(FAKE, store(tmp_path))
    v = case.versions[-1]
    assert not any(r.source_id == "user_reviews" for r in case.raw)
    assert not any(i.key == "user_reviews" for s in v.signals for i in s.items)


def test_refresh_puts_new_reviews_into_a_new_version(tmp_path):
    s = store(tmp_path)
    case = make(FAKE, s)
    with pytest.raises(NoNewReviews):
        refresh_reviews(case, replace(svc, reviews=s))                     # 还没有评价
    for i in range(3):
        s.add(body(author=f"browser-000{i}", stars=1 if i < 2 else 5))
    case = refresh_reviews(case, replace(svc, reviews=s))
    v = case.versions[-1]
    assert v.no == 2 and v.trigger == "reviews" and v.trigger_label == "更新用户评价"
    assert v.change_summary.startswith("这一版放进了新写的用户评价：上一版 0 条，现在 3 条。")
    ch = next(c for c in v.changes if c.target == "reputation.user_reviews")
    assert ch.kind == "new_concern" and ch.because and ch.plain in v.change_summary
    s.add(body(author="browser-0009"))
    v = refresh_reviews(case, replace(svc, reviews=s)).versions[-1]          # 条数变了，状态没变
    assert "上一版 3 条，现在 4 条" in v.change_summary and "没变，仍是\"要留意（4 条" in v.change_summary
    with pytest.raises(NoNewReviews):
        refresh_reviews(case, replace(svc, reviews=s))                     # 没有新的，不再出一版


# ---------- 小企：不借评价说出定性词 ----------

def test_assistant_cannot_borrow_characterization_from_reviews(tmp_path):
    s = store(tmp_path)
    s.add(body(text="我看它就是非法集资，大家千万别投钱进去。"))
    case = make(FAKE, s)
    v = case.versions[-1]
    valid = citable(case, v)
    rid = next(r.id for r in case.raw if r.source_id == "user_reviews")
    assert "非法集资" in valid[rid]                                       # 评价原文可以引用
    assert overreach("它涉嫌非法集资。", evidence_text(case, valid)) == ["涉嫌非法集资"]


# ---------- 接口 ----------

client = TestClient(app)


def test_review_api_and_case_refresh():
    company = "杭州接口测试虚构有限公司"
    assert client.get("/api/reviews", params={"company": company}).json()["count"] == 0
    assert client.post("/api/reviews", json={"company": company, "stars": 7, "relation": "customer",
                                             "text": "十个字以上的一条评价内容。", "author": "browser-api1"}).status_code == 422
    case = client.post("/api/cases", json={"company_name": company, "need": SAVINGS_NEED}).json()
    assert client.post(f"/api/cases/{case['id']}/reviews").status_code == 409
    ok = client.post("/api/reviews", json={"company": company, "stars": 2, "relation": "applicant",
                                           "text": "面试时让先交 800 元培训费，说入职后退。", "author": "browser-api1"})
    assert ok.status_code == 200 and ok.json()["reviews"][0]["mine"] and ok.json()["reviews"][0]["relation_label"] == "求职者"
    again = client.post("/api/reviews", json={"company": company, "stars": 5, "relation": "other",
                                              "text": "再写一条试试看，应该被拦下来。", "author": "browser-api1"})
    assert again.status_code == 409
    got = client.post(f"/api/cases/{case['id']}/reviews")
    assert got.status_code == 200 and got.json()["versions"][-1]["trigger"] == "reviews"
    assert client.get("/api/sources").json() and any(s["id"] == "user_reviews" for s in client.get("/api/sources").json())

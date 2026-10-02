"""可追踪的判断：三层分离、依据带位置、五格变化、冲突并列保留、澄清与撤回。

这组测试盯的是产品最要紧的一条：报告只是某一版的样子，判断才是被追踪的东西。
系统不许把材料上的文字当成事实，不许只会加警告不会撤警告。
"""
import re

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import DEMO_COMPANY, add, make_case, run

PAY = """合同草案 V1 第六条：服务未使用时可以申请退款。
付款信息
收款户名：张某
开户行：中国银行深圳分行
金额：5800 元"""


def ids(v):
    return {j.id: j for j in v.judgments}


# ---------- 1. 三个东西不能混 ----------

def test_material_text_is_recorded_as_said_not_as_fact():
    v = add(make_case(DEMO_COMPANY), "material", PAY).versions[-1]
    j = ids(v)["said.A7"]
    assert j.layer == "said" and j.state_label == "照录"
    assert "张某" in j.text
    # 材料里写的，必须自己带着"这材料真不真还没确认"这一条未知
    assert any("真实" in u for u in j.unknown)


def test_inference_always_carries_premise_unknown_and_cannot():
    v = add(make_case(DEMO_COMPANY), "material", PAY).versions[-1]
    j = ids(v)["check.A7"]
    assert j.layer == "inferred" and j.state == "needs_check"
    assert j.premise and j.cannot
    # 不能由材料内容直接推出这些
    assert any("诈骗" in c for c in j.cannot)
    assert any("违法收款" in c for c in j.cannot)
    assert any("真实属于" in c for c in j.cannot)


def test_ocr_right_does_not_mean_screenshot_is_real():
    """报告口径里也不许写"钱进了别人的账户"这种把材料当事实的话。"""
    v = add(make_case(DEMO_COMPANY), "material", PAY).versions[-1]
    a = next(x for x in v.assertions if x.id == "A7")
    assert "钱进了别人的账户" not in a.plain
    assert "先核实" in a.plain or "核实" in a.plain


# ---------- 2. 判断要带依据和位置 ----------

def test_basis_points_back_into_the_material_with_a_locator():
    v = add(make_case(DEMO_COMPANY), "material", PAY).versions[-1]
    b = [x for x in ids(v)["said.A7"].basis if x.grade == "material"]
    assert b and any(x.locator and "第 3 行" in x.locator for x in b)


def test_every_judgment_has_scope_and_a_target():
    v = run(DEMO_COMPANY, PAY)
    assert v.judgments
    for j in v.judgments:
        assert j.scope, f"{j.id} 没有适用范围"
        assert j.target, f"{j.id} 没挂回报告条目"


def test_scenario_key_items_are_checked_even_without_an_old_judgment():
    """不能只检查已经存在的判断：场景要看的关键事项，没有记录也要立一条。"""
    v = run(DEMO_COMPANY, PAY)
    assert any(j.id.startswith("key.") for j in v.judgments)


# ---------- 3. 新材料进来：五格 ----------

def test_change_list_speaks_in_five_buckets_not_severity():
    case = add(make_case(DEMO_COMPANY), "material", PAY)
    v = case.versions[-1]
    assert v.judgment_changes and v.judgment_summary
    kinds = {c.kind for c in v.judgment_changes}
    assert kinds <= {"same", "found", "recheck", "unconfirmed", "next_question", "dropped"}
    assert "found" in kinds and "recheck" in kinds
    assert "更严重" not in v.judgment_summary
    assert "新增发现" in v.judgment_summary and "需要重新核实" in v.judgment_summary


def test_unrelated_material_changes_nothing():
    case = add(make_case(DEMO_COMPANY), "material", PAY)
    case = add(case, "material", "小区停水通知：本周三上午停水四小时，请提前储水。")
    v = case.versions[-1]
    assert all(c.kind == "same" for c in v.judgment_changes)
    assert "保持不变" in v.judgment_summary


# ---------- 4. 冲突：两边都留着 ----------

def test_new_material_does_not_overwrite_the_old_evidence():
    v = add(make_case(DEMO_COMPANY), "material", PAY).versions[-1]
    j = ids(v)["check.A7"]
    assert len(j.dispute) >= 3
    joined = " ".join(j.dispute)
    assert DEMO_COMPANY in joined and "张某" in joined
    assert "两边都留着" in joined and "不以后交的材料为准" in joined


# ---------- 5. 疑点能被澄清，误识别能被撤回 ----------

def client():
    return TestClient(app)


def new_case_via_api():
    c = client()
    demo = next(d for d in c.get("/api/demo/cases").json() if d["ready"])
    case = c.post("/api/cases", json={"company_name": demo["input"]["company_name"],
                                      "need": "我们要给这家公司交一笔服务费"}).json()
    return c, case["id"]


def test_a_person_can_withdraw_a_warning_and_it_sticks():
    c, cid = new_case_via_api()
    c.post(f"/api/cases/{cid}/supplements", json={"kind": "material", "title": "付款截图", "text": PAY})
    r = c.post(f"/api/cases/{cid}/resolve", json={"judgment_id": "check.A7", "action": "withdrawn",
                                                  "by": "范美琳", "note": "看错了，是公司简称"})
    assert r.status_code == 200
    v = r.json()["versions"][-1]
    j = next(x for x in v["judgments"] if x["id"] == "check.A7")
    assert j["state"] == "withdrawn" and j["state_label"] == "已撤回"
    assert j["history"] and "范美琳" in j["history"][0]
    assert "已撤回" in v["judgment_summary"]

    # 后面再来一版（改需求），撤回过的不能被悄悄翻回来
    after = c.post(f"/api/cases/{cid}/supplements", json={"kind": "need", "text": "我其实是想去这家公司上班"}).json()
    j2 = next(x for x in after["versions"][-1]["judgments"] if x["id"] == "check.A7")
    assert j2["state"] == "withdrawn"


def test_withdrawing_a_warning_also_takes_it_out_of_the_report():
    """她点名要的：只会加警告、不会撤警告的系统不可靠。
    核实过之后，报告里那条不能再催人去核实，变化清单也要说"已经澄清"。"""
    c, cid = new_case_via_api()
    c.post(f"/api/cases/{cid}/supplements", json={"kind": "material", "title": "付款截图", "text": PAY})
    v = c.post(f"/api/cases/{cid}/resolve", json={"judgment_id": "check.A7", "action": "clarified",
                                                  "by": "范美琳", "note": "打给公司对公户了"}).json()["versions"][-1]
    a7 = next(a for a in v["assertions"] if a["id"] == "A7")
    assert "已澄清" in a7["plain"] and "原来的核验结论是" in a7["plain"]
    assert "范美琳" in a7["plain"]
    kinds = [ch["kind"] for ch in v["judgment_changes"]]
    assert "cleared" in kinds and "recheck" not in kinds
    j = next(x for x in v["judgments"] if x["id"] == "check.A7")
    assert j["unknown"] == [], "已澄清了就不能还挂着'还没证明的事'"
    assert any("不再挂着这些待核的事" in h for h in j["history"])


def test_recheck_keeps_the_open_questions():
    """"继续查"跟"已澄清"不一样：待核的事还得挂在卡片上，别顺手清空。"""
    c, cid = new_case_via_api()
    c.post(f"/api/cases/{cid}/supplements", json={"kind": "material", "title": "付款截图", "text": PAY})
    v = c.post(f"/api/cases/{cid}/resolve", json={"judgment_id": "check.A7", "action": "recheck",
                                                  "by": "范美琳", "note": "还在等对方回话"}).json()["versions"][-1]
    j = next(x for x in v["judgments"] if x["id"] == "check.A7")
    assert j["state"] == "recheck" and len(j["unknown"]) >= 3


def test_resolve_unknown_judgment_is_404():
    c, cid = new_case_via_api()
    r = c.post(f"/api/cases/{cid}/resolve", json={"judgment_id": "根本没这条"})
    assert r.status_code == 404


def test_resolve_keeps_old_versions():
    c, cid = new_case_via_api()
    case = c.get(f"/api/cases/{cid}").json()
    before = len(case["versions"])
    jid = next(j["id"] for j in case["versions"][-1]["judgments"] if j["state"] == "needs_check")
    c.post(f"/api/cases/{cid}/resolve", json={"judgment_id": jid, "action": "clarified", "note": "问过了"})
    case = c.get(f"/api/cases/{cid}").json()
    assert len(case["versions"]) == before + 1
    assert case["versions"][-1]["trigger"] == "resolve"


def test_ask_ids_follow_content_not_position():
    """问题的"编号"会随问题增减整体挪位，判断的 id 不能跟着编号走，
    否则旧问题会被认成"变了"，一次冒出三条假变化。"""
    c, cid = new_case_via_api()
    v1 = c.get(f"/api/cases/{cid}").json()["versions"][-1]
    a1 = {j["id"]: j["text"] for j in v1["judgments"] if j["id"].startswith("ask.")}
    assert a1
    c.post(f"/api/cases/{cid}/supplements", json={"kind": "material", "title": "付款截图", "text": PAY})
    v2 = c.get(f"/api/cases/{cid}").json()["versions"][-1]
    a2 = {j["id"]: j["text"] for j in v2["judgments"] if j["id"].startswith("ask.")}
    # 同一个 id 在两版里必须指同一句话，不能因为编号挪位就换了所指
    for jid in set(a1).intersection(a2):
        assert a1[jid] == a2[jid], "id 在两版里指的不是同一句问题了"
    # 两版都在的问题，不能被当成"新增问题"
    still = set(a1.values()).intersection(a2.values())
    same_ids = {i for i, t in a1.items() if t in still}
    changed = {x["target"] for x in v2["judgment_changes"] if x["kind"] == "next_question"}
    assert not same_ids.intersection(changed), "旧问题不该被当成新增问题"


def test_key_items_are_named_not_leaked():
    """场景关键事项的内部编号不能直接漏给用户。"""
    v = add(make_case(DEMO_COMPANY), "material", PAY).versions[-1]
    for j in v.judgments:
        if j.id.startswith("key."):
            assert j.id[4:] not in j.text, f"{j.id} 这条把编号漏在正文里了"


def test_every_scenario_item_has_a_name_or_says_it_generically():
    """每个场景列进 first_items 的检查项都得有人话名字。

    2026-10-02 队友加了 risk.amac_tips，名字表里没有、这一版又没查到，正文里就漏出了
    「risk.amac_tips」这种内部编号，用户看不懂。所以这里把六个场景一次扫完：
    认得出名字的，名字里不能再出现内部编号的样子（带点的英文、下划线）；
    认不出的，宁可返回 None（调用方会说成"有一项该核的事"），也不许把编号当名字用。
    """
    from app.analysis.judgments import _item_title
    from app.scenarios import load_scenarios
    for sid, sc in load_scenarios().items():
        for key in sc.first_items:
            name = _item_title(key, [], [], sc)
            if name is None:
                continue
            assert not re.search(r"[a-z_]+\.[a-z_]+|[a-z]+_[a-z]+", name), f"{sid} 的 {key} 名字还是内部编号的样子：{name}"


def test_payee_example_lands_in_the_five_buckets():
    """她给的例子：新材料进来后，结果该是"保持不变 / 新增发现 / 需要重新核实 / 尚不能确认 / 下一步问题"，
    而不是"风险等级从低变高"。"""
    v = add(make_case(DEMO_COMPANY), "material", PAY).versions[-1]
    kinds = {c.kind for c in v.judgment_changes}
    assert {"same", "found", "recheck", "unconfirmed", "next_question"}.issubset(kinds)
    same = [c for c in v.judgment_changes if c.kind == "same"]
    assert any("登记状态" in (c.after or "") for c in same), "工商登记状态这条不该被新材料推翻"
    # 需要核实和不能确认要分开：前者等人去查，后者现在没证据
    nxt = [c for c in v.judgment_changes if c.kind == "unconfirmed"]
    assert any("收款名是不是真的" in c.text or "什么关系" in c.text for c in nxt), "收款人身份/授权这类还没证据的事要单列"
    # 不能因为一条材料就说这是诈骗
    recheck = [c for c in v.judgment_changes if c.kind == "recheck"][0]
    assert any("诈骗" in x for x in ids(v)[recheck.target].cannot)

# ---------- 拍合同：合同要按合同去读 ----------
CONTRACT = """劳动合同
甲方：深圳前海某某科技有限公司
乙方：范某某
第一条 乙方须在入职前向甲方支付服装费 5800 元
第二条 本合同自双方签字之日起生效
"""


def test_contract_party_mismatch_is_flagged_not_silently_absorbed():
    v = add(make_case(DEMO_COMPANY), "material", CONTRACT).versions[-1]
    party = [j for j in v.judgments if j.id.startswith("contract.party.")]
    assert party, "合同进来了，却没读出当事人是谁"
    assert party[0].state == "needs_check"
    assert "深圳前海某某科技有限公司" in party[0].text and DEMO_COMPANY in party[0].plain
    assert "这是诈骗" not in party[0].plain          # 需求 §1：不许从材料直接跳到定性
    assert party[0].basis[0].quote                  # 依据要引到原句


def test_contract_upfront_fee_gets_its_own_judgment_with_a_locator():
    """规则没拎过的先交钱条款（借款合同里这条），要自己开一张卡。"""
    loan = ("借款合同\n甲方：深圳前海某某科技有限公司\n乙方：张某\n"
            "第一条 甲方须在放款前向乙方支付保证金 5800 元\n第二条 本合同自双方签字之日起生效\n")
    v = add(make_case(DEMO_COMPANY), "material", loan).versions[-1]
    pre = [j for j in v.judgments if j.id.startswith("contract.prepay.")]
    assert pre and pre[0].state == "needs_check"
    assert "保证金" in pre[0].text and "5800" in pre[0].text
    assert pre[0].basis[0].locator and "第" in pre[0].basis[0].locator
    assert "这是诈骗" in pre[0].cannot and "这是诈骗" not in pre[0].plain
    assert pre[0].unknown


def test_contract_does_not_double_card_a_clause_the_rules_already_caught():
    """劳动合同里那条"入职前交服装费"规则已经拎过了，别再开一张重复的卡。"""
    v = add(make_case(DEMO_COMPANY), "material", CONTRACT).versions[-1]
    pre = [j for j in v.judgments if j.id.startswith("contract.prepay.") and "服装费" in j.text]
    assert not pre
    assert any(a.id == "A9" for a in v.assertions)      # 规则确实拎到了


def test_contract_gap_lists_what_the_paper_is_missing_without_judging_the_company():
    v = add(make_case(DEMO_COMPANY), "material", CONTRACT).versions[-1]
    blank = [j for j in v.judgments if j.id.startswith("contract.blank.")]
    assert blank and "保证金" not in blank[0].cannot
    assert "这份合同无效" in blank[0].cannot         # 缺的是材料，不是事实
    assert blank[0].plain.startswith("缺的是")


def test_photo_of_a_contract_shows_up_in_the_change_list():
    """拍一份合同进来，变化清单里得看得见它——不能是"没有影响判断的变化"。"""
    case = add(make_case(DEMO_COMPANY), "material", CONTRACT)
    v = case.versions[-1]
    by_target = {}
    for c in v.judgment_changes:
        prev = by_target.get(c.target)
        if prev is None or (prev.kind == "unconfirmed" and c.kind != "unconfirmed"):
            by_target[c.target] = c          # 一条判断下面可能挂着几行"还没证据"，取主行
    for prefix in ("contract.party.", "contract.blank."):
        hits = [c for t, c in by_target.items() if t.startswith(prefix)]
        assert hits, f"{prefix} 读出来了，却没进变化清单"
        assert hits[0].because, "变化要说清是哪份材料带来的"
    party = by_target[next(t for t in by_target if t.startswith("contract.party."))]
    assert party.kind == "recheck"                       # 需要重新核实，不是"新增发现"混着说
    assert "需要重新核实" in v.judgment_summary


def test_contract_excerpt_without_a_named_party_still_gets_read():
    """认购协议节选这类：没写甲方：，只有"协议"和条款，也要按合同读，并说出"没写当事人"。"""
    txt = ("《某康养财富认购协议》（节选）\n第五条 认购期限为 12 个月，期间为封闭期，不得提前赎回。\n"
           "第六条 甲方如要求提前退出，乙方扣除本金的 20% 作为违约金后退还余款。\n")
    v = add(make_case(DEMO_COMPANY), "material", txt).versions[-1]
    party = [j for j in v.judgments if j.id.startswith("contract.party.")]
    assert party and party[0].state == "unconfirmed"
    assert "没写甲方" in party[0].text

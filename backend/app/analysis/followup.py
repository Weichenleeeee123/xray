"""该问对方的问题：全部由规则生成，不依赖模型。

来源有三类：对不上或核不了的说法、"该有的没有"和"没查"的项、场景模板里的必问清单。
每个问题都写明拿到答案后去哪里查；同一主题只问一次，最多 5 个。
"""
import re

from app.models import Assertion, ClaimKind, MissingItem, Question, Scenario, Signal, Status

LIMIT = 5

# 说法对不上或核不了时该问的话：(问题, 去哪里查)
CLAIM_QUESTIONS = {
    ClaimKind.qualification: ("请给出金融许可证编号，或者理财产品登记编码",
                              "金融许可证到国家金融监督管理总局官网查；理财产品登记编码到中国理财网（chinawealth.com.cn）查"),
    ClaimKind.return_promise: ("收益从哪里来？钱投到了什么资产？写进合同了吗",
                               "正规理财产品有登记编码，到中国理财网查得到；承诺保本保息的都不合规"),
    ClaimKind.partner: ("存管银行是哪一家？请给出存管协议",
                        "打这家银行的官方客服电话，核实存管关系是否真实"),
    ClaimKind.background: ("说的国资背景是哪一家？持股多少",
                           "国家企业信用信息公示系统查股东，一层层往上查到最终出资人"),
    ClaimKind.capital: ("注册资本实际交了多少",
                        "国家企业信用信息公示系统 → 年度报告 → 股东及出资信息"),
    ClaimKind.scale: ("门店地址和员工人数能不能给一份清单",
                      "国家企业信用信息公示系统查分支机构；年度报告里有参保人数"),
    ClaimKind.payee: ("收款账户的户名是什么？是不是公司的对公账户",
                      "只转对公账户，户名和合同上的公司全称必须一致"),
    ClaimKind.refund: ("退款或提前取回的条件写进合同了吗？违约金多少",
                       "看合同原文的退款、赎回条款，口头承诺不算"),
    ClaimKind.upfront_fee: ("为什么入职要先交钱？交给谁？有没有正式收据",
                            "正规单位招人不收费；被要求交钱可向当地人社部门劳动保障监察举报"),
}
# 没查的数据，让对方提供线索
GAP_QUESTIONS = {
    "credit.registry": ("identity", "这家公司的全称和统一社会信用代码是什么",
                        "国家企业信用信息公示系统（gsxt.gov.cn）按代码查登记状态、股东、处罚"),
    "risk.amac": ("amac", "有没有私募基金管理人登记编号",
                  "中国证券投资基金业协会信息公示（gs.amac.org.cn）按名称或编号查"),
}
# 有问题 / 要留意时追问的条目
FLAG_QUESTIONS = {
    "risk.pf_threshold": ("pf_threshold", "你们推荐的是不是私募基金？我达不到合格投资者标准（单只 100 万起），为什么能卖给我",
                          "中国证券投资基金业协会信息公示（gs.amac.org.cn）查这只产品的备案编号；查不到备案的不要买"),
}
# 用户最担心的事，对应到要问的主题
FOCUS_ABOUT = {"急用时钱能不能拿回来": "refund", "本金会不会亏": "return_promise", "说的收益是不是真的": "return_promise",
               "这家公司正不正规、有没有资格": "qualification", "会不会让我先交钱": "upfront_fee"}


def build_questions(assertions: list[Assertion], missing: list[MissingItem], signals: list[Signal],
                    scenario: Scenario, focus: list[str]) -> list[Question]:
    candidates: list[tuple[int, str, Question]] = []  # (优先级, 主题, 问题)
    focus_about = {FOCUS_ABOUT[f] for f in focus if f in FOCUS_ABOUT}

    for a in assertions:
        if a.color == "green" or a.kind not in CLAIM_QUESTIONS:
            continue
        ask, where = CLAIM_QUESTIONS[a.kind]
        if a.kind is ClaimKind.background and not re.search(r"国资|国企|央企|国有|政府", a.text):
            backer = "上市公司" if "上市" in a.text else "金融集团注资"
            ask = f"说的\"{backer}\"是哪一家？持股多少"
        rank = 0 if a.kind.value in focus_about else (1 if a.color == "red" else 2)
        candidates.append((rank, a.kind.value, Question(id="", ask=ask, why=a.plain, check_where=where, linked=[a.id])))

    for m in missing:
        candidates.append((2, m.id, Question(id="", ask=f"为什么材料上没有写\"{m.text}\"", why=m.plain,
                                             check_where="正规金融产品的销售材料都有风险提示，没有就要多留个心", linked=[m.id])))

    for s in signals:
        for item in s.items:
            key = f"{s.key}.{item.key}"
            if key in ("credit.official_web", "risk.regulator_warning") and item.status is Status.bad:
                candidates.append((1, "official_web", Question(
                    id="", ask=f"政府网站上有一份点名你们的文件（{(item.detail or '').split('；另有')[0]}），这件事现在处理完了吗",
                    why=f"{item.label}：{item.value}", check_where="点开原始数据里的原文链接，看处罚或通报的内容和日期",
                    linked=[key])))
            if key in FLAG_QUESTIONS and item.status in (Status.bad, Status.warn):
                about, ask, where = FLAG_QUESTIONS[key]
                candidates.append((0 if item.status is Status.bad else 2, about,
                                   Question(id="", ask=ask, why=f"{item.label}：{item.value}", check_where=where, linked=[key])))
            if key in GAP_QUESTIONS and item.status is Status.none:
                about, ask, where = GAP_QUESTIONS[key]
                candidates.append((3, about, Question(id="", ask=ask, why=f"{item.label}还没查：{item.detail or item.value}",
                                                      check_where=where, linked=[key])))

    for m in scenario.must_ask:
        rank = 0 if m.about in focus_about else 3
        candidates.append((rank, m.about, Question(id="", ask=m.ask, why=f"这类事最先要问：{scenario.first_question}",
                                                   check_where=m.check_where)))

    seen, out = set(), []
    for _, about, q in sorted(candidates, key=lambda c: c[0]):
        if about in seen:
            continue
        seen.add(about)
        out.append(q.model_copy(update={"id": f"Q{len(out) + 1}"}))
        if len(out) == LIMIT:
            break
    return out

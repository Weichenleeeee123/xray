"""企查查智能体平台的补充信息：实际控制人、行政许可和资质、变更记录、开庭和立案、劳动仲裁、招聘。

每项一个工具、每家每项约 5 积分，结果按"公司 + 工具"缓存（同 qcc_agent.py）。规矩：
- 隐私（仓库公开）：当事人、董监高、实际控制人是个人的，名字一律不存。
  开庭、立案只留案号、案由、法院、日期和"它是原告还是被告"；变更记录只留日期和变更项目
  （名称、住所、注册资本这类不涉及个人的才留前后内容）；实控人是个人只写"自然人"和持股比例。
- 平台只给最近几十条明细：统计都说"返回的最近 N 条里"，总数用平台给的。
- 打官司不等于有问题：银行天天起诉借款人。只看它当被告的，案由按关键词分，不让模型判断。
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.models import Coverage, RawRecord
from app.sources.licenses import normalize
from app.sources.qcc_agent import EMPTY, is_empty, is_person, rows, total

SITE = "https://agent.qcc.com"
TOOLS = {"controller": ("company", "get_actual_controller", "实际控制人"),
         "licenses": ("operation", "get_administrative_license", "行政许可"),
         "qualifications": ("operation", "get_qualifications", "资质证书"),
         "changes": ("company", "get_change_records", "变更记录"),
         "hearings": ("risk", "get_hearing_notice", "开庭公告"),
         "filings": ("risk", "get_case_filing_info", "立案信息"),
         "labor": ("risk", "get_service_announcement", "劳动仲裁"),
         "jobs": ("operation", "get_recruitment_info", "招聘信息")}
# 原始数据里每项一条记录，source_id 都以 qcc_ 开头
SOURCE = {k: f"qcc_{k}" for k in TOOLS}

DEFENDANT = ("被告", "被申请人", "被执行人", "被起诉人")
INVEST = re.compile(r"合伙|委托理财|理财|投资|证券|基金|私募|民间借贷|集资|信托")
LABOR = re.compile(r"劳动|劳务|工资|社会保险|工伤|竞业|经济补偿")
# 资质里和"金融牌照"相关的类型
FIN_LICENSE = re.compile(r"金融许可|保险|证券|期货|基金|支付|融资担保|小额贷款|典当|信托|外汇|征信")
KEEP_CHANGE = re.compile(r"名称变更|住所|经营场所|注册资本")
# 变更前后内容里带这些字的整条丢掉：可能是人名、职务
PERSONISH = re.compile(r"法定代表人|负责人|股东|投资人|董事|监事|经理|职务|组织机构|姓名|成员|发起人")
FLAG_CHANGE = re.compile(r"名称变更|法定代表人|负责人变更")


@dataclass
class Part:
    coverage: str                  # found / not_found / failed / not_covered
    total: int = 0
    rows: list[dict] = field(default_factory=list)   # 清理过的明细
    summary: dict = field(default_factory=dict)      # 平台给的分类计数（资质类型等）
    error: str | None = None
    retrieved_at: str | None = None


@dataclass
class QccExtras:
    company: str
    parts: dict[str, Part]

    def get(self, key: str) -> Part:
        return self.parts.get(key) or Part("not_covered")


def _roles(parties, company: str) -> list[str]:
    """它在案子里的角色：当事人字段是 {角色: [名字]}，名字里含它全称的那一栏（分支机构也算它）。"""
    me = normalize(company)
    if not isinstance(parties, dict):
        return []
    return [role for role, names in parties.items()
            if any(me in normalize(str(n)) for n in (names if isinstance(names, list) else [names]))]


def _case(r: dict, company: str, when_key: str) -> dict:
    roles = _roles(r.get("当事人"), company)
    return {"案号": r.get("案号"), "案由": r.get("案由") or r.get("主案由"), "法院": r.get("法院") or r.get("发布机构"),
            "日期": str(r.get(when_key) or "")[:10] or None, "它的角色": "、".join(roles) or "未列明",
            "被告": any(x in DEFENDANT for x in roles)}


def _labor(data: dict, company: str) -> list[dict]:
    out = []
    for kind, items in (data.get("劳动仲裁信息") or {}).items() if isinstance(data.get("劳动仲裁信息"), dict) else []:
        for r in items if isinstance(items, list) else []:
            who = r.get("被申请人") or []
            defendant = any(normalize(company) in normalize(str(n)) for n in (who if isinstance(who, list) else [who]))
            out.append({"类型": kind, "案号": r.get("案号"), "案由": r.get("主案由") or r.get("案由"),
                        "机构": r.get("发布机构"), "日期": str(r.get("开庭日期") or r.get("发布日期") or "")[:10] or None,
                        "它的角色": "被申请人" if defendant else "未列明", "被告": defendant})
    return out or [_case(r, company, "开庭日期") for r in rows(data)]


def _change(r: dict) -> dict:
    item = str(r.get("变更项目") or "")
    out = {"日期": str(r.get("变更日期") or "")[:10] or None, "项目": item}
    if KEEP_CHANGE.search(item) and not re.search(r"投资人|股东|人员|法定代表人|负责人", item):
        # 平台有时把整段登记内容都塞进来（含股东、董监高名字）：按变更项目只留对得上的那一句
        want = (re.compile(r"公司|企业|合伙|中心|集团|银行") if "名称" in item else
                re.compile(r"^(住所|经营场所)|[省市区县路街号]") if re.search(r"住所|经营场所", item) else
                re.compile(r"^[\d,.]+\s*(万|亿)?(元|人民币)?$|注册资本"))

        def keep(v):
            vs = v if isinstance(v, list) else [v]
            return [x for x in vs if isinstance(x, str) and x and want.search(x) and not is_person(x.split(",")[0].strip())
                    and not PERSONISH.search(x)]
        out |= {"变更前": keep(r.get("变更前内容")), "变更后": keep(r.get("变更后内容"))}
    return out


def _controller(rs: list[dict]) -> list[dict]:
    out = []
    for r in rs:
        name = str(r.get("实际控制人名称") or r.get("名称") or "")
        out.append({"名称": "自然人" if is_person(name) else name, "是自然人": is_person(name),
                    "总持股比例": r.get("总持股比例"), "表决权比例": r.get("表决权比例")})
    return out


def _clean(key: str, data: dict, company: str) -> tuple[list[dict], dict]:
    rs = rows(data)
    summary = {k[:-3]: v for k, v in data.items() if isinstance(k, str) and k.endswith("条目数") and isinstance(v, int)}
    if key == "controller":
        return _controller(rs), {}
    if key == "licenses":
        return [{"名称": r.get("决定文书/许可证名称") or "", "编号": r.get("决定文书/许可编号"), "机关": r.get("许可机关"),
                 "状态": r.get("许可状态"), "有效期自": r.get("有效期自"), "有效期至": r.get("有效期至")} for r in rs], {}
    if key == "qualifications":
        return [{"名称": r.get("资质名称"), "状态": r.get("证书状态"), "发证日期": r.get("发证日期"),
                 "有效期至": r.get("有效期至")} for r in rs], summary
    if key == "changes":
        return [_change(r) for r in rs], {}
    if key in ("hearings", "filings"):
        return [_case(r, company, "开庭时间" if key == "hearings" else "立案日期") for r in rs], {}
    if key == "labor":
        return _labor(data, company), {}
    if key == "jobs":
        return [{"日期": r.get("发布日期"), "职位": r.get("招聘职位"), "月薪": r.get("月薪"), "学历": r.get("学历"),
                 "地点": r.get("办公地点")} for r in rs], {}
    return rs, summary


def fetch(client, company: str) -> QccExtras:
    """client 是 QccAgentClient（有 call）。每项单独查，一项失败不影响别的。"""
    parts = {}
    for key, (server, tool, _) in TOOLS.items():
        c = client.call(server, tool, company)
        if c.error:
            parts[key] = Part("failed", error=c.error, retrieved_at=c.retrieved_at)
            continue
        data = c.data or {}
        cleaned, summary = _clean(key, data, company)
        if not cleaned:
            said = str(data.get("摘要") or data.get("搜索结果") or "")
            cov = "not_found" if (not data or is_empty(data) or EMPTY.search(said) or total(data) == 0) else "failed"
            parts[key] = Part(cov, 0, [], summary, None if cov == "not_found" else "返回的数据认不出明细", c.retrieved_at)
            continue
        parts[key] = Part("found", max(total(data), len(cleaned)), cleaned, summary, None, c.retrieved_at)
    return QccExtras(company, parts)


def records(x: QccExtras) -> list[RawRecord]:
    out = []
    for key, (_, _, label) in TOOLS.items():
        p = x.get(key)
        cov = Coverage(p.coverage)
        content = {"平台记录总数": p.total, "返回的明细": p.rows} | ({"分类计数": p.summary} if p.summary else {}) \
            if cov is Coverage.found else None
        note = {"found": f"第三方商业数据；个人名字不存{'；只给了最近 ' + str(len(p.rows)) + ' 条明细' if p.total > len(p.rows) else ''}",
                "not_found": "查了，平台没有这一项的记录", "failed": f"没查成：{p.error}",
                "not_covered": "没查"}[p.coverage]
        out.append(RawRecord(id="", source_id=SOURCE[key], title=f"{label}（企查查）", kind="commercial", coverage=cov,
                             retrieved_at=p.retrieved_at or "", as_of=(p.retrieved_at or "")[:10] or None, url=SITE,
                             content=content, note=note))
    return out


# ---------- 给规则用的小结 ----------

def recent(rows_: list[dict], today: date, days: int, key: str = "日期") -> list[dict]:
    since = (today - timedelta(days=days)).isoformat()
    return [r for r in rows_ if str(r.get(key) or "") >= since]


def defendant_cases(x: QccExtras) -> list[dict]:
    seen, out = set(), []
    for key in ("hearings", "filings"):
        for r in x.get(key).rows:
            if r.get("被告") and r.get("案号") not in seen:
                seen.add(r.get("案号"))
                out.append(r)
    return out


def financial_licenses(x: QccExtras) -> list[str]:
    """资质、许可里和金融牌照相关的类型名。"""
    names = [k for k in x.get("qualifications").summary if FIN_LICENSE.search(k)]
    names += [r["名称"] for r in x.get("qualifications").rows if r.get("名称") and FIN_LICENSE.search(r["名称"])]
    names += [r["名称"] for r in x.get("licenses").rows if r.get("名称") and FIN_LICENSE.search(str(r["名称"]))]
    return list(dict.fromkeys(names))

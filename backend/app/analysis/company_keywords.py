"""Company descriptors from this report's structured records, never from claims or name guesses."""
import re

from app.models import Case, CompanyKeyword, RawRecord, Version

QUALIFICATIONS = {
    "高新技术企业", "科技型中小企业", "小微企业", "专精特新中小企业", "专精特新小巨人企业",
    "创新型中小企业", "绿色工厂", "绿色制造", "企业技术中心", "国家企业技术中心",
    "重点实验室", "技术创新示范企业",
}
ROUNDS = {"种子轮", "天使轮", "Pre-A轮", "A轮", "A+轮", "B轮", "B+轮", "C轮", "D轮", "E轮"}
BUSINESSES = (
    "软件开发", "人工智能", "集成电路设计", "通信设备制造", "信息技术咨询", "互联网信息服务",
    "数据处理", "健康咨询", "养老服务", "家政服务", "企业管理咨询", "资产管理", "投资管理",
    "餐饮服务", "食品销售", "教育咨询", "机械设备制造", "建筑工程", "电子产品销售", "货物进出口",
)
NEGATIVE = re.compile(r"未认定|未取得|未获|不属于|非高新|申请中|申报中|拟申请|已撤销|已取消|已过期|已失效|历史")


def _labels(value, report_day: str) -> list[str]:
    """Read explicit tag values only; descriptions and historical/expired entries are not tags."""
    if isinstance(value, list):
        return [label for item in value for label in _labels(item, report_day)]
    if isinstance(value, dict):
        status = str(value.get("状态") or value.get("status") or "")
        until = str(value.get("有效期至") or value.get("valid_until") or "")
        if NEGATIVE.search(status) or status in {"撤销", "取消", "过期", "失效", "无", "否"}:
            return []
        if until and re.fullmatch(r"\d{4}-\d{2}-\d{2}", until) and until < report_day:
            return []
        return _labels(value.get("名称") or value.get("name") or "", report_day)
    if not isinstance(value, str) or NEGATIVE.search(value):
        return []
    return [part.strip() for part in re.split(r"[,，、;；|]", value) if part.strip()]


def company_keywords(version: Version, raw: list[RawRecord]) -> list[CompanyKeyword]:
    records = [r for r in raw if r.id in version.raw_ids and r.coverage == "found"
               and r.kind in {"official", "collected", "commercial", "demo"}]
    by_source = {r.source_id: r for r in records}
    result: list[CompanyKeyword] = []

    def add(label: str, record: RawRecord, basis: str):
        if label and not any(item.label == label for item in result) and len(result) < 6:
            result.append(CompanyKeyword(label=label, ref=record.id, basis=basis))

    company = version.company
    registry = by_source.get("registry")
    if company and registry:
        data = registry.content if isinstance(registry.content, dict) else {}
        data = data.get("工商信息", data)
        if not isinstance(data, dict):
            data = {}
        # Do not scan shareholder/branch records or full-text materials for company honours.
        for key in ("企业标签", "资质标签", "企业资质", "荣誉资质", "tags"):
            for label in _labels(data.get(key), version.created_at[:10]):
                if label in QUALIFICATIONS:
                    add(label, registry, f"本版登记资料的「{key}」记载：{label}")
        for key in ("融资轮次", "融资阶段"):
            for label in _labels(data.get(key), version.created_at[:10]):
                if label in ROUNDS:
                    add(label, registry, f"本版登记资料的「{key}」记载：{label}")
        for key in ("所属行业", "行业", "industry"):
            label = data.get(key)
            if isinstance(label, str) and 2 <= len(label.strip()) <= 24 and not NEGATIVE.search(label) and label not in {"未知", "暂无", "未披露"}:
                add(label.strip(), registry, f"本版登记资料的「{key}」记载：{label.strip()}")
                break
        if company.known("listing") and company.listing:
            add("上市公司", registry, "本版登记资料已收录该公司的上市信息")

    lic = version.license
    if lic.found and lic.record and (record := by_source.get(lic.source)):
        add(lic.record.type, record, f"本版机构名单记载的类型：{lic.record.type}")
    if version.amac.registered and (record := by_source.get("amac")):
        add("私募基金管理人", record, "本版中基协公示名单收录该公司")

    if company and registry:
        if company.known("scope"):
            # Parenthetical exclusions and prohibited activities must not become business tags.
            scope = re.sub(r"[（(][^）)]*[）)]", "", company.scope)
            parts = [p for p in re.split(r"[;；。\n]", scope)
                     if not re.search(r"不得|不含|不包括|禁止|除外|尚未|未取得|不从事", p)]
            hits = []
            for i, part in enumerate(parts):
                # Keep short business phrases in their original order, including less common industries.
                phrases = re.split(r"[,，、]", re.sub(r"^\s*(一般项目|许可项目)\s*[：:]", "", part))
                for phrase in phrases:
                    phrase = phrase.strip()
                    if re.search(r"依法|许可|审批|批准|须|不得|不含|不包括|禁止|除外|尚未|未取得|不从事", phrase):
                        continue
                    matched = [label for label in BUSINESSES if label in phrase]
                    if matched:
                        hits.extend((i, part.index(label), label) for label in matched)
                    elif 2 <= len(phrase) <= 12 and re.search(r"服务|咨询|管理|开发|设计|制造|销售|加工|生产|进出口|零售|批发|研发|运输|租赁", phrase):
                        hits.append((i, part.index(phrase), phrase))
            hits.sort()
            for label in list(dict.fromkeys(label for _, _, label in hits))[:3]:
                add(label, registry, f"登记经营范围包含「{label}」；不代表已取得相关许可或实际业务规模")
        if company.known("status") and company.status and company.status not in {"未知", "未覆盖"}:
            add(company.status, registry, f"本版登记状态：{company.status}")
    return result


def refresh_company_keywords(case: Case, *, current_only: bool = False) -> Case:
    """Old reports use their own saved snapshots; no network query or conclusion changes."""
    for version in case.versions:
        if current_only and version.no != case.current:
            continue
        version.company_keywords = company_keywords(version, case.raw)
    return case

"""用户输入的公司名 → 营业执照上的全称。

用户输简称很正常（"巨鲸财富""杭州银行"），但后面每一步——持牌名单、中基协、企查查——都按全称核对，
拿简称去查，就会查成"没有登记""名字对不上"，比查不到更糟：看起来像查过了。所以开查之前先把名字定下来：

1. 本地名单（持牌机构、私募、保险、期货、支付）或证据包（含别名）能精确对上，直接用全称；
2. 对不上就问企查查的模糊搜索。平台说"唯一精确匹配"才算定了；简称会返回多个候选，
   平台明确要求让用户选（"巨鲸财富"同时命中巨鲸财富管理和兄弟公司巨鲸资产管理），这里只给候选，不替用户挑；
3. 企查查没配或断网，就在本地名单里找名字里包含输入的全称，作为候选。

候选只带名称、统一社会信用代码、成立日期、状态，不带法定代表人等个人信息。
"""
from dataclasses import dataclass, field

from app.sources.licenses import normalize
from app.sources.qcc_agent import QccAgentClient

MAX_CANDIDATES = 8


@dataclass
class Candidate:
    name: str
    code: str | None = None
    founded: str | None = None
    status: str | None = None


@dataclass
class Resolution:
    query: str
    exact: bool                      # True：name 就是全称，可以直接查
    name: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    source: str = "none"             # local / qcc / none
    note: str | None = None


def _local_names(svc) -> dict[str, str]:
    """本地认识的全称：规范化名字 → 全称。证据包的别名也指向它的全称。"""
    names: dict[str, str] = {}
    for key, record in getattr(svc.licenses, "_by_name", {}).items():
        names[key] = record.name
    for registry in (svc.registries or {}).values():
        for key, row in registry.rows.items():
            names.setdefault(key, row["name"])
    for key, raw in getattr(svc.packs, "_by_name", {}).items():
        names[key] = raw["company"]
    for key, company in getattr(svc.registry, "_by_name", {}).items():
        names.setdefault(key, company.name)
    return names


def _qcc(svc) -> QccAgentClient | None:
    c = getattr(svc, "commercial", None)
    return c if isinstance(c, QccAgentClient) and c.configured else None


def _candidate(row: dict) -> Candidate | None:
    name = row.get("企业名称")
    if not isinstance(name, str) or not name.strip():
        return None
    return Candidate(name=name.strip(), code=row.get("统一社会信用代码") or None, founded=row.get("成立日期") or None,
                     status=row.get("状态") or row.get("登记状态") or None)


def resolve(query: str, svc) -> Resolution:
    q = normalize(query or "")
    if len(q) < 2:
        return Resolution(query, False, note="名字太短，请输入营业执照上的全称")
    names = _local_names(svc)
    if q in names:
        return Resolution(query, True, names[q], source="local")

    qcc, note = _qcc(svc), None
    if qcc is not None:
        call = qcc.call("company", "get_company_by_query", query.strip())
        if call.error is None and call.data:
            info = call.data.get("企业信息")
            rows = info if isinstance(info, list) else [info] if isinstance(info, dict) else []
            found = [c for c in map(_candidate, rows) if c][:MAX_CANDIDATES]
            unique = "唯一" in str(call.data.get("匹配结果", "")) and len(found) == 1
            if unique and normalize(found[0].name) == q:
                return Resolution(query, True, found[0].name, found, source="qcc")
            if found:
                return Resolution(query, False, None, found, source="qcc",
                                  note="按这个名字找到下面几家，请选一家" if len(found) > 1 else "是不是这家？")
        else:
            note = f"企业搜索这次没成功（{call.error or '没有结果'}），先从本地名单里找"

    local = sorted({name for key, name in names.items() if q in key}, key=len)[:MAX_CANDIDATES]
    if local:
        return Resolution(query, False, None, [Candidate(n) for n in local], source="local",
                          note=note or ("按这个名字在名单里找到下面几家，请选一家" if len(local) > 1 else "是不是这家？"))
    return Resolution(query, False, None, [], source="qcc" if qcc else "none",
                      note=note or "没找到叫这个名字的公司，请输入营业执照上的全称")

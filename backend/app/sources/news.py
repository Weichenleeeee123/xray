"""新闻舆情：企查查智能体平台的 get_news_sentiment（标题、发布时间、来源、情感倾向）。

- 情感倾向是企查查的模型标的，报告里写"企查查标为负面"，不当成我们的结论；口碑最多标"要留意"。
- 平台只给最近 30 条明细（摘要里有总条数）。统计都按"返回的这 30 条"说，不外推。
- 隐私（仓库公开）：只存负面新闻的标题，标题里括号中列的个人名字换成"相关个人"；中立、正面的只存日期、来源、倾向。
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.sources.qcc_agent import EMPTY, is_empty, is_person, rows, scrub_text, total

PAREN = re.compile(r"[（(]([^（）()]{1,40})[）)]")
NEGATIVE = "消极"


def scrub_title(title: str, company: str | None = None) -> str:
    """"行政处罚决定书（巨鲸财富、某某某）" → "行政处罚决定书（巨鲸财富、相关个人）"。"""
    def fix(m: re.Match) -> str:
        parts = re.split(r"([、，,；;])", m.group(1))
        def person(p: str) -> bool:  # 公司简称（"巨鲸财富"）也短、也没有机构字样，靠出现在全称里认出来
            return is_person(p) and not (company and p in company)
        return m.group(0)[0] + "".join("相关个人" if i % 2 == 0 and person(p.strip()) else p
                                       for i, p in enumerate(parts)) + m.group(0)[-1]
    return scrub_text(PAREN.sub(fix, title or ""), company)


@dataclass
class NewsItem:
    date: str | None
    sentiment: str            # 消极 / 中立 / 积极
    source: str
    url: str | None
    title: str | None = None  # 只有负面的留标题


@dataclass
class NewsFindings:
    coverage: str             # found / not_found / failed
    total: int = 0            # 平台说一共多少条
    items: list[NewsItem] = field(default_factory=list)   # 返回的明细，新的在前
    retrieved_at: str | None = None
    error: str | None = None

    @property
    def negatives(self) -> list[NewsItem]:
        return [i for i in self.items if i.sentiment == NEGATIVE]

    def recent_negatives(self, today: date, days: int = 365) -> list[NewsItem]:
        since = (today - timedelta(days=days)).isoformat()
        return [i for i in self.negatives if (i.date or "") >= since]

    def counts(self) -> dict[str, int]:
        out = {"消极": 0, "中立": 0, "积极": 0}
        for i in self.items:
            out[i.sentiment] = out.get(i.sentiment, 0) + 1
        return out


def findings(call, company: str) -> NewsFindings:
    if call.error:
        return NewsFindings("failed", retrieved_at=call.retrieved_at, error=call.error)
    data = call.data or {}
    items = []
    for r in rows(data):
        senti = str(r.get("情感类型") or r.get("情感倾向") or "中立")
        when = str(r.get("发布时间") or "")[:10] or None
        items.append(NewsItem(date=when, sentiment=senti, source=str(r.get("来源") or ""), url=r.get("链接") or None,
                              title=scrub_title(str(r.get("标题") or ""), company) if senti == NEGATIVE else None))
    items.sort(key=lambda i: i.date or "", reverse=True)
    if items:
        return NewsFindings("found", max(total(data), len(items)), items, call.retrieved_at)
    said = str(data.get("摘要") or data.get("搜索结果") or "")
    if not data or is_empty(data) or EMPTY.search(said):
        return NewsFindings("not_found", 0, retrieved_at=call.retrieved_at)
    return NewsFindings("failed", retrieved_at=call.retrieved_at, error="返回的数据认不出新闻列表")

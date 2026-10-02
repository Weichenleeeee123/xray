"""用户评价：按公司存，不按案卷存。同一家公司开多少份案卷，看到的都是同一批评价。

评价是别人说的，未核实。它只让人多留意，不让人放心：报告里差评集中才标"要留意"，好评再多也不标绿
（规则在 analysis/signals.py 的 review_item）。星级只给分布，不算平均分。

- 每家公司一个文件：data/reviews/<名称哈希>.json，git 忽略。演示评价在 data/fixtures/reviews.json，只读，
  只给虚构公司，不给真实公司编评价。
- 没有账号：浏览器生成一个匿名编号，后端只存它的哈希。同一个浏览器对同一家公司只能写一条。这只能防手滑，防不了刷。
- 存之前遮掉手机号、身份证号、住址、出生信息。评价里的定性话照发，页面上统一写"用户个人观点，未经核实"。
"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.models import REVIEW_RELATIONS, Coverage, RawRecord, Review, ReviewIn, ReviewList
from app.sources.licenses import normalize
from app.sources.web import redact as redact_doc

SOURCE_ID = "user_reviews"
PHONE = re.compile(r"(?<!\d)1[3-9]\d[\s-]?\d{4}[\s-]?\d{4}(?!\d)")
ID_NO = re.compile(r"(?<![0-9A-Za-z])\d{17}[\dXx](?![0-9A-Za-z])")


class DuplicateReview(Exception):
    """这个浏览器已经给这家公司写过一条。"""


def redact(text: str) -> str:
    text = redact_doc(text)          # 出生信息、住址、带"身份证"字样的号码
    text = ID_NO.sub("（证件号略）", text)
    return PHONE.sub("（电话略）", text)


def _hash(author: str) -> str:
    return hashlib.sha256(("xray-review:" + author).encode()).hexdigest()[:24]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ReviewStore:
    def __init__(self, directory: Path, seed: Path | None = None):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seed: dict[str, list[dict]] = {}
        if seed and Path(seed).exists():
            for company, items in json.loads(Path(seed).read_text(encoding="utf-8"))["companies"].items():
                self.seed[normalize(company)] = [{**r, "id": f"D{i + 1}", "demo": True} for i, r in enumerate(items)]

    def _path(self, company: str) -> Path:
        return self.dir / (hashlib.sha256(normalize(company).encode()).hexdigest()[:24] + ".json")

    def _own(self, company: str) -> list[dict]:
        path = self._path(company)
        return json.loads(path.read_text(encoding="utf-8"))["reviews"] if path.exists() else []

    def all(self, company: str) -> list[dict]:
        """这家公司的全部评价（含演示数据），新的在前。带着作者哈希，只在后端用。"""
        items = self.seed.get(normalize(company), []) + self._own(company)
        # 同一秒写的两条，后写的在前
        order = sorted(range(len(items)), key=lambda i: (items[i]["created_at"], i), reverse=True)
        return [items[i] for i in order]

    def listing(self, company: str, author: str | None = None) -> ReviewList:
        items = self.all(company)
        me = _hash(author) if author else None
        reviews = [Review(id=r["id"], stars=r["stars"], relation=r["relation"],
                          relation_label=REVIEW_RELATIONS.get(r["relation"], "其他"), text=r["text"],
                          nickname=r.get("nickname"), created_at=r["created_at"], demo=r.get("demo", False),
                          mine=bool(me) and r.get("author") == me) for r in items]
        dist = {str(s): sum(r.stars == s for r in reviews) for s in range(5, 0, -1)}
        return ReviewList(company=company, count=len(reviews), dist=dist, reviews=reviews)

    def add(self, body: ReviewIn) -> ReviewList:
        me = _hash(body.author)
        own = self._own(body.company)
        if any(r.get("author") == me for r in own):
            raise DuplicateReview(body.company)
        own.append({"id": uuid4().hex[:8], "stars": body.stars, "relation": body.relation, "text": redact(body.text),
                     "nickname": redact(body.nickname) if body.nickname else None, "created_at": _now(),
                     "author": me})
        path = self._path(body.company)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"company": body.company, "reviews": own}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(path)
        return self.listing(body.company, body.author)


def review_record(reviews: list[dict]) -> RawRecord | None:
    """汇集数据时的快照：一条原始数据，内容是当时的全部评价。不含作者哈希。评价没变，内容就不变，案卷里复用同一条。"""
    if not reviews:
        return None
    demo = all(r.get("demo") for r in reviews)
    content = [{"星级": r["stars"], "身份": REVIEW_RELATIONS.get(r["relation"], "其他"), "评价": r["text"],
                "昵称": r.get("nickname") or "匿名用户", "日期": r["created_at"][:10],
                **({"演示数据": True} if r.get("demo") else {})} for r in reviews]
    note = "用户自己写的评价，未经核实，系统不判断真假" + ("；演示数据，公司和评价都是编的" if demo else "")
    return RawRecord(id="", source_id=SOURCE_ID, title=f"用户评价（{len(reviews)} 条）", kind="user_review",
                     coverage=Coverage.found, retrieved_at=_now(), as_of=max(r["created_at"][:10] for r in reviews),
                     content=content, note=note)

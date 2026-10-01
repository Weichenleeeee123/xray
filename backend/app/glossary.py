"""名词解释：人工写好的固定词表，报告标注和助手回答共用。

不让模型每次现编解释：金融和法律名词说错一个字就会误导人，而且每次生成的说法都不一样。
模型只在助手里引用这里的解释，出处写作 [term.<id>]。
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from app.models import Term

GLOSSARY_FILE = Path(__file__).parent / "glossary.json"


@lru_cache(maxsize=1)
def load_glossary() -> tuple[Term, ...]:
    data = json.loads(GLOSSARY_FILE.read_text(encoding="utf-8"))
    return tuple(Term(**t) for t in data["terms"])


@lru_cache(maxsize=1)
def _matcher() -> tuple[re.Pattern, dict[str, Term]]:
    names: dict[str, Term] = {}
    for t in load_glossary():
        for n in (t.term, *t.aliases):
            names.setdefault(n, t)
    # 长的写法排前面："失信被执行人"不会被认成"被执行人"
    return re.compile("|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))), names


def find_terms(text: str) -> list[Term]:
    """text 里出现的名词，按第一次出现的顺序，每个只算一次。"""
    pattern, names = _matcher()
    seen, out = set(), []
    for m in pattern.finditer(text or ""):
        t = names[m.group(0)]
        if t.id not in seen:
            seen.add(t.id)
            out.append(t)
    return out


def term_ref(t: Term) -> str:
    return f"term.{t.id}"

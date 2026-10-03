"""Small, explicit conversational routes; never a substitute for company evidence.

Only a whole-message definition or an ambiguous investment opener can take an
early route. Mixed questions and selected factual entries keep the normal
evidence/coverage pipeline. No model-classified 'intent' can waive those checks.
"""
import re

from app.glossary import load_glossary
from app.models import Term


def _clean(text: str) -> str:
    return re.sub(r"[\s\"“”‘’「」『』]", "", text).strip("？?。！!")


_PREFIX = r"(?:(?:请问|请|麻烦|能不能|能|可以|我想知道|我想问|我想了解|告诉我|帮我|给我|问一下))*"
_DEFINITION = re.compile(
    _PREFIX + r"(?:什么是|什么叫|何为|怎么理解|(?:用大白话|通俗地)?解释(?:一下)?)(?P<before>.+?)(?:这个词(?:的意思|的含义)?|的意思|的含义)?(?:吗|呢)?$"
    r"|" + _PREFIX + r"(?P<after>.+?)(?:这个词)?(?:是什么意思|是什么|啥意思|什么意思|指什么|怎么理解|的含义|的意思)(?:吗|呢)?$"
    r"|" + _PREFIX + r"(?P<compare>.+?)(?:有什么区别|的区别)(?:吗|呢)?$"
)
_NOT_A_TERM = re.compile(
    r"这|那|它|他|她|我|你|公司|企业|银行|报告|材料|合同里|条款|"
    r"是否|是不是|能否|能不能|可以|值得|安全吗|怎么样|多少|为什么|风险|判赔|退款|投资|"
    r"本案|本次|结果|条数|数量|多不多"
)


def definition_terms(text: str) -> list[Term] | None:
    """None: company/mixed question; []: pure but unknown term; else snapshots.

    Only curated terms are definition evidence. Historical model-generated
    report explanations are not silently promoted to general knowledge.
    """
    query = _clean(text)
    names = {name: term for term in load_glossary() for name in (term.term, *term.aliases)}
    match = _DEFINITION.fullmatch(query)
    # A bare report label ("登记状态") can request this company's actual value;
    # do not silently turn it into a generic definition.
    if not match:
        return None
    target = next((value for value in match.groups() if value), "")
    targets = [target] if target in names else re.split(r"和|与|、|及", target)
    if len(targets) > 3 or any(not t for t in targets):
        return None
    if any(t not in names for t in targets):
        # Do not swallow mixed clauses, company questions, or quoted instructions.
        if all(re.fullmatch(r"[\u4e00-\u9fffA-Za-z]{2,24}", t) and not _NOT_A_TERM.search(t)
               and not any(name in t for name in names)
               for t in targets):
            return []
        return None
    found = []
    for name in targets:
        term = names[name].model_copy(deep=True)
        # Status aliases denote different states, not synonyms. Answer the state
        # actually asked about using a verbatim sentence from the vetted entry.
        if term.id == "status" and name in {"存续", "吊销", "注销"}:
            sentence = next((s for s in re.findall(r"“(?:存续|吊销|注销)”[^“]+", term.plain)
                             if s.startswith(f"“{name}”")), None)
            if sentence:
                term.term, term.plain = name, sentence.strip()
        if any(t.id == term.id for t in found):
            # Comparing aliases of the same term needs the complete definition.
            found = [t for t in found if t.id != term.id]
            term = names[name].model_copy(deep=True)
        found.append(term)
    return found


def current_terms(terms: list[Term]) -> list[Term]:
    """Refresh known definitions for new replies, never mutate saved versions."""
    reviewed = {t.id: t for t in load_glossary()}
    return [reviewed.get(t.id, t).model_copy(deep=True) for t in terms]


def needs_investment_clarification(text: str, refs: list[str]) -> bool:
    """A narrowly anchored opener, never a coverage exemption for a real claim."""
    if refs:
        return False
    query = _clean(text)
    return bool(re.fullmatch(
        r"(?:请问|帮我看看|想问一下)?(?:我|我们)?(?:想|准备|打算)?"
        r"(?:投资|投)(?:一下)?(?:这家公司|这个公司|这家企业|这家|它|该公司)"
        r"(?:怎么样|如何|好不好|值得吗|可以吗|行不行|合适吗|要注意什么|需要注意什么)?", query
    ))

"""Resolve explicit save requests to existing, version-bound answer snapshots.

This module proposes a browser action. It never writes the library, creates a
definition, edits a report, or treats a mixed company question as a save request.
"""
import re

from app.models import Case, ChatMessage, LibrarySaveAction, Version
from app.sources.collect import now


_PREFIX = r"(?:(?:请|麻烦|劳驾)(?:你)?)?(?:帮我|替我|给我|我想|我要)?"
_DESTINATION = r"(?:我的)?(?:知识库|收藏夹)"
_COMMANDS = [re.compile(_PREFIX + command) for command in (
    r"(?:把|将)(?P<target>.+?)(?:收藏|保存)(?:到|进|入)?" + _DESTINATION,
    r"(?:把|将)(?P<target>.+?)(?:收进|收入|存入|加入|记进|记入)" + _DESTINATION,
    r"(?:把|将)(?P<target>.+?)(?:收藏(?:一下|起来)?|保存(?:一下|下来)?|记下来|记录下来)",
    r"(?:收藏|保存)(?:一下)?(?P<target>.+?)(?:(?:到|进|入)" + _DESTINATION + r")?",
)]
_POINTERS = {
    "这一词", "这个词", "这词", "该词", "这个名词", "这一名词", "这个术语", "该术语",
    "这个词条", "这条解释", "这个解释", "刚才的解释", "刚才解释的词", "刚才那个词",
    "刚才讲的词", "上一个词", "上面那个词", "这些词", "这几个词", "刚才的词",
}
# Keep clauses, negation, conditions, reported speech and company investigations
# out of the small imperative grammar, including when punctuation is omitted.
_CLAUSE = re.compile(
    r"不要|不想|不用|不必|别|不收藏|不保存|取消|如果|假如|假设|是否|能否|能不能|"
    r"应该|吗|呢|如何|怎么|为什么|什么|有没有|有无|多少|多大|多高|多低|看看|"
    r"这家|该公司|这公司|本公司|它|你|"
    r"然后|顺便|并|还有|以及|同时|之后|之前|的话|告诉|说|再|或|但|查|核对|分析|判断|"
    r"收藏|保存|记下来|收进|存入|"
    r"[和与及]"
)


def save_target(text: str) -> str | None:
    """Only a complete, affirmative imperative enters the action route."""
    if "\n" in text or "\r" in text:
        return None
    query = re.sub(r"\s+", "", text).rstrip("。！!").removesuffix("吧")
    for command in _COMMANDS:
        match = command.fullmatch(query)
        if not match:
            continue
        target = match["target"]
        if target in _POINTERS:
            return target
        # Quoted term names are fine; quoted commands are not matched above.
        if len(target) > 2 and (target[0], target[-1]) in {("“", "”"), ("「", "」"), ("『", "』"), ('"', '"'), ("'", "'")}:
            target = target[1:-1]
        target = re.sub(r"(?:这个(?:名词|术语|词)|的(?:解释|定义))$", "", target)
        names = re.split(r"[和与、]", target)
        if 1 <= len(names) <= 3 and all(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]{2,24}", name)
                                      and not _CLAUSE.search(name) for name in names):
            return target
    return None


def _recent_explanation(case: Case, version: int) -> ChatMessage | None:
    for message in reversed(case.chat):
        if message.role != "assistant" or message.version != version:
            continue
        if message.answer_kind == "library_action":
            continue
        # A different topic ends the referent; do not revive a stale explanation.
        return message if message.answer_kind == "glossary" else None
    return None


def build_library_reply(case: Case, version: Version, text: str, refs: list[str]) -> ChatMessage | None:
    target = save_target(text)
    if target is None:
        return None
    base = dict(role="assistant", version=version.no, created_at=now(), refs=refs,
                mode="template", answer_kind="library_action")
    if refs:
        return ChatMessage(text="你还选中了报告条目。请先取消条目选择，再告诉我想收藏哪个词；收藏不会修改报告。", **base)
    message = _recent_explanation(case, version.no)
    if not message or not message.knowledge_terms:
        return ChatMessage(text="还没有找到本版对话中刚解释过的词条。请先告诉我想解释哪个词，再把解释收藏到知识库。", **base)
    terms = message.knowledge_terms
    if len({term.id for term in terms}) != len(terms):
        # Resolve identity before narrowing by a shown name: different labels
        # can share a library key (for example status aliases), so filtering
        # first could turn an ambiguous snapshot into an automatic write.
        return ChatMessage(text="这次解释里的词条尚不能唯一对应，暂未保存。请重新询问想收藏的具体词语。", **base)
    if target not in _POINTERS:
        # Match a shown term name, not an alias of a differently scoped snapshot.
        # For example, a saved explanation of 存续 can retain aliases for 注销.
        names = {name.casefold() for name in re.split(r"[和与、]", target)}
        terms = [term for term in terms if re.sub(r"\s+", "", term.term).casefold() in names]
        found = {re.sub(r"\s+", "", term.term).casefold() for term in terms}
        if found != names:
            return ChatMessage(text="刚才的解释里没有找到你指定的词条。请先让我解释这个词，再收藏对应解释。", **base)
    action = LibrarySaveAction(terms=[term.model_copy(deep=True) for term in terms],
                               source_version=message.version, auto_save=len(terms) == 1)
    return ChatMessage(text="已找到你要收藏的词条，保存结果见下方。" if action.auto_save
                       else "刚才解释了多个词，请在下方选择要收藏的词条。",
                       library_action=action, **base)

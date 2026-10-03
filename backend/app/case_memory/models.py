from typing import Literal

from pydantic import BaseModel, Field


class Locator(BaseModel):
    raw_id: str
    path: list[str | int] = Field(default_factory=list)
    # JSON path only; no invented page numbers or character-cut excerpts.


class EvidenceCard(BaseModel):
    card_id: str
    topics: list[str]
    statement_type: str
    summary: str
    fact_refs: list[str] = Field(default_factory=list)
    raw_refs: list[str] = Field(default_factory=list)
    locators: list[Locator] = Field(default_factory=list)
    coverage: str = ""
    conditions: list[str] = Field(default_factory=list)
    related_cards: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)


class EvidenceUnit(BaseModel):
    unit_id: str
    locator: Locator
    topics: list[str]
    keywords: list[str]
    chars: int
    # No second copy of the raw content in the index.


class CaseMemory(BaseModel):
    schema_version: int = 1
    case_id: str
    version_no: int
    owner_key: str
    source_manifest_hash: str
    ruleset_version: str
    builder_version: str
    state: Literal["building", "ready", "failed"] = "building"
    overview: dict = Field(default_factory=dict)
    cards: list[EvidenceCard] = Field(default_factory=list)
    evidence_index: list[EvidenceUnit] = Field(default_factory=list)
    built_at: str = ""
    warnings: list[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    intent: str
    topics: list[str]
    selected_cards: list[str] = Field(default_factory=list)
    provided_refs: list[str] = Field(default_factory=list)
    raw_leaves: dict[str, list[str]] = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    missing_topics: list[str] = Field(default_factory=list)
    omitted_units: list[str] = Field(default_factory=list)
    complete: bool = True
    reasons: list[str] = Field(default_factory=list)

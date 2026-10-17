"""Strict Pydantic contracts shared by extraction, API, and report storage."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Feature(StrictModel):
    id: str = Field(pattern=r"^F[1-9][0-9]*$")
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=240)


class ProposalProfile(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=600)
    problem: str = Field(min_length=1, max_length=500)
    target_users: list[str] = Field(min_length=1, max_length=6)
    features: list[Feature] = Field(min_length=3, max_length=12)
    tech_stack: list[str] = Field(default_factory=list)
    domain_tags: list[str] = Field(min_length=2, max_length=8)
    novelty_claims: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("domain_tags")
    @classmethod
    def tags_are_lowercase(cls, values: list[str]) -> list[str]:
        if any(tag != tag.lower() for tag in values):
            raise ValueError("domain_tags must be lowercase")
        return values

    @model_validator(mode="after")
    def feature_ids_are_unique(self):
        ids = [feature.id for feature in self.features]
        if len(set(ids)) != len(ids):
            raise ValueError("feature ids must be unique")
        return self


class ReadmeChunk(StrictModel):
    chunk_id: str
    section: str
    text: str


class RepoProfile(ProposalProfile):
    repo_id: str = Field(pattern=r"^[a-z0-9_.-]+/[a-z0-9_.-]+$")
    url: str
    stars: int = Field(ge=0)
    last_updated: str
    topics: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    readme_chunks: list[ReadmeChunk] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    description: str | None = None
    readme_chars: int | None = Field(default=None, ge=0)
    readme_lang: str | None = None
    file_tree_top: list[str] | None = None
    profile_source: Literal["llm", "heuristic"] = "heuristic"
    profile_confidence: Literal["high", "medium", "low"] = "low"


class Evidence(StrictModel):
    chunk_id: str
    snippet: str = Field(max_length=240)
    source_url: str


class NoEvidence(StrictModel):
    status: Literal["no evidence"]


class FeatureMatch(StrictModel):
    proposal_feature_id: str
    repo_feature: str
    verdict: Literal["same", "partial", "different"]
    explanation: str
    evidence: Evidence | NoEvidence


class ComparisonResult(StrictModel):
    repo_id: str
    overall_overlap: float = Field(ge=0, le=100)
    label: Literal["near_duplicate", "strong_overlap", "partial_overlap", "related", "distinct"]
    breakdown: dict[str, float]
    feature_matches: list[FeatureMatch] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    cosine_raw: dict[str, float] | None = None
    notes: list[str] = Field(default_factory=list)
    retrieval: dict[str, int | None] | None = None

    @model_validator(mode="after")
    def score_breakdown_is_bounded(self):
        if any(value < 0 or value > 1 for value in self.breakdown.values()):
            raise ValueError("breakdown scores must be between 0 and 1")
        return self


class Recommendation(StrictModel):
    rank: int = Field(ge=1, le=5)
    change: str
    why_distinctive: str
    grounded_in_gap: str
    effort: Literal["S", "M", "L"]
    feasible_in_hackathon: bool


class Gap(StrictModel):
    gap_id: str
    angle: str
    why_open: str
    supporting_gap: str


class NoveltyReport(StrictModel):
    novelty_score: float = Field(ge=0, le=100)
    score_breakdown: dict[str, object]
    confidence: Literal["high", "medium", "low"]
    commodity_features: list[dict[str, object]] = Field(default_factory=list)
    unique_features: list[dict[str, str]] = Field(default_factory=list)
    white_space: list[Gap] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def recommendations_reference_real_gaps(self):
        gap_ids = {gap.gap_id for gap in self.white_space}
        if any(rec.grounded_in_gap not in gap_ids for rec in self.recommendations):
            raise ValueError("recommendation references an unknown gap")
        return self


def evidence_is_substring(snippet: str, source: str) -> bool:
    """Guard evidence by exact substring after case and whitespace normalization."""
    normalize = lambda value: " ".join(value.casefold().split())
    return bool(normalize(snippet)) and normalize(snippet) in normalize(source)

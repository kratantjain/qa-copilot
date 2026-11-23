"""Typed data models shared by the engine, exporters, CLI and UI."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

    @classmethod
    def parse(cls, value: Any) -> "Priority":
        v = str(value or "").strip().lower()
        if v in {"high", "critical", "p0", "p1", "blocker"}:
            return cls.HIGH
        if v in {"low", "minor", "p3", "p4"}:
            return cls.LOW
        return cls.MEDIUM


class Category(str, Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
    BOUNDARY = "Boundary"
    EDGE = "Edge Case"
    REGRESSION = "Regression"
    SECURITY = "Security"
    PERFORMANCE = "Performance"
    ACCESSIBILITY = "Accessibility"

    @classmethod
    def parse(cls, value: Any) -> "Category":
        v = " ".join(str(value or "").lower().replace("_", " ").replace("-", " ").split())
        table = {
            "positive": cls.POSITIVE, "happy path": cls.POSITIVE, "positive testing": cls.POSITIVE,
            "negative": cls.NEGATIVE, "negative testing": cls.NEGATIVE,
            "boundary": cls.BOUNDARY, "boundary value": cls.BOUNDARY, "boundary testing": cls.BOUNDARY,
            "edge": cls.EDGE, "edge case": cls.EDGE, "edge cases": cls.EDGE,
            "regression": cls.REGRESSION, "regression testing": cls.REGRESSION,
            "security": cls.SECURITY, "performance": cls.PERFORMANCE, "load": cls.PERFORMANCE,
            "accessibility": cls.ACCESSIBILITY, "a11y": cls.ACCESSIBILITY,
        }
        return table.get(v, cls.POSITIVE)


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "; ".join(_text(v) for v in value if _text(v))
    return str(value).strip() or default


def _parse_priority(value: Any) -> "Priority":
    return Priority.parse(value)


def _parse_category(value: Any) -> "Category":
    return Category.parse(value)


def _to_text(value: Any) -> str:
    return _text(value)


class Finding(BaseModel):
    """A gap, ambiguity or conflict discovered in a requirement."""

    id: str = ""
    kind: str = "gap"  # gap | ambiguity | conflict
    title: str = "Requirement finding"
    observation: str = ""
    business_impact: str = ""
    qa_impact: str = ""
    priority: Priority = Priority.MEDIUM

    _clean = field_validator("id", "title", "observation", "business_impact", "qa_impact",
                             mode="before")(_to_text)
    _prio = field_validator("priority", mode="before")(_parse_priority)


class Question(BaseModel):
    id: str = ""
    question: str = ""
    why_it_matters: str = ""
    related_area: str = ""
    priority: Priority = Priority.MEDIUM
    related_finding_ids: list[str] = Field(default_factory=list)

    _clean = field_validator("id", "question", "why_it_matters", "related_area",
                             mode="before")(_to_text)
    _prio = field_validator("priority", mode="before")(_parse_priority)

    @field_validator("related_finding_ids", mode="before")
    @classmethod
    def _ids(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [v]
        return [_text(i) for i in (v or []) if _text(i)]


class Dependency(BaseModel):
    system: str = ""
    purpose: str = ""
    interface: str = ""
    qa_considerations: str = ""

    _clean = field_validator("*", mode="before")(_to_text)


class Risk(BaseModel):
    """Risk with a simple likelihood x impact score (1-5 each)."""

    description: str
    likelihood: int = 3
    impact: int = 3
    mitigation: str = ""

    @field_validator("likelihood", "impact", mode="before")
    @classmethod
    def _scale(cls, v: Any) -> int:
        try:
            return max(1, min(5, int(float(v))))
        except (TypeError, ValueError):
            return 3

    @field_validator("description", "mitigation", mode="before")
    @classmethod
    def _t(cls, v: Any) -> str:
        return _text(v)

    @property
    def score(self) -> int:
        return self.likelihood * self.impact

    @property
    def level(self) -> str:
        return "Critical" if self.score >= 16 else "High" if self.score >= 10 else \
            "Medium" if self.score >= 5 else "Low"


class Analysis(BaseModel):
    summary: str = ""
    gaps: list[Finding] = Field(default_factory=list)
    ambiguities: list[Finding] = Field(default_factory=list)
    conflicts: list[Finding] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    readiness_score: int = 0  # 0-100
    readiness_verdict: str = "Needs clarification"

    @property
    def findings(self) -> list[Finding]:
        return [*self.gaps, *self.ambiguities, *self.conflicts]


class TestCase(BaseModel):
    __test__ = False  # not a pytest class

    id: str = ""
    category: Category = Category.POSITIVE
    area: str = ""
    scenario: str
    preconditions: str = ""
    test_data: str = ""
    steps: list[str] = Field(default_factory=list)
    expected: str = ""
    priority: Priority = Priority.MEDIUM
    automatable: bool = True
    traces_to: list[str] = Field(default_factory=list)  # acceptance-criteria / finding ids

    _cat = field_validator("category", mode="before")(_parse_category)
    _prio = field_validator("priority", mode="before")(_parse_priority)

    @field_validator("scenario", "area", "preconditions", "test_data", "expected", mode="before")
    @classmethod
    def _t(cls, v: Any) -> str:
        return _text(v)

    @field_validator("steps", mode="before")
    @classmethod
    def _steps(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [ln.strip() for ln in v.splitlines()]
        return [_text(s) for s in (v or []) if _text(s)] or ["Execute the described scenario."]

    @field_validator("traces_to", mode="before")
    @classmethod
    def _tr(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [x.strip() for x in v.replace(";", ",").split(",")]
        return [_text(i) for i in (v or []) if _text(i)]

    @field_validator("automatable", mode="before")
    @classmethod
    def _auto(cls, v: Any) -> bool:
        if isinstance(v, str):
            return v.strip().lower() not in {"no", "false", "manual", "0"}
        return bool(v) if v is not None else True


class Suite(BaseModel):
    story: str
    test_cases: list[TestCase] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ClarificationRound(BaseModel):
    answers: str
    resolved: list[str] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)
    new_questions: list[Question] = Field(default_factory=list)
    updated_story: str = ""

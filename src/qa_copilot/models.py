"""Typed data models shared by the engine, exporters, CLI and UI.

Plain dataclasses (no third-party dependency) so the project installs anywhere
without a compiler toolchain.
Every model coerces untrusted LLM output in ``__post_init__``.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T")


class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

    @classmethod
    def parse(cls, value: Any) -> Priority:
        if isinstance(value, cls):
            return value
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
    def parse(cls, value: Any) -> Category:
        if isinstance(value, cls):
            return value
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


# --------------------------------------------------------------------------- helpers

def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "; ".join(_text(v) for v in value if _text(v))
    return str(value).strip() or default


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [_text(v) for v in value if _text(v)]


def _scale(value: Any) -> int:
    try:
        return max(1, min(5, int(float(value))))
    except (TypeError, ValueError):
        return 3


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"no", "false", "manual", "0"}
    return True if value is None else bool(value)


def pick(cls: type[T], raw: dict, **extra: Any) -> T:
    """Build ``cls`` from a dict, ignoring unknown keys."""
    names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    return cls(**{k: v for k, v in raw.items() if k in names}, **extra)  # type: ignore[call-arg]


def to_dict(obj: Any) -> Any:
    """Recursively convert models/enums to JSON-friendly primitives."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_dict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


# --------------------------------------------------------------------------- models

@dataclass
class Finding:
    """A gap, ambiguity or conflict discovered in a requirement."""

    id: str = ""
    kind: str = "gap"  # gap | ambiguity | conflict
    title: str = ""
    observation: str = ""
    business_impact: str = ""
    qa_impact: str = ""
    priority: Priority = Priority.MEDIUM

    def __post_init__(self):
        for name in ("id", "kind", "title", "observation", "business_impact", "qa_impact"):
            setattr(self, name, _text(getattr(self, name)))
        self.priority = Priority.parse(self.priority)


@dataclass
class Question:
    id: str = ""
    question: str = ""
    why_it_matters: str = ""
    related_area: str = ""
    priority: Priority = Priority.MEDIUM
    related_finding_ids: list[str] = field(default_factory=list)

    def __post_init__(self):
        for name in ("id", "question", "why_it_matters", "related_area"):
            setattr(self, name, _text(getattr(self, name)))
        self.priority = Priority.parse(self.priority)
        self.related_finding_ids = _str_list(self.related_finding_ids)


@dataclass
class Dependency:
    system: str = ""
    purpose: str = ""
    interface: str = ""
    qa_considerations: str = ""

    def __post_init__(self):
        for f in fields(self):
            setattr(self, f.name, _text(getattr(self, f.name)))


@dataclass
class Risk:
    """Risk with a simple likelihood x impact score (1-5 each)."""

    description: str = ""
    likelihood: int = 3
    impact: int = 3
    mitigation: str = ""

    def __post_init__(self):
        self.description = _text(self.description)
        self.mitigation = _text(self.mitigation)
        self.likelihood = _scale(self.likelihood)
        self.impact = _scale(self.impact)

    @property
    def score(self) -> int:
        return self.likelihood * self.impact

    @property
    def level(self) -> str:
        return "Critical" if self.score >= 16 else "High" if self.score >= 10 else \
            "Medium" if self.score >= 5 else "Low"


@dataclass
class Analysis:
    summary: str = ""
    gaps: list[Finding] = field(default_factory=list)
    ambiguities: list[Finding] = field(default_factory=list)
    conflicts: list[Finding] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    readiness_score: int = 0  # 0-100
    readiness_verdict: str = "Needs clarification"

    @property
    def findings(self) -> list[Finding]:
        return [*self.gaps, *self.ambiguities, *self.conflicts]

    @classmethod
    def from_dict(cls, d: dict) -> Analysis:
        d = dict(d)
        for key, model in (("gaps", Finding), ("ambiguities", Finding), ("conflicts", Finding),
                           ("dependencies", Dependency), ("risks", Risk), ("questions", Question)):
            d[key] = [pick(model, i) for i in d.get(key) or []]
        return pick(cls, d)


@dataclass
class TestCase:
    __test__ = False  # not a pytest class

    scenario: str = ""
    id: str = ""
    category: Category = Category.POSITIVE
    area: str = ""
    preconditions: str = ""
    test_data: str = ""
    steps: list[str] = field(default_factory=list)
    expected: str = ""
    priority: Priority = Priority.MEDIUM
    automatable: bool = True
    traces_to: list[str] = field(default_factory=list)  # acceptance-criteria / finding ids

    def __post_init__(self):
        for name in ("scenario", "id", "area", "preconditions", "test_data", "expected"):
            setattr(self, name, _text(getattr(self, name)))
        if not self.scenario:
            raise ValueError("test case needs a scenario")
        self.category = Category.parse(self.category)
        self.priority = Priority.parse(self.priority)
        steps = self.steps
        if isinstance(steps, str):
            steps = steps.splitlines()
        self.steps = _str_list(steps) or ["Execute the described scenario."]
        traces = self.traces_to
        if isinstance(traces, str):
            traces = [x.strip() for x in traces.replace(";", ",").split(",")]
        self.traces_to = _str_list(traces)
        self.automatable = _bool(self.automatable)


@dataclass
class Suite:
    story: str = ""
    test_cases: list[TestCase] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Suite:
        d = dict(d)
        d["test_cases"] = [pick(TestCase, c) for c in d.get("test_cases") or []]
        return pick(cls, d)


@dataclass
class ClarificationRound:
    answers: str = ""
    resolved: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)
    new_questions: list[Question] = field(default_factory=list)
    updated_story: str = ""

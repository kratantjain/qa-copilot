"""Core orchestration: analyse -> clarify -> generate."""
from __future__ import annotations

import re
from typing import Callable

from .json_utils import extract_json
from .models import (
    Analysis,
    Category,
    ClarificationRound,
    Dependency,
    Finding,
    Question,
    Risk,
    Suite,
    TestCase,
    pick,
)
from .prompts import SYSTEM, analyze_prompt, generate_prompt, reassess_prompt
from .providers import LLMError, Provider

DEFAULT_SPEC = {"Positive": 4, "Negative": 4, "Boundary": 3, "Edge Case": 3, "Regression": 3}
DOMAINS = ("General", "E-commerce / Retail", "Payments / Fintech", "Healthcare", "Embedded / Devices",
           "API / Microservices", "Mobile", "Data / ETL")
ProgressFn = Callable[[str], None]


def _call(provider: Provider, prompt: str, max_tokens: int, retries: int = 1) -> dict:
    """Call the LLM and parse JSON, retrying once with a repair hint."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        p = prompt if attempt == 0 else prompt + "\n\nYour previous reply was not valid JSON. " \
            "Reply again with ONLY the JSON object."
        try:
            return extract_json(provider.complete(SYSTEM, p, max_tokens))
        except LLMError as e:
            last = e
    raise LLMError(str(last))


def _findings(items, kind: str, prefix: str) -> list[Finding]:
    out = []
    for i, raw in enumerate(items or [], 1):
        raw = raw if isinstance(raw, dict) else {"observation": str(raw)}
        f = pick(Finding, {**raw, "kind": kind})
        f.id = f.id or f"{prefix}-{i:03d}"
        f.title = f.title or "Requirement finding"
        out.append(f)
    return out


def _models(items, model):
    out = []
    for raw in items or []:
        if not isinstance(raw, dict):
            raw = {"description": str(raw)} if model is Risk else {"question": str(raw)}
        try:
            out.append(pick(model, raw))
        except (TypeError, ValueError):
            continue
    return out


_PLACEHOLDERS = ("testable, atomic", "derived from the story", "specific scenario",
                 "<one atomic", "<specific", "<action", "<observable", "short title")


def is_placeholder(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in _PLACEHOLDERS) or (t.startswith("<") and t.endswith(">"))


def _strings(items) -> list[str]:
    if isinstance(items, str):
        items = [items]
    return [str(i).strip() for i in (items or []) if str(i).strip()]


def _drop_similar(items: list[Finding], existing: list[Finding], threshold: float = 0.6):
    """Small models often report one issue as both a gap and an ambiguity - keep the first."""
    return [f for f in items
            if not any(similarity(f.title + " " + f.observation, e.title + " " + e.observation)
                       >= threshold for e in existing)]


def readiness(a: Analysis) -> tuple[int, str]:
    """Deterministic readiness score so results are comparable across models."""
    penalty = 0
    weights = {"High": 12, "Medium": 6, "Low": 2}
    for f in a.findings:
        penalty += weights[f.priority.value] * (2 if f.kind == "conflict" else 1)
    score = max(0, 100 - penalty)
    if not a.acceptance_criteria:
        score = min(score, 60)
    verdict = ("Ready for test design" if score >= 80 else
               "Ready with assumptions" if score >= 60 else "Needs clarification")
    return score, verdict


def analyze(provider: Provider, story: str, domain: str = "General") -> Analysis:
    if not story.strip():
        raise ValueError("Please enter a requirement or user story.")
    d = _call(provider, analyze_prompt(story, domain), 4096)
    qs = _models(d.get("questions"), Question)
    for i, q in enumerate(qs, 1):
        q.id = q.id or f"Q-{i:03d}"
    acs = [a for a in _strings(d.get("acceptance_criteria")) if not is_placeholder(a)]
    acs = [a if a.upper().startswith("AC-") else f"AC-{i}: {a}" for i, a in enumerate(acs, 1)]
    gaps = _findings(d.get("gaps"), "gap", "GAP")
    ambiguities = _drop_similar(_findings(d.get("ambiguities"), "ambiguity", "AMB"), gaps)
    conflicts = _drop_similar(_findings(d.get("conflicts"), "conflict", "CON"),
                              gaps + ambiguities)
    a = Analysis(
        summary=str(d.get("summary", "")).strip(),
        gaps=gaps, ambiguities=ambiguities, conflicts=conflicts,
        dependencies=_models(d.get("dependencies"), Dependency),
        risks=sorted(_models(d.get("risks"), Risk), key=lambda r: -r.score),
        questions=qs,
        assumptions=_strings(d.get("assumptions")),
        acceptance_criteria=acs,
    )
    a.readiness_score, a.readiness_verdict = readiness(a)
    return a


def reassess(provider: Provider, story: str, analysis: Analysis, answers: str) -> ClarificationRound:
    if not answers.strip():
        raise ValueError("Please provide BA / PO answers.")
    findings = "\n".join(f"{f.id}: {f.title} - {f.observation}" for f in analysis.findings)
    questions = "\n".join(f"{q.id}: {q.question}" for q in analysis.questions)
    d = _call(provider, reassess_prompt(story, questions, answers, findings), 2048)
    return ClarificationRound(
        answers=answers, resolved=_strings(d.get("resolved")),
        remaining=_strings(d.get("remaining")),
        new_questions=_models(d.get("new_questions"), Question),
        updated_story=str(d.get("updated_story", "") or "").strip())


_HUMAN_HINTS = ("visual", "look and feel", "appearance", "usability", "aesthetic", "readab",
                "screen reader", "subjective", "manually verify", "color contrast", "colour")


def needs_human(case: TestCase) -> bool:
    """Deterministic automatable/manual call - small LLMs set this flag unreliably."""
    text = " ".join([case.scenario, case.expected, *case.steps]).lower()
    return case.category is Category.ACCESSIBILITY or any(h in text for h in _HUMAN_HINTS)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def similarity(a: str, b: str) -> float:
    """Jaccard similarity of word sets (0-1)."""
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def is_duplicate(a: TestCase, b: TestCase) -> bool:
    """Same category, same test data, near-identical steps and a similar scenario."""
    if a.category is not b.category:
        return False
    if _norm(a.scenario) == _norm(b.scenario):
        return True
    return (_norm(a.test_data) == _norm(b.test_data)
            and similarity(" ".join(a.steps), " ".join(b.steps)) >= 0.8
            and similarity(a.scenario, b.scenario) >= 0.5)


def dedupe(cases: list[TestCase]) -> list[TestCase]:
    """Drop exact repeats and near-duplicates (keeps the first occurrence)."""
    out: list[TestCase] = []
    for c in cases:
        if _norm(c.scenario) and not any(is_duplicate(o, c) for o in out):
            out.append(c)
    return out


_ID_ONLY = re.compile(r"^[A-Za-z]{2,5}-\d+$")


def _clean_notes(items: list[str]) -> list[str]:
    return sorted({i for i in items if not _ID_ONLY.match(i) and not is_placeholder(i)})


def generate(provider: Provider, story: str, analysis: Analysis | None = None,
             domain: str = "General", spec: dict[str, int] | None = None,
             progress: ProgressFn | None = None) -> Suite:
    """Generate test cases category-by-batch so small local models stay within token limits."""
    if not story.strip():
        raise ValueError("Please enter a requirement or user story.")
    spec = {k: v for k, v in (spec or DEFAULT_SPEC).items() if v > 0}
    if not spec:
        raise ValueError("Select at least one category.")
    context = ""
    if analysis:
        context = "\n".join(analysis.acceptance_criteria) + "\n" + "\n".join(
            f"{f.id}: {f.title}" for f in analysis.findings)
    batches, cur, size = [], {}, 0
    for cat, n in spec.items():  # <=8 cases per LLM call
        if cur and size + n > 8:
            batches.append(cur)
            cur, size = {}, 0
        cur[cat] = n
        size += n
    if cur:
        batches.append(cur)

    cases, assumptions, gaps = [], [], []
    for i, batch in enumerate(batches, 1):
        if progress:
            progress(f"Generating batch {i}/{len(batches)}: {', '.join(batch)}")
        d = _call(provider, generate_prompt(story, domain, batch, context), 4096)
        for raw in d.get("test_cases") or []:
            if not isinstance(raw, dict):
                raw = {"scenario": str(raw)}
            if not (raw.get("scenario") or raw.get("title")):
                continue
            raw = {**raw, "scenario": raw.get("scenario") or raw.get("title")}
            if is_placeholder(str(raw["scenario"])):
                continue
            try:
                cases.append(pick(TestCase, raw))
            except (TypeError, ValueError):
                continue
        assumptions += _strings(d.get("assumptions"))
        gaps += _strings(d.get("gaps"))
    cases = dedupe(cases)

    # One top-up pass for categories that came back short (common with small models).
    short = {cat: n - sum(c.category.value == cat for c in cases) for cat, n in spec.items()}
    short = {cat: min(n, 4) for cat, n in short.items() if n > 0}
    if short:
        if progress:
            progress(f"Top-up pass for: {', '.join(short)}")
        avoid = "\n".join(f"- {c.scenario}" for c in cases)
        try:
            d = _call(provider, generate_prompt(story, domain, short, context, avoid), 4096)
            for raw in d.get("test_cases") or []:
                if isinstance(raw, dict) and (raw.get("scenario") or raw.get("title")):
                    raw = {**raw, "scenario": raw.get("scenario") or raw.get("title")}
                    if is_placeholder(str(raw["scenario"])):
                        continue
                    try:
                        cases.append(pick(TestCase, raw))
                    except (TypeError, ValueError):
                        continue
            assumptions += _strings(d.get("assumptions"))
            gaps += _strings(d.get("gaps"))
        except LLMError:
            pass  # top-up is best effort
        cases = dedupe(cases)
    for c in cases:
        c.automatable = not needs_human(c)
    if not cases:
        raise LLMError("No usable test cases were generated.")
    order = list(Category)
    cases.sort(key=lambda c: order.index(c.category))
    for n, c in enumerate(cases, 1):
        c.id = f"TC-{n:03d}"
    return Suite(story=story, test_cases=cases, assumptions=_clean_notes(assumptions),
                 gaps=_clean_notes(gaps))

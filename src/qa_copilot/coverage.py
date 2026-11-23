"""Traceability matrix and coverage metrics (no LLM involved - deterministic)."""
from __future__ import annotations

from .models import Analysis, Category, Priority, Suite


def traceability(analysis: Analysis, suite: Suite) -> list[dict]:
    """Rows: each acceptance criterion / finding -> covering test-case ids."""
    items: list[tuple[str, str]] = []
    for ac in analysis.acceptance_criteria:
        key = ac.split(":", 1)[0].strip()
        items.append((key, ac))
    items += [(f.id, f"{f.title}: {f.observation}") for f in analysis.findings]
    rows = []
    for key, text in items:
        covering = [c.id for c in suite.test_cases if key.lower() in (t.lower() for t in c.traces_to)]
        rows.append({"id": key, "requirement": text, "test_cases": covering,
                     "covered": bool(covering)})
    return rows


def coverage_report(analysis: Analysis | None, suite: Suite) -> dict:
    cases = suite.test_cases
    by_cat = {c.value: 0 for c in Category}
    by_pri = {p.value: 0 for p in Priority}
    for c in cases:
        by_cat[c.category.value] += 1
        by_pri[c.priority.value] += 1
    rows = traceability(analysis, suite) if analysis else []
    covered = sum(r["covered"] for r in rows)
    ac_rows = [r for r in rows if r["id"].upper().startswith("AC-")]
    ac_cov = sum(r["covered"] for r in ac_rows)
    return {
        "total": len(cases),
        "by_category": {k: v for k, v in by_cat.items() if v},
        "by_priority": by_pri,
        "automatable_pct": round(100 * sum(c.automatable for c in cases) / len(cases)) if cases else 0,
        "traced_pct": round(100 * covered / len(rows)) if rows else 0,
        "ac_coverage_pct": round(100 * ac_cov / len(ac_rows)) if ac_rows else 0,
        "uncovered": [r["id"] for r in rows if not r["covered"]],
        "missing_categories": [c for c in ("Positive", "Negative", "Boundary", "Edge Case")
                               if by_cat[c] == 0],
    }

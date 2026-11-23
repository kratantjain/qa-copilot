from __future__ import annotations

import csv
import io
import re

from ..coverage import coverage_report, traceability
from ..models import Analysis, Suite, TestCase

COLUMNS = ["ID", "Category", "Area", "Priority", "Scenario", "Preconditions", "Test data",
           "Steps", "Expected result", "Automatable", "Traces to"]


def _row(c: TestCase) -> list[str]:
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(c.steps, 1))
    return [c.id, c.category.value, c.area, c.priority.value, c.scenario, c.preconditions,
            c.test_data, steps, c.expected, "Yes" if c.automatable else "No", ", ".join(c.traces_to)]


def _safe(cell: str) -> str:
    """Neutralise spreadsheet formula injection from LLM-generated text."""
    return "'" + cell if cell[:1] in ("=", "+", "-", "@") else cell


def to_csv(suite: Suite) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    for c in suite.test_cases:
        w.writerow([_safe(x) for x in _row(c)])
    return buf.getvalue()


def to_json(suite: Suite, analysis: Analysis | None = None) -> str:
    import json
    return json.dumps({"analysis": analysis.model_dump(mode="json") if analysis else None,
                       "suite": suite.model_dump(mode="json")}, indent=2)


def to_markdown(suite: Suite, analysis: Analysis | None = None) -> str:
    out = ["# QA Report", ""]
    if analysis:
        out += ["## Requirement analysis", "", analysis.summary, "",
                f"**Readiness:** {analysis.readiness_score}/100 - {analysis.readiness_verdict}", ""]
        for title, items in (("Gaps", analysis.gaps), ("Ambiguities", analysis.ambiguities),
                             ("Conflicts", analysis.conflicts)):
            if items:
                out += [f"### {title}", ""]
                out += [f"- **{f.id}** [{f.priority.value}] {f.title} - {f.observation}"
                        for f in items] + [""]
        if analysis.risks:
            out += ["### Risks", "", "| Risk | L | I | Score | Level | Mitigation |",
                    "|---|---|---|---|---|---|"]
            out += [f"| {r.description} | {r.likelihood} | {r.impact} | {r.score} | {r.level} | "
                    f"{r.mitigation} |" for r in analysis.risks] + [""]
        if analysis.acceptance_criteria:
            out += ["### Acceptance criteria", ""] + [f"- {a}" for a in analysis.acceptance_criteria] + [""]
        if analysis.questions:
            out += ["### Clarification questions", ""]
            out += [f"{i}. **{q.id}** ({q.priority.value}) {q.question}"
                    for i, q in enumerate(analysis.questions, 1)] + [""]
    rep = coverage_report(analysis, suite)
    out += ["## Coverage", "", f"- Total test cases: **{rep['total']}**",
            f"- By category: {rep['by_category']}", f"- Automatable: {rep['automatable_pct']}%"]
    if analysis:
        out += [f"- Acceptance-criteria coverage: {rep['ac_coverage_pct']}%",
                f"- Uncovered items: {', '.join(rep['uncovered']) or 'none'}"]
    out += ["", "## Test cases", ""]
    for c in suite.test_cases:
        out += [f"### {c.id} - {c.scenario}", "",
                f"*{c.category.value} | {c.priority.value} | {c.area or 'n/a'}"
                f"{' | manual' if not c.automatable else ''}*", ""]
        if c.preconditions:
            out.append(f"**Preconditions:** {c.preconditions}  ")
        if c.test_data:
            out.append(f"**Test data:** {c.test_data}  ")
        out += ["", "**Steps:**"] + [f"{i}. {s}" for i, s in enumerate(c.steps, 1)]
        out += ["", f"**Expected:** {c.expected}", ""]
        if c.traces_to:
            out += [f"**Traces to:** {', '.join(c.traces_to)}", ""]
    if suite.assumptions or suite.gaps:
        out += ["## Assumptions and gaps", ""]
        out += [f"- Assumption: {a}" for a in suite.assumptions]
        out += [f"- Gap: {g}" for g in suite.gaps]
    return "\n".join(out).rstrip() + "\n"


def to_gherkin(suite: Suite) -> str:
    out = ["Feature: " + (suite.story.strip().splitlines()[0][:100] if suite.story.strip() else "Feature"),
           ""]
    for c in suite.test_cases:
        tags = [f"@{c.category.value.lower().replace(' ', '-')}", f"@{c.priority.value.lower()}",
                f"@{c.id}"] + [f"@{t}" for t in c.traces_to if re.fullmatch(r"[\w-]+", t)]
        out.append("  " + " ".join(tags))
        out.append(f"  Scenario: {c.scenario}")
        if c.preconditions:
            out.append(f"    Given {c.preconditions}")
        for i, s in enumerate(c.steps):
            out.append(f"    {'When' if i == 0 else 'And'} {s}")
        out.append(f"    Then {c.expected or 'the system behaves as specified'}")
        out.append("")
    return "\n".join(out)


def _ident(text: str) -> str:
    s = re.sub(r"\W+", "_", text.lower()).strip("_")[:50]
    return s if s and not s[0].isdigit() else f"t_{s}"


def to_pytest(suite: Suite) -> str:
    out = ['"""Auto-generated pytest skeleton from QA Copilot. Implement the TODOs."""', "",
           "import pytest", ""]
    for c in suite.test_cases:
        marks = f"@pytest.mark.{c.category.value.lower().replace(' ', '_')}"
        if not c.automatable:
            marks += "\n@pytest.mark.skip(reason='manual test')"
        out += ["", marks, f"def test_{c.id.lower().replace('-', '_')}_{_ident(c.scenario)}():",
                f'    """{c.scenario.replace(chr(34), chr(39))}', "",
                f"    Preconditions: {c.preconditions}", f"    Test data: {c.test_data}",
                f"    Expected: {c.expected}", '    """']
        out += [f"    # TODO step {i}: {s}" for i, s in enumerate(c.steps, 1)]
        out += ['    pytest.skip("TODO: implement")', ""]
    return "\n".join(out)


def to_jira_csv(suite: Suite) -> str:
    """Generic Jira CSV importer layout (one row per issue; steps in description)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Summary", "Issue Type", "Priority", "Labels", "Description"])
    for c in suite.test_cases:
        desc = (f"Preconditions: {c.preconditions}\nTest data: {c.test_data}\nSteps:\n"
                + "\n".join(f"# {s}" for s in c.steps) + f"\nExpected: {c.expected}")
        w.writerow([_safe(f"{c.id} {c.scenario}"), "Test", c.priority.value,
                    " ".join([c.category.value.replace(" ", "-")] + c.traces_to), _safe(desc)])
    return buf.getvalue()


def to_xlsx(suite: Suite, analysis: Analysis | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Test cases"
    ws.append(COLUMNS)
    for c in suite.test_cases:
        ws.append([_safe(x) for x in _row(c)])
    head = PatternFill("solid", fgColor="163246")
    for cell in ws[1]:
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), head
    for col, width in zip("ABCDEFGHIJK", (9, 12, 16, 10, 40, 30, 28, 50, 40, 11, 18)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    if analysis:
        tr = wb.create_sheet("Traceability")
        tr.append(["ID", "Requirement / finding", "Covered", "Test cases"])
        for r in traceability(analysis, suite):
            tr.append([r["id"], _safe(r["requirement"]), "Yes" if r["covered"] else "NO",
                       ", ".join(r["test_cases"])])
        fi = wb.create_sheet("Findings")
        fi.append(["ID", "Type", "Priority", "Title", "Observation", "QA impact"])
        for f in analysis.findings:
            fi.append([f.id, f.kind, f.priority.value, _safe(f.title), _safe(f.observation),
                       _safe(f.qa_impact)])
        rk = wb.create_sheet("Risks")
        rk.append(["Risk", "Likelihood", "Impact", "Score", "Level", "Mitigation"])
        for r in analysis.risks:
            rk.append([_safe(r.description), r.likelihood, r.impact, r.score, r.level,
                       _safe(r.mitigation)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

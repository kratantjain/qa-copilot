import io
import json

import pytest
from openpyxl import load_workbook

from qa_copilot.coverage import coverage_report, traceability
from qa_copilot.engine import analyze, dedupe, generate, reassess
from qa_copilot.exporters import EXPORTERS, export
from qa_copilot.history import History
from qa_copilot.json_utils import extract_json
from qa_copilot.models import Category, Priority, TestCase
from qa_copilot.providers import LLMError, MockProvider

STORY = "As a customer I want to pay by credit card or gift card."


@pytest.fixture
def provider():
    return MockProvider()


@pytest.fixture
def analysis(provider):
    return analyze(provider, STORY)


@pytest.fixture
def suite(provider, analysis):
    return generate(provider, STORY, analysis)


def test_extract_json_handles_fences_and_trailing_commas():
    assert extract_json('```json\n{"a": 1,}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": [1,2,]} done') == {"a": [1, 2]}
    with pytest.raises(LLMError):
        extract_json("no json here")


def test_enum_parsing():
    assert Priority.parse("P1") is Priority.HIGH
    assert Category.parse("happy_path") is Category.POSITIVE
    assert Category.parse("edge-cases") is Category.EDGE
    assert Category.parse("nonsense") is Category.POSITIVE


def test_analysis_fields_and_readiness(analysis):
    assert analysis.gaps[0].id == "GAP-001"
    assert analysis.acceptance_criteria[0].startswith("AC-1")
    assert 0 <= analysis.readiness_score <= 100
    assert analysis.risks[0].score == 15 and analysis.risks[0].level == "High"


def test_analyze_rejects_empty(provider):
    with pytest.raises(ValueError):
        analyze(provider, "   ")


def test_retry_on_bad_json():
    p = MockProvider(responses=["garbage", '{"summary": "ok"}'])
    assert analyze(p, STORY).summary == "ok"
    assert len(p.calls) == 2


def test_generate_batches_and_ids(provider, analysis):
    s = generate(provider, STORY, analysis)
    assert [c.id for c in s.test_cases] == [f"TC-{i:03d}" for i in range(1, len(s.test_cases) + 1)]
    assert len(provider.calls) >= 3  # analysis + >=2 batches (<=8 cases each)
    assert {c.category for c in s.test_cases} >= {Category.POSITIVE, Category.REGRESSION}


def test_generate_custom_spec_includes_new_categories(provider):
    s = generate(provider, STORY, spec={"Security": 2, "Accessibility": 1})
    assert {c.category for c in s.test_cases} == {Category.SECURITY, Category.ACCESSIBILITY}


def test_generate_requires_categories(provider):
    with pytest.raises(ValueError):
        generate(provider, STORY, spec={"Positive": 0})


def test_dedupe():
    a, b = TestCase(scenario="Pay by card"), TestCase(scenario="  pay   BY card ")
    assert len(dedupe([a, b])) == 1


def test_reassess(provider, analysis):
    r = reassess(provider, STORY, analysis, "Q-001: yes, split allowed")
    assert r.resolved == ["GAP-001"]


def test_traceability_and_coverage(analysis, suite):
    rows = {r["id"]: r for r in traceability(analysis, suite)}
    assert rows["AC-1"]["covered"] and rows["AC-2"]["covered"]
    assert not rows["GAP-001"]["covered"]
    rep = coverage_report(analysis, suite)
    assert rep["ac_coverage_pct"] == 100 and "GAP-001" in rep["uncovered"]
    assert rep["missing_categories"] == []


@pytest.mark.parametrize("fmt", list(EXPORTERS))
def test_every_exporter_produces_output(fmt, suite, analysis):
    data, ext = export(fmt, suite, analysis)
    assert data and ext


def test_exports_content(suite, analysis):
    xlsx, _ = export("xlsx", suite, analysis)
    wb = load_workbook(io.BytesIO(xlsx))
    assert wb.sheetnames == ["Test cases", "Traceability", "Findings", "Risks"]
    assert wb["Test cases"].max_row == len(suite.test_cases) + 1
    feature, _ = export("feature", suite, analysis)
    assert b"Scenario:" in feature and b"@AC-1" in feature
    py, _ = export("pytest", suite, analysis)
    compile(py.decode(), "generated", "exec")
    js, _ = export("json", suite, analysis)
    assert json.loads(js)["suite"]["test_cases"]
    with pytest.raises(ValueError):
        export("pdf", suite)


def test_csv_blocks_formula_injection():
    from qa_copilot.models import Suite
    s = Suite(story="x", test_cases=[TestCase(scenario="=HYPERLINK(\"http://evil\")", id="TC-001")])
    data, _ = export("csv", s)
    assert "'=HYPERLINK" in data.decode()


def test_history_roundtrip(analysis, suite):
    h = History(":memory:")
    rid = h.save(STORY, analysis, suite)
    story, a, s = h.load(rid)
    assert story == STORY and a.gaps[0].id == "GAP-001" and len(s.test_cases) == len(suite.test_cases)
    assert h.list()[0]["id"] == rid


def test_cli_end_to_end(tmp_path, capsys):
    from qa_copilot.cli import main
    rc = main(["run", "--provider", "mock", "--story", STORY, "--format", "md,xlsx",
               "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "qa_report.md").read_text().startswith("# QA Report")
    assert (tmp_path / "qa_report.xlsx").stat().st_size > 0


def test_placeholder_text_is_filtered():
    from qa_copilot.engine import is_placeholder
    assert is_placeholder("AC-1: Testable, atomic criterion derived from the story")
    assert not is_placeholder("AC-1: Order is created only after payment succeeds")
    p = MockProvider(responses=['{"acceptance_criteria": ["AC-1: Testable, atomic criterion '
                                'derived from the story", "Orders need payment"]}'])
    a = analyze(p, STORY)
    assert a.acceptance_criteria == ["AC-1: Orders need payment"]
    assert a.readiness_score <= 100


def test_automatable_is_decided_in_code():
    from qa_copilot.engine import needs_human
    assert not needs_human(TestCase(scenario="Pay by card", steps=["Pay"], expected="Order placed"))
    assert needs_human(TestCase(scenario="Check visual appearance of checkout"))
    assert needs_human(TestCase(scenario="Alt text", category="accessibility"))
    s = generate(MockProvider(), STORY, spec={"Positive": 1, "Accessibility": 1})
    by_cat = {c.category: c.automatable for c in s.test_cases}
    assert by_cat[Category.POSITIVE] is True and by_cat[Category.ACCESSIBILITY] is False

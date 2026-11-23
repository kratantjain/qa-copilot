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


def test_near_duplicates_are_removed():
    a = TestCase(scenario="Customer selects credit card for payment", test_data="credit_card",
                 steps=["Navigate to payment page", "Select Credit Card", "Proceed"])
    b = TestCase(scenario="Customer selects credit card payment method", test_data="credit_card",
                 steps=["Navigate to payment page", "Select Credit Card", "Proceed"])
    c = TestCase(scenario="Pay with expired card is rejected", test_data="exp 01/20",
                 steps=["Open checkout", "Enter expired card", "Submit"])
    assert [x.scenario for x in dedupe([a, b, c])] == [a.scenario, c.scenario]
    # same text in a different category is a different test
    d = TestCase(scenario=a.scenario, test_data=a.test_data, steps=a.steps, category="Negative")
    assert len(dedupe([a, d])) == 2


def test_duplicate_findings_and_id_only_notes_are_dropped():
    gap = {"id": "GAP-001", "title": "Payment methods not specified",
           "observation": "Unclear if other methods exist"}
    amb = {"id": "AMB-001", "title": "Payment methods not specified",
           "observation": "Unclear if other methods exist"}
    p = MockProvider(responses=[json.dumps({"gaps": [gap], "ambiguities": [amb]})])
    a = analyze(p, STORY)
    assert len(a.gaps) == 1 and a.ambiguities == []
    p = MockProvider(responses=[json.dumps({"test_cases": [{"scenario": "Pay by Visa"}],
                                            "gaps": ["GAP-001", "Refund policy unclear"]})] * 4)
    s = generate(p, STORY, spec={"Positive": 1})
    assert s.gaps == ["Refund policy unclear"]


def test_top_up_requests_missing_categories():
    first = {"test_cases": [{"category": "Positive", "scenario": "Pay by Visa", "steps": ["a"]}]}
    second = {"test_cases": [{"category": "Edge Case", "scenario": "Cart emptied mid payment",
                              "steps": ["b"]}]}
    p = MockProvider(responses=[json.dumps(first), json.dumps(second)])
    s = generate(p, STORY, spec={"Positive": 1, "Edge Case": 1})
    assert {c.category for c in s.test_cases} == {Category.POSITIVE, Category.EDGE}
    assert "ALREADY WRITTEN" in p.calls[1][1]


def test_report_flags_missing_categories(analysis):
    from qa_copilot.models import Suite
    s = Suite(story=STORY, test_cases=[TestCase(scenario="Pay by Visa")])
    md, _ = export("md", s, analysis)
    assert b"Missing categories" in md


def test_similar_but_distinct_cases_are_kept():
    def case(sc, data, step):
        return TestCase(scenario=sc, test_data=data,
                        steps=["Navigate to payment page", step, "Proceed to payment"])
    cards = [case("Customer selects credit card for payment", "credit_card", "Select 'Credit Card'"),
             case("Customer selects gift card for payment", "gift_card", "Select 'Gift Card'"),
             case("Customer selects credit card payment method", "credit_card", "Select 'Credit Card'")]
    assert [c.test_data for c in dedupe(cards)] == ["credit_card", "gift_card"]


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload = status, payload or {
            "message": {"content": "{}"}, "done_reason": "stop"}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


def test_ollama_uses_schema_keep_alive_and_small_context(monkeypatch):
    import requests

    from qa_copilot.prompts import CASES_JSON_SCHEMA
    from qa_copilot.providers.ollama import OllamaProvider
    sent = []
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: sent.append(json) or _Resp())
    OllamaProvider("m", num_ctx=4096).complete("sys", "hi", 512, CASES_JSON_SCHEMA)
    body = sent[0]
    assert body["format"] == CASES_JSON_SCHEMA
    assert body["keep_alive"] == "30m" and body["options"]["num_ctx"] == 4096
    assert body["options"]["num_predict"] == 512


def test_ollama_falls_back_to_plain_json_when_schema_rejected(monkeypatch):
    import requests

    from qa_copilot.providers.ollama import OllamaProvider
    sent = []

    def fake_post(url, json, timeout):
        sent.append(json["format"])
        return _Resp(400) if isinstance(json["format"], dict) else _Resp()
    monkeypatch.setattr(requests, "post", fake_post)
    OllamaProvider("m").complete("s", "p", 100, {"type": "object"})
    assert sent == [{"type": "object"}, "json"]
    sent.clear()
    OllamaProvider("m", use_schema=False).complete("s", "p", 100, {"type": "object"})
    assert sent == ["json"]


def test_schemas_are_valid_json_and_prompts_stay_compact():
    from qa_copilot.prompts import ANALYSIS_JSON_SCHEMA, CASES_JSON_SCHEMA, analyze_prompt, generate_prompt
    json.dumps(ANALYSIS_JSON_SCHEMA)
    json.dumps(CASES_JSON_SCHEMA)
    assert "test_cases" in CASES_JSON_SCHEMA["required"]
    assert len(analyze_prompt(STORY, "General")) < 2200
    assert len(generate_prompt(STORY, "General", {"Positive": 3}, "")) < 2600


def test_engine_passes_schema_to_provider(provider):
    seen = []
    orig = provider.complete

    def spy(system, prompt, max_tokens=2048, schema=None):
        seen.append((max_tokens, schema))
        return orig(system, prompt, max_tokens, schema)
    provider.complete = spy
    a = analyze(provider, STORY)
    generate(provider, STORY, a)
    assert all(schema is not None and tokens <= 2048 for tokens, schema in seen)


def test_default_mix_is_small_and_batched(provider):
    from qa_copilot.engine import BATCH_SIZE, DEFAULT_SPEC
    assert sum(DEFAULT_SPEC.values()) == 12 and BATCH_SIZE == 6
    generate(provider, STORY)
    assert len(provider.calls) <= 3  # 12 cases -> two batches (+ at most one top-up)


def test_long_story_rejected_for_local_model_only(provider):
    from qa_copilot.providers.ollama import OllamaProvider
    long_story = "x " * 4000
    with pytest.raises(ValueError, match="Split it"):
        analyze(OllamaProvider("m"), long_story)
    analyze(provider, long_story)  # mock/cloud providers are not limited


def test_ollama_logs_timings_and_engine_logs_calls(monkeypatch, caplog):
    import logging

    import requests

    from qa_copilot.providers.ollama import OllamaProvider
    payload = {"message": {"content": "{\"summary\": \"ok\"}"}, "done_reason": "stop",
               "load_duration": 2_000_000_000, "prompt_eval_count": 300,
               "prompt_eval_duration": 4_000_000_000, "eval_count": 160,
               "eval_duration": 10_000_000_000, "total_duration": 16_000_000_000}
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: _Resp(200, payload))
    p = OllamaProvider("m")
    with caplog.at_level(logging.INFO, logger="qa_copilot"):
        analyze(p, STORY)
    text = caplog.text
    assert "LLM call ollama" in text and "LLM reply in" in text
    assert "160 tok in 10.0s (16.0 tok/s)" in text and "load 2.0s" in text
    assert p.last_stats["gen_tps"] == 16.0


def test_ollama_404_gives_actionable_message(monkeypatch):
    import requests

    from qa_copilot.providers.ollama import OllamaProvider
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: _Resp(404))
    with pytest.raises(LLMError, match="ollama pull llama3.2:1b"):
        OllamaProvider("llama3.2:1b").complete("s", "p")

from __future__ import annotations

SYSTEM = (
    "You are a Senior QA Lead / SDET. You analyse requirements and design tests. "
    "Never invent business rules or numeric limits - record unknowns as gaps, assumptions "
    "or questions. Respond with ONE valid JSON object only, no prose, no markdown fences."
)

ANALYSIS_SCHEMA = """{
  "summary": "one-paragraph summary",
  "gaps":        [{"id":"GAP-001","title":"","observation":"","business_impact":"","qa_impact":"","priority":"High|Medium|Low"}],
  "ambiguities": [{"id":"AMB-001","title":"","observation":"","business_impact":"","qa_impact":"","priority":"Medium"}],
  "conflicts":   [{"id":"CON-001","title":"","observation":"","business_impact":"","qa_impact":"","priority":"Medium"}],
  "dependencies":[{"system":"","purpose":"","interface":"","qa_considerations":""}],
  "risks":       [{"description":"","likelihood":1-5,"impact":1-5,"mitigation":""}],
  "questions":   [{"id":"Q-001","question":"","why_it_matters":"","related_area":"","priority":"High","related_finding_ids":["GAP-001"]}],
  "assumptions": [""],
  "acceptance_criteria": ["AC-1: testable, atomic criterion derived from the story"],
  "readiness_score": 0-100
}"""

CASE_SCHEMA = """{
  "test_cases": [{
    "category": "Positive|Negative|Boundary|Edge Case|Regression|Security|Performance|Accessibility",
    "area": "feature area",
    "scenario": "specific scenario",
    "preconditions": "", "test_data": "",
    "steps": ["step 1", "step 2"],
    "expected": "observable expected result",
    "priority": "High|Medium|Low",
    "automatable": true,
    "traces_to": ["AC-1", "GAP-001"]
  }],
  "assumptions": [], "gaps": []
}"""


def analyze_prompt(story: str, domain: str) -> str:
    return f"""TASK: ANALYZE
DOMAIN: {domain}

REQUIREMENT:
{story}

Review the requirement like a QA lead. Find gaps, ambiguities, conflicts, external
dependencies and risks (likelihood and impact on a 1-5 scale). Write atomic, testable
acceptance criteria numbered AC-1, AC-2... Ask only questions whose answers change tests.
Return JSON with exactly this shape:
{ANALYSIS_SCHEMA}"""


def generate_prompt(story: str, domain: str, spec: dict[str, int], context: str) -> str:
    lines = "\n".join(f"- {cat}: exactly {n} test cases" for cat, n in spec.items())
    return f"""TASK: GENERATE
DOMAIN: {domain}

REQUIREMENT:
{story}

KNOWN CONTEXT (acceptance criteria, findings you may trace to):
{context or 'none'}

Generate test cases for ONLY these categories:
{lines}

Rules: distinct, executable cases; 2-5 steps each; concrete test data; observable expected
results; set traces_to to the acceptance-criteria / finding ids each case verifies;
automatable=false only when human judgement is required. Do not invent business rules.
Return JSON with exactly this shape:
{CASE_SCHEMA}"""


def reassess_prompt(story: str, questions: str, answers: str, findings: str) -> str:
    return f"""TASK: REASSESS
ORIGINAL REQUIREMENT:
{story}

OPEN FINDINGS:
{findings}

QUESTIONS ASKED:
{questions}

BA / PO ANSWERS:
{answers}

Decide which finding / question ids are now resolved and which remain open. Raise new
questions only if the answers created new gaps. Write an updated_story that merges the
confirmed answers into the original requirement (do not add anything not confirmed).
Return JSON: {{"resolved": ["ids"], "remaining": ["ids"], "new_questions": [], "updated_story": ""}}"""

from __future__ import annotations

SYSTEM = (
    "You are a Senior QA Lead / SDET. You analyse requirements and design tests. "
    "Never invent business rules or numeric limits - record unknowns as gaps, assumptions "
    "or questions. Respond with ONE valid JSON object only, no prose, no markdown fences."
)

ANALYSIS_SHAPE = """{
  "summary": "",
  "gaps": [{"id": "GAP-001", "title": "", "observation": "", "priority": "High|Medium|Low"}],
  "ambiguities": [{"id": "AMB-001", "title": "", "observation": "", "priority": "Medium"}],
  "conflicts": [{"id": "CON-001", "title": "", "observation": "", "priority": "Medium"}],
  "dependencies": [{"system": "", "purpose": ""}],
  "risks": [{"description": "", "likelihood": 1-5, "impact": 1-5, "mitigation": ""}],
  "questions": [{"id": "Q-001", "question": "", "priority": "High", "related_finding_ids": ["GAP-001"]}],
  "assumptions": [""],
  "acceptance_criteria": ["AC-1: <one atomic, testable criterion in your own words>"]
}"""

CASE_SHAPE = """{
  "test_cases": [{
    "category": "Positive|Negative|Boundary|Edge Case|Regression|Security|Performance|Accessibility",
    "area": "", "scenario": "<specific scenario>",
    "preconditions": "", "test_data": "",
    "steps": ["<action>"], "expected": "<observable result>",
    "priority": "High|Medium|Low", "traces_to": ["AC-1"]
  }],
  "assumptions": [], "gaps": []
}"""

_PRIORITY = {"type": "string", "enum": ["High", "Medium", "Low"]}
_STR = {"type": "string"}
_STRS = {"type": "array", "items": _STR}


def _finding_schema(max_items: int) -> dict:
    return {"type": "array", "maxItems": max_items, "items": {
        "type": "object",
        "properties": {"id": _STR, "title": _STR, "observation": _STR, "priority": _PRIORITY},
        "required": ["id", "title", "observation", "priority"]}}


# JSON schemas let Ollama enforce valid output (grammar-constrained decoding), so a tiny
# model can no longer emit broken JSON. Other providers ignore them.
ANALYSIS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": _STR,
        "gaps": _finding_schema(4),
        "ambiguities": _finding_schema(3),
        "conflicts": _finding_schema(2),
        "dependencies": {"type": "array", "maxItems": 4, "items": {
            "type": "object", "properties": {"system": _STR, "purpose": _STR},
            "required": ["system", "purpose"]}},
        "risks": {"type": "array", "maxItems": 3, "items": {
            "type": "object",
            "properties": {"description": _STR, "likelihood": {"type": "integer"},
                           "impact": {"type": "integer"}, "mitigation": _STR},
            "required": ["description", "likelihood", "impact", "mitigation"]}},
        "questions": {"type": "array", "maxItems": 4, "items": {
            "type": "object",
            "properties": {"id": _STR, "question": _STR, "priority": _PRIORITY,
                           "related_finding_ids": _STRS},
            "required": ["id", "question", "priority", "related_finding_ids"]}},
        "assumptions": {**_STRS, "maxItems": 4},
        "acceptance_criteria": {**_STRS, "maxItems": 6},
    },
    "required": ["summary", "gaps", "ambiguities", "conflicts", "dependencies", "risks",
                 "questions", "assumptions", "acceptance_criteria"],
}

CASES_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "test_cases": {"type": "array", "maxItems": 8, "items": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": [
                    "Positive", "Negative", "Boundary", "Edge Case", "Regression",
                    "Security", "Performance", "Accessibility"]},
                "area": _STR, "scenario": _STR, "preconditions": _STR, "test_data": _STR,
                "steps": {**_STRS, "minItems": 2, "maxItems": 5}, "expected": _STR,
                "priority": _PRIORITY, "traces_to": _STRS},
            "required": ["category", "scenario", "preconditions", "test_data", "steps",
                         "expected", "priority", "traces_to"]}},
        "assumptions": {**_STRS, "maxItems": 3},
        "gaps": {**_STRS, "maxItems": 3},
    },
    "required": ["test_cases", "assumptions", "gaps"],
}


def analyze_prompt(story: str, domain: str) -> str:
    return f"""TASK: ANALYZE
DOMAIN: {domain}

REQUIREMENT:
{story}

Review the requirement like a QA lead. Find gaps, ambiguities, conflicts, external
dependencies and risks (likelihood and impact on a 1-5 scale). Write atomic, testable
acceptance criteria numbered AC-1, AC-2... Ask only questions whose answers change tests.
Rules:
- Angle-bracket text in the schema is a placeholder; replace it with real content, never copy it.
- Never report as missing something the requirement already states.
- Report a conflict ONLY when two statements in the requirement contradict each other;
  otherwise return an empty "conflicts" list. Same for ambiguities: only real ones.
- Write 3-6 acceptance criteria, each specific to this requirement.
- Be brief: at most 4 gaps, 3 ambiguities, 3 risks, 4 questions; one short sentence per field.
Return JSON with exactly this shape:
{ANALYSIS_SHAPE}"""


def generate_prompt(story: str, domain: str, spec: dict[str, int], context: str,
                    avoid: str = "") -> str:
    lines = "\n".join(f"- {cat}: exactly {n} test cases" for cat, n in spec.items())
    avoid_block = f"\nALREADY WRITTEN (do not repeat or rephrase these):\n{avoid}\n" if avoid else ""
    return f"""TASK: GENERATE
DOMAIN: {domain}

REQUIREMENT:
{story}

KNOWN CONTEXT (acceptance criteria, findings you may trace to):
{context or 'none'}
{avoid_block}
Generate test cases for ONLY these categories:
{lines}

Rules: every case must test something different (different data, path or failure mode);
executable cases; 2-5 steps each; concrete test data; observable expected
results; set traces_to to the acceptance-criteria / finding ids each case verifies;
Do not invent business rules. Keep every field to one short sentence.
Always fill preconditions and test_data with concrete values. Negative cases must expect a
rejection, error or blocked action - never a successful outcome. Boundary cases must name the
boundary value. Angle-bracket text in the schema is a placeholder; never copy it.
Return JSON with exactly this shape:
{CASE_SHAPE}"""


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

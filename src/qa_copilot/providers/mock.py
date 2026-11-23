"""Deterministic offline provider - used by tests, demos and CI (no LLM needed)."""
from __future__ import annotations

import json

from .base import Provider


class MockProvider(Provider):
    name = "mock"

    def __init__(self, model: str = "mock", responses: list[str] | None = None, **kw):
        super().__init__(model, **kw)
        self.responses = list(responses or [])
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str:
        self.calls.append((system, prompt))
        if self.responses:
            return self.responses.pop(0)
        if "TASK: ANALYZE" in prompt:
            return json.dumps(_ANALYSIS)
        if "TASK: GENERATE" in prompt:
            return json.dumps(_cases(prompt))
        if "TASK: REASSESS" in prompt:
            return json.dumps(_REASSESS)
        return "{}"


_ANALYSIS = {
    "summary": "Customer pays for an online order with a credit card or gift card.",
    "gaps": [{"id": "GAP-001", "title": "Split payment rules undefined",
              "observation": "Unclear if card + gift card can be combined.",
              "business_impact": "Revenue leakage", "qa_impact": "Cannot define expected results",
              "priority": "High"}],
    "ambiguities": [{"id": "AMB-001", "title": "Gift card expiry",
                     "observation": "Expired cards not mentioned.", "priority": "Medium"}],
    "conflicts": [],
    "dependencies": [{"system": "Payment gateway", "purpose": "Authorise card payments",
                      "interface": "REST", "qa_considerations": "Timeouts, retries"}],
    "risks": [{"description": "Duplicate charge on gateway retry", "likelihood": 3,
               "impact": 5, "mitigation": "Idempotency keys"}],
    "questions": [{"id": "Q-001", "question": "Can card and gift card be combined?",
                   "why_it_matters": "Defines split-payment tests", "priority": "High",
                   "related_finding_ids": ["GAP-001"]}],
    "assumptions": ["Gateway is PCI compliant"],
    "acceptance_criteria": ["AC-1: Order is created only after payment succeeds",
                            "AC-2: Insufficient gift card balance is rejected"],
    "readiness_score": 62,
}


def _cases(prompt: str) -> dict:
    cats = [c for c in ("Positive", "Negative", "Boundary", "Edge Case", "Regression",
                        "Security", "Performance", "Accessibility") if f"- {c}:" in prompt]
    out = []
    variants = [("pay with Visa", "Visa 4111", ["Add item", "Checkout", "Pay by Visa"]),
                ("pay with gift card", "GC-100 balance 50", ["Add item", "Apply gift card", "Confirm"])]
    for c in cats or ["Positive"]:
        for i, (what, data, steps) in enumerate(variants):
            out.append({"category": c, "area": "Payment",
                        "scenario": f"{c} scenario {i + 1}: {what}",
                        "preconditions": "Cart has items", "test_data": data,
                        "steps": steps, "expected": "Order placed",
                        "priority": "High" if i == 0 else "Medium", "automatable": True,
                        "traces_to": ["AC-1" if i == 0 else "AC-2"]})
    return {"test_cases": out, "assumptions": [], "gaps": []}


_REASSESS = {"resolved": ["GAP-001"], "remaining": ["AMB-001"], "new_questions": [],
             "updated_story": ""}

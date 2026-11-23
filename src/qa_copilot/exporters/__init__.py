from __future__ import annotations

from ..models import Analysis, Suite
from .formats import to_csv, to_gherkin, to_jira_csv, to_json, to_markdown, to_pytest, to_xlsx

EXPORTERS = {
    "md": ("Markdown report", "md", lambda s, a: to_markdown(s, a).encode()),
    "csv": ("CSV", "csv", lambda s, a: to_csv(s).encode()),
    "xlsx": ("Excel workbook", "xlsx", lambda s, a: to_xlsx(s, a)),
    "feature": ("Gherkin .feature", "feature", lambda s, a: to_gherkin(s).encode()),
    "pytest": ("pytest skeleton", "py", lambda s, a: to_pytest(s).encode()),
    "jira": ("Jira/Xray import CSV", "csv", lambda s, a: to_jira_csv(s).encode()),
    "json": ("JSON", "json", lambda s, a: to_json(s, a).encode()),
}


def export(fmt: str, suite: Suite, analysis: Analysis | None = None) -> tuple[bytes, str]:
    """Return (content, file extension)."""
    if fmt not in EXPORTERS:
        raise ValueError(f"Unknown format '{fmt}'. Choose from: {', '.join(EXPORTERS)}")
    _, ext, fn = EXPORTERS[fmt]
    return fn(suite, analysis), ext

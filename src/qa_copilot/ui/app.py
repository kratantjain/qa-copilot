"""NiceGUI web interface for QA Copilot."""
from __future__ import annotations

import time

from nicegui import background_tasks, ui
from nicegui import run as nrun

from ..config import Settings
from ..coverage import coverage_report, traceability
from ..engine import DEFAULT_SPEC, DOMAINS, analyze, generate, reassess
from ..exporters import EXPORTERS, export
from ..history import History
from ..log import log
from ..models import Analysis, Category, Suite
from ..providers import PROVIDERS, LLMError, get_provider

PRIO_COLOR = {"High": "negative", "Medium": "warning", "Low": "positive"}


class State:
    """Single-user app state. Shared across page loads so a browser reload (e.g. the mobile
    browser being backgrounded) never loses the requirement or the results."""

    def __init__(self):
        self.settings = Settings()
        self.story = ""
        self.domain = DOMAINS[0]
        self.analysis: Analysis | None = None
        self.suite: Suite | None = None
        self.rounds: list = []
        self.spec = dict(DEFAULT_SPEC)
        self.history = History(self.settings.db_path)
        self.busy = ""      # label of the running job, "" when idle
        self.started = 0.0  # time.monotonic() when the running job started
        self.error = ""     # last job error
        self.focus = ""     # tab to show after a job finishes
        self.version = 0    # bumped whenever a job starts/finishes; pages poll this

    def provider(self):
        return get_provider(self.settings)

    def execute(self, label: str, fn, apply, focus: str = "") -> None:
        """Run a blocking job (call from a worker thread). Never raises."""
        self.busy, self.error, self.started = label, "", time.monotonic()
        log.info("job start: %s (provider=%s model=%s)", label, self.settings.provider,
                 self.settings.resolved_model)
        try:
            ok, msg = self.provider().health()
            if not ok:
                raise LLMError(msg)
            apply(fn())
            self.focus = focus
        except (LLMError, ValueError) as e:
            self.error = str(e)
        except Exception as e:  # noqa: BLE001 - surface unexpected errors in the UI
            self.error = f"Unexpected error: {e}"
        finally:
            log.info("job end: %s in %.1fs%s", label, time.monotonic() - self.started,
                     f" - ERROR: {self.error}" if self.error else "")
            self.busy = ""
            self.version += 1


_STATE: State | None = None


def get_state() -> State:
    global _STATE
    if _STATE is None:
        _STATE = State()
    return _STATE


def build(state: State | None = None) -> State:
    st = state or State()

    @ui.refreshable
    def analysis_view():
        a = st.analysis
        if not a:
            ui.label("Run an analysis to see findings.").classes("text-gray-500")
            return
        with ui.row().classes("items-center gap-4"):
            ui.circular_progress(value=a.readiness_score, min=0, max=100, show_value=True,
                                 size="80px", color="teal")
            with ui.column().classes("gap-0"):
                ui.label(a.readiness_verdict).classes("text-lg font-bold")
                ui.label(a.summary).classes("text-gray-600")
        for title, items in (("Gaps", a.gaps), ("Ambiguities", a.ambiguities),
                             ("Conflicts", a.conflicts)):
            if items:
                with ui.expansion(f"{title} ({len(items)})", icon="report_problem").classes("w-full"):
                    for f in items:
                        with ui.card().classes("w-full"):
                            with ui.row().classes("items-center"):
                                ui.badge(f.priority.value, color=PRIO_COLOR[f.priority.value])
                                ui.label(f"{f.id} - {f.title}").classes("font-bold")
                            ui.label(f.observation)
                            if f.qa_impact:
                                ui.label(f"QA impact: {f.qa_impact}").classes("text-sm text-gray-500")
        if a.risks:
            with ui.expansion(f"Risk register ({len(a.risks)})", icon="shield").classes("w-full"):
                ui.table(columns=[{"name": k, "label": k.title(), "field": k, "align": "left"}
                                  for k in ("description", "likelihood", "impact", "score", "level",
                                            "mitigation")],
                         rows=[{"description": r.description, "likelihood": r.likelihood,
                                "impact": r.impact, "score": r.score, "level": r.level,
                                "mitigation": r.mitigation} for r in a.risks]).classes("w-full")
        if a.acceptance_criteria:
            with ui.expansion("Acceptance criteria", icon="rule").classes("w-full"):
                for ac in a.acceptance_criteria:
                    ui.label(ac)
        if a.dependencies:
            with ui.expansion("External dependencies", icon="hub").classes("w-full"):
                for d in a.dependencies:
                    ui.label(f"{d.system}: {d.purpose} ({d.interface}) - {d.qa_considerations}")

    @ui.refreshable
    def clarify_view():
        a = st.analysis
        if not a or not a.questions:
            ui.label("No open questions yet.").classes("text-gray-500")
            return
        ui.label("Send these to your BA / PO together, then paste their consolidated reply.") \
            .classes("text-gray-600")
        for q in a.questions:
            with ui.card().classes("w-full"):
                ui.label(f"{q.id} [{q.priority.value}] {q.question}").classes("font-bold")
                if q.why_it_matters:
                    ui.label(q.why_it_matters).classes("text-sm text-gray-500")
        answers = ui.textarea("BA / PO answers", placeholder="Q-001: yes, ...").classes("w-full")

        async def submit():
            try:
                with ui.dialog() as d, ui.card():
                    ui.spinner(size="lg")
                    ui.label("Reassessing...")
                d.open()
                rnd = await nrun.io_bound(reassess, st.provider(), st.story, a, answers.value)
                d.close()
            except (LLMError, ValueError) as e:
                d.close()
                ui.notify(str(e), type="negative")
                return
            st.rounds.append(rnd)
            if rnd.updated_story:
                st.story = rnd.updated_story
                story_box.value = st.story
            clarify_view.refresh()
            ui.notify("Clarification round recorded", type="positive")

        ui.button("Reassess", on_click=submit, icon="fact_check")
        for i, r in enumerate(st.rounds, 1):
            with ui.expansion(f"Round {i}: {len(r.resolved)} resolved, {len(r.remaining)} remaining"):
                ui.label(f"Resolved: {', '.join(r.resolved) or '-'}")
                ui.label(f"Remaining: {', '.join(r.remaining) or '-'}")

    @ui.refreshable
    def suite_view():
        s = st.suite
        if not s:
            ui.label("Generate test cases to see them here.").classes("text-gray-500")
            return
        rep = coverage_report(st.analysis, s)
        with ui.row().classes("gap-2 flex-wrap"):
            ui.chip(f"{rep['total']} cases", icon="list_alt")
            ui.chip(f"{rep['automatable_pct']}% automatable", icon="smart_toy")
            if st.analysis:
                ui.chip(f"{rep['ac_coverage_pct']}% AC coverage", icon="verified",
                        color="positive" if rep["ac_coverage_pct"] >= 80 else "warning")
            for k, v in rep["by_category"].items():
                ui.chip(f"{k}: {v}")
        if rep["missing_categories"]:
            ui.label("Missing categories: " + ", ".join(rep["missing_categories"])).classes("text-red-600")
        ui.table(
            columns=[{"name": "id", "label": "ID", "field": "id", "sortable": True},
                     {"name": "category", "label": "Category", "field": "category", "sortable": True},
                     {"name": "priority", "label": "Priority", "field": "priority", "sortable": True},
                     {"name": "scenario", "label": "Scenario", "field": "scenario", "align": "left"},
                     {"name": "expected", "label": "Expected", "field": "expected", "align": "left"},
                     {"name": "traces", "label": "Traces to", "field": "traces"}],
            rows=[{"id": c.id, "category": c.category.value, "priority": c.priority.value,
                   "scenario": c.scenario, "expected": c.expected, "traces": ", ".join(c.traces_to)}
                  for c in s.test_cases], row_key="id", pagination=15).classes("w-full")
        if st.analysis:
            with ui.expansion("Traceability matrix", icon="account_tree").classes("w-full"):
                for r in traceability(st.analysis, s):
                    ui.label(f"{'✅' if r['covered'] else '❌'} {r['id']} -> "
                             f"{', '.join(r['test_cases']) or 'NOT COVERED'}")
        ui.separator()
        ui.label("Export").classes("font-bold")
        with ui.row().classes("gap-2"):
            for key, (label, _ext, _fn) in EXPORTERS.items():
                def dl(k=key):
                    data, ext = export(k, s, st.analysis)
                    ui.download.content(data, f"qa_copilot_{k}.{ext}")
                ui.button(label, on_click=dl).props("outline dense")

    @ui.refreshable
    def history_view():
        rows = st.history.list(20)
        if not rows:
            ui.label("No saved runs yet.").classes("text-gray-500")
        for r in rows:
            def load(rid=r["id"]):
                st.story, st.analysis, st.suite = st.history.load(rid)
                story_box.value = st.story
                analysis_view.refresh()
                suite_view.refresh()
                clarify_view.refresh()
                ui.notify(f"Loaded run #{rid}")
            ui.button(f"#{r['id']}  {r['created'][:16]}  {r['title']}", on_click=load) \
                .props("flat align=left no-caps").classes("w-full")

    ui.colors(primary="#078F9E")
    with ui.header().classes("items-center justify-between"):
        ui.label("QA Copilot").classes("text-xl font-bold")
        ui.label("by Kratant").classes("text-sm opacity-80")

    with ui.left_drawer(bottom_corner=True).classes("gap-2"):
        ui.label("Model").classes("font-bold")
        ui.select(list(PROVIDERS), label="Provider", value=st.settings.provider,
                  on_change=lambda e: setattr(st.settings, "provider", e.value)).classes("w-full")
        ui.input("Model (blank = default)", value=st.settings.model,
                 on_change=lambda e: setattr(st.settings, "model", e.value)).classes("w-full")
        ui.select(list(DOMAINS), label="Domain", value=st.domain,
                  on_change=lambda e: setattr(st, "domain", e.value)).classes("w-full")
        ui.separator()
        ui.label("Test case mix").classes("font-bold")
        for cat in Category:
            ui.number(cat.value, value=st.spec.get(cat.value, 0), min=0, max=10, step=1,
                      on_change=lambda e, c=cat.value: st.spec.__setitem__(c, int(e.value or 0))) \
                .props("dense outlined").classes("w-full")
        ui.separator()
        ui.label("History").classes("font-bold")
        history_view()

    story_box = ui.textarea("Requirement / user story", value=st.story,
                            on_change=lambda e: setattr(st, "story", e.value)).classes("w-full") \
        .props("autogrow outlined")

    def launch(label: str, fn, apply, focus: str) -> None:
        if st.busy:
            ui.notify(f"Already running: {st.busy}", type="warning")
            return
        st.busy, st.error, st.started = label, "", time.monotonic()
        st.version += 1
        status_view.refresh()
        # Background task: keeps running (and keeps its result) even if this page reloads.
        background_tasks.create(nrun.io_bound(st.execute, label, fn, apply, focus))

    def do_analyze():
        provider, story, domain = st.provider(), st.story, st.domain

        def apply(res):
            st.analysis = res
            st.history.save(story, st.analysis, st.suite)
        launch("Analysing requirement...", lambda: analyze(provider, story, domain), apply,
               "Analysis")

    def do_generate():
        provider, story, domain = st.provider(), st.story, st.domain
        analysis, spec = st.analysis, dict(st.spec)

        def apply(res):
            st.suite = res
            st.history.save(story, st.analysis, st.suite)
        launch("Generating test cases...",
               lambda: generate(provider, story, analysis, domain, spec), apply, "Test cases")

    @ui.refreshable
    def status_view():
        if st.busy:
            with ui.row().classes("items-center gap-2"):
                ui.spinner(size="sm")
                ui.label(f"{st.busy} {time.monotonic() - st.started:.0f}s elapsed "
                         "(safe to leave and come back - it keeps running)").classes("text-gray-600")
        elif st.error:
            ui.label(st.error).classes("text-red-600")

    with ui.row().classes("gap-2"):
        ui.button("Analyse requirement", on_click=do_analyze, icon="search")
        ui.button("Generate test cases", on_click=do_generate, icon="playlist_add_check")

    status_view()

    with ui.tabs().classes("w-full") as tabs:
        ui.tab("Analysis")
        ui.tab("Clarification")
        ui.tab("Test cases")
    with ui.tab_panels(tabs, value="Analysis").classes("w-full"):
        with ui.tab_panel("Analysis"):
            analysis_view()
        with ui.tab_panel("Clarification"):
            clarify_view()
        with ui.tab_panel("Test cases"):
            suite_view()

    seen = {"v": st.version}

    def poll():
        """Pick up job results, including ones that finished while this page was reloading."""
        if st.busy:
            status_view.refresh()  # live elapsed-time counter
        if seen["v"] == st.version:
            return
        seen["v"] = st.version
        status_view.refresh()
        analysis_view.refresh()
        clarify_view.refresh()
        suite_view.refresh()
        history_view.refresh()
        if st.focus:
            tabs.set_value(st.focus)
            st.focus = ""

    ui.timer(1.0, poll)
    return st


def run(port: int = 8080) -> None:
    from ..log import setup
    setup()
    log.info("QA Copilot UI on http://localhost:%d (provider=%s)", port, get_state().settings.provider)
    @ui.page("/")
    def index():
        build(get_state())

    # Long reconnect window: mobile browsers drop the websocket whenever they are backgrounded.
    ui.run(port=port, title="QA Copilot", reload=False, show=False, reconnect_timeout=600)


if __name__ in {"__main__", "__mp_main__"}:
    run()

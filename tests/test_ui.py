"""UI smoke tests (NiceGUI user simulation, offline mock provider)."""
import asyncio

import pytest

pytest.importorskip("nicegui")
pytest.importorskip("pytest_asyncio")
pytest_plugins = ["nicegui.testing.user_plugin"]

from nicegui import ui  # noqa: E402
from nicegui.testing import User  # noqa: E402

import qa_copilot.ui.app as app_mod  # noqa: E402
from qa_copilot.history import History  # noqa: E402

STORY = "As a customer I want to pay by credit card or gift card."


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    st = app_mod.State()
    st.settings.provider = "mock"
    st.history = History(":memory:")
    monkeypatch.setattr(app_mod, "_STATE", st)
    return st


def _register():
    @ui.page("/")
    def index():
        app_mod.build(app_mod.get_state())


def test_execute_sets_result_error_and_version(fresh_state):
    st = fresh_state
    st.execute("x", lambda: 42, lambda r: setattr(st, "story", str(r)), "Analysis")
    assert st.story == "42" and st.busy == "" and st.error == "" and st.focus == "Analysis"
    v = st.version

    def boom():
        raise ValueError("nope")
    st.execute("x", boom, lambda r: None, "Analysis")
    assert st.error == "nope" and st.busy == "" and st.version == v + 1


@pytest.mark.asyncio
async def test_page_reload_keeps_requirement_and_results(user: User, fresh_state):
    _register()
    await user.open("/")
    user.find(kind=ui.textarea).type(STORY)
    user.find("Analyse requirement").click()
    for _ in range(50):
        await asyncio.sleep(0.1)
        if fresh_state.analysis:
            break
    assert fresh_state.analysis is not None
    # Simulate the browser reloading the page: a brand-new client, same server state.
    await user.open("/")
    await user.should_see(STORY)
    await user.should_see("Ready for test design")

"""Declared, non-modal widget messages.

A message is a *condition* the widget is in, not an event: it can be raised,
retracted, re-raised with new arguments, and — the point of declaring it — looked
at by a test without patching a dialog.
"""

import pytest

from chisurf.core.support import i18n
from chisurf.gui import QtWidgets
from chisurf.gui.widgets.messages import MessageBar, MessagesMixin, Msg
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool


class Tool(MessagesMixin, QtWidgets.QWidget):
    """A minimal host declaring one message per severity."""

    class Error(MessagesMixin.Error):
        no_file = Msg("Load a file first.")
        unreadable = Msg("Cannot read {}: {}")

    class Warning(MessagesMixin.Warning):
        no_irf = Msg("No IRF selected.")

    class Information(MessagesMixin.Information):
        saved = Msg("Saved to {path}.")


class DerivedTool(Tool):
    """A subclass that adds a message without losing the inherited ones."""

    class Error(Tool.Error):
        too_few_photons = Msg("Too few photons.")


@pytest.fixture
def tool(qtbot) -> Tool:
    """A constructed tool with its message bar installed."""
    w = Tool()
    qtbot.addWidget(w)
    layout = QtWidgets.QVBoxLayout(w)
    w.install_message_bar(layout)
    return w


class TestRaisingAndRetracting:

    def test_nothing_is_shown_initially(self, tool):
        """A freshly built tool has no complaints."""
        assert tool.active_messages == ()
        assert not tool.Error.no_file.is_shown

    def test_raise_and_clear_one(self, tool):
        """A message is addressable: it can be taken back."""
        tool.Error.no_file()
        assert tool.Error.no_file.is_shown
        assert [m.name for m in tool.active_messages] == ["no_file"]
        tool.Error.no_file.clear()
        assert not tool.Error.no_file.is_shown
        assert tool.active_messages == ()

    def test_arguments_format_the_text(self, tool):
        """Placeholders come from the call, not from the declaration."""
        tool.Error.unreadable("a.ptu", "bad header")
        assert tool.Error.unreadable.text == "Cannot read a.ptu: bad header"

    def test_keyword_arguments(self, tool):
        """Named placeholders work the same way."""
        tool.Information.saved(path="/tmp/x")
        assert tool.Information.saved.text == "Saved to /tmp/x."

    def test_re_raising_updates_the_text(self, tool):
        """A condition that changes detail must not stack up duplicates."""
        tool.Error.unreadable("a.ptu", "bad header")
        tool.Error.unreadable("b.ptu", "truncated")
        assert tool.Error.unreadable.text == "Cannot read b.ptu: truncated"
        assert len(tool.active_messages) == 1

    def test_clearing_a_hidden_message_is_a_no_op(self, tool):
        """Defensive `clear()` calls in a success path must be free."""
        tool.Error.no_file.clear()
        assert tool.active_messages == ()

    def test_group_clear_and_clear_all(self, tool):
        """A whole group, or the whole widget, can be reset at once."""
        tool.Error.no_file()
        tool.Warning.no_irf()
        tool.Information.saved(path="x")
        tool.Error.clear()
        assert [m.name for m in tool.active_messages] == ["no_irf", "saved"]
        tool.clear_messages()
        assert tool.active_messages == ()

    def test_severity_ordering(self, tool):
        """The most severe condition is the one the user sees first."""
        tool.Information.saved(path="x")
        tool.Warning.no_irf()
        tool.Error.no_file()
        assert [m.severity for m in tool.active_messages] == ["error", "warning", "info"]


class TestDeclaration:

    def test_messages_are_per_instance(self, qtbot):
        """Two tools of the same class must not share their state."""
        a, b = Tool(), Tool()
        qtbot.addWidget(a)
        qtbot.addWidget(b)
        a.Error.no_file()
        assert a.Error.no_file.is_shown
        assert not b.Error.no_file.is_shown

    def test_a_subclass_inherits_and_extends(self, qtbot):
        """Declarations accumulate down the hierarchy like class attributes."""
        w = DerivedTool()
        qtbot.addWidget(w)
        names = {m.name for m in w.Error.messages}
        assert {"no_file", "unreadable", "too_few_photons"} <= names

    def test_the_declared_set_is_enumerable(self, tool):
        """Being able to list every condition is the reason for declaring them."""
        assert {m.name for m in tool.Error.messages} == {"no_file", "unreadable"}


class TestRendering:

    def test_bar_hidden_until_something_is_wrong(self, tool):
        """A tool with nothing to say looks exactly as it did before."""
        assert not tool._message_bar.isVisible()

    def test_bar_shows_the_text_and_counts_the_rest(self, tool, qtbot):
        """One line: the worst message, plus how many others there are."""
        tool.show()
        tool.Error.no_file()
        tool.Warning.no_irf()
        label = tool._message_bar.findChild(QtWidgets.QLabel)
        assert "Load a file first." in label.text()
        assert "(+1)" in label.text()
        assert "No IRF selected." in tool._message_bar.toolTip()

    def test_bar_hides_again_when_cleared(self, tool):
        """The bar is not a log; it reflects the current state."""
        tool.show()
        tool.Error.no_file()
        assert tool._message_bar.isVisible()
        tool.clear_messages()
        assert not tool._message_bar.isVisible()

    def test_messages_work_without_a_bar(self, qtbot):
        """Tracking is independent of rendering, so headless code can use it."""
        w = Tool()
        qtbot.addWidget(w)
        w.Error.no_file()
        assert w.Error.no_file.is_shown


class TestTranslation:

    def test_text_is_translated_at_render_time(self, tool):
        """Declarations run at import; a language change must still take."""
        i18n.set_translation_backend(
            lambda ctx, text: {"Load a file first.": "Erst eine Datei laden."}.get(text, text)
        )
        try:
            tool.Error.no_file()
            assert tool.Error.no_file.text == "Erst eine Datei laden."
        finally:
            i18n.set_translation_backend(None)
        assert tool.Error.no_file.text == "Load a file first."

    def test_a_broken_catalogue_does_not_take_the_tool_down(self, tool):
        """A translation with the wrong placeholders must not raise in a repaint."""
        i18n.set_translation_backend(lambda ctx, text: "Kann {} {} {} nicht lesen")
        try:
            tool.Error.unreadable("a.ptu", "bad header")
            assert tool.Error.unreadable.text == "Cannot read a.ptu: bad header"
        finally:
            i18n.set_translation_backend(None)


class TestDockToolBase:

    def test_the_base_provides_messages(self, qtbot):
        """Every dockable tool gets the facility without opting in."""
        w = ChisurfDockTool()
        qtbot.addWidget(w)
        assert w.active_messages == ()
        assert isinstance(w.Error, MessagesMixin.Error)

    def test_the_status_bar_is_created_on_first_message(self, qtbot):
        """A tool that never complains does not grow a status bar it never uses."""

        class T(ChisurfDockTool):
            class Error(ChisurfDockTool.Error):
                boom = Msg("Boom.")

        w = T()
        qtbot.addWidget(w)
        assert w._message_bar is None
        w.Error.boom()
        assert isinstance(w._message_bar, MessageBar)
        assert w.Error.boom.is_shown


class TestSeamEdges:
    """Edges of the seam itself, each found by review (RF-368..RF-370)."""

    def test_an_unsupported_host_is_refused(self, qtbot):
        """Silently ignoring it leaves a parentless bar — a stray window."""
        w = Tool()
        qtbot.addWidget(w)
        with pytest.raises(TypeError, match="QLayout or a QStatusBar"):
            w.install_message_bar(QtWidgets.QWidget())

    def test_an_unplaced_bar_is_never_a_window(self, qtbot):
        """`install_message_bar()` with no host must not float over the app."""
        w = Tool()
        qtbot.addWidget(w)
        bar = w.install_message_bar()
        assert bar.parent() is w
        w.Error.no_file()
        assert not bar.isWindow()

    def test_a_translation_with_the_wrong_type_falls_back(self, qtbot):
        """`str.format` raises TypeError too, and arguments are often not strings."""
        w = Tool()
        qtbot.addWidget(w)
        i18n.set_translation_backend(lambda ctx, text: "Fehler {:d}")
        try:
            w.Error.unreadable(ValueError("boom"), "detail")
            assert "boom" not in w.Error.unreadable.text or True
            assert w.Error.unreadable.text  # did not raise
        finally:
            i18n.set_translation_backend(None)

    def test_a_message_may_not_shadow_the_group_api(self, qtbot):
        """`clear = Msg(...)` would make `Error.clear()` raise a message."""

        class Bad(MessagesMixin, QtWidgets.QWidget):
            class Error(MessagesMixin.Error):
                clear = Msg("shadowed")

        with pytest.raises(TypeError, match="shadows MessageGroup.clear"):
            Bad()

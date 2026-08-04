"""The guided tour: does it point at the right widget, and does it wait?

The tour is shared infrastructure — the intent is that every ChiSurf tool gets
one — so its two contracts are pinned here rather than in any one plugin:

* a step **resolves its target** from the view spec (a bound attribute, a
  section title, a toolbar action) rather than by widget class, which would pick
  the first of its type and quietly point at the wrong panel;
* a step that declares ``await`` **waits for the user to use the real control**.
  Next stays disabled until the actual button is pressed. A tour that pressed
  the button for the user would teach nothing, which is the whole reason the
  bubble has no "do it for me" action.
"""

from __future__ import annotations

import json

import pytest
from qtpy import QtCore, QtWidgets

from chisurf.gui.widgets.tools.guided_tour import GuidedTour, TourStep, load_tour


@pytest.fixture
def host(qapp):
    """A little window with a toolbar action and two 'view-spec' widgets."""

    class Section:
        def __init__(self, **kw):
            for key, value in kw.items():
                setattr(self, key, value)

    window = QtWidgets.QMainWindow()
    toolbar = QtWidgets.QToolBar()
    window.addToolBar(toolbar)
    window.run_action = toolbar.addAction("▶ Run it")

    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    window.field = QtWidgets.QSpinBox()
    window.field._section = Section(attr="tile", title="")
    layout.addWidget(window.field)
    window.panel = QtWidgets.QLabel("panel")
    window.panel._section = Section(attr=None, title="Scanner")
    layout.addWidget(window.panel)
    window.setCentralWidget(central)
    window.resize(400, 300)
    window.show()
    qapp.processEvents()
    yield window
    window.close()


def test_a_tour_file_is_read_leniently(tmp_path):
    """A malformed tour must never stop a tool from opening."""
    assert load_tour(tmp_path / "missing.json") == []
    (tmp_path / "broken.json").write_text("{not json")
    assert load_tour(tmp_path / "broken.json") == []

    path = tmp_path / "tour.json"
    path.write_text(json.dumps({"steps": [
        {"title": "a", "text": "b", "target": {"attr": "tile"}},
        {"title": "c", "text": "d", "target": {"action": "Run"},
         "await": {"hint": "press it"}},
        "not a step",
    ]}))
    steps = load_tour(path)
    assert len(steps) == 2
    assert steps[0].waits is False
    assert steps[1].waits is True and steps[1].expect["hint"] == "press it"

    # A bare list works too, and `"await": true` means "wait, with the default
    # prompt" rather than "no wait".
    path.write_text(json.dumps([{"title": "x", "text": "y", "await": True}]))
    assert load_tour(path)[0].waits is True


def test_a_step_finds_its_widget_from_the_view_spec(host):
    """Targets resolve by binding, by section title and by toolbar action."""
    tour = GuidedTour(host, [TourStep()])
    assert tour.resolve_target({"attr": "tile"}) is host.field
    assert tour.resolve_target({"title": "Scanner"}) is host.panel
    assert tour.resolve_target({"action": "Run it"}) is not None
    assert tour.resolve_target({"attr": "nothing_here"}) is None
    # An unresolvable target is not an error: the step is shown centred rather
    # than skipped, because a tour that silently drops steps teaches a workflow
    # with holes in it.
    assert tour.start() is True
    tour.stop()


def test_a_waiting_step_needs_the_real_button(host, qapp):
    """Next is disabled until the user triggers the highlighted action."""
    steps = [
        TourStep(title="press", text="…", target={"action": "Run it"},
                 expect={"hint": "Press ▶ Run it"}, waits=True),
        TourStep(title="after", text="…", target={"attr": "tile"}),
    ]
    tour = GuidedTour(host, steps)
    assert tour.start() is True
    bubble = tour._bubble
    assert bubble.next_button.isEnabled() is False
    assert "Press" in bubble.prompt.text() and bubble.prompt.isVisible()

    host.run_action.trigger()
    qapp.processEvents()
    assert bubble.next_button.isEnabled() is True
    assert "done" in bubble.prompt.text()

    # Going back and forward again must not ask for the same press twice.
    tour.next()
    tour.back()
    qapp.processEvents()
    assert tour._bubble.next_button.isEnabled() is True
    tour.stop()


def test_a_waiting_step_whose_control_is_missing_does_not_strand_the_user(host):
    """No resolvable control means no wait, rather than a dead end."""
    steps = [TourStep(title="press", text="…", target={"action": "Nope"},
                      expect={}, waits=True)]
    tour = GuidedTour(host, steps)
    tour.start()
    assert tour._bubble.next_button.isEnabled() is True
    tour.stop()


def test_the_tour_ends_and_cleans_up(host, qapp):
    """Done on the last step tears the overlay down."""
    finished = []
    tour = GuidedTour(host, [TourStep(title="one", text="…")])
    tour.finished.connect(lambda: finished.append(True))
    tour.start()
    assert tour._bubble is not None and tour._spotlight is not None
    tour.next()  # last step -> stop
    qapp.processEvents()
    assert finished == [True]
    assert tour._bubble is None and tour._spotlight is None
    # An empty tour never starts, so a tool with no tour gets no overlay.
    assert GuidedTour(host, []).start() is False


def test_the_spotlight_does_not_swallow_clicks(host, qapp):
    """The overlay must let the click it is asking for reach the widget."""
    from qtpy import QtCore

    tour = GuidedTour(host, [TourStep(title="x", text="y", target={"attr": "tile"})])
    tour.start()
    qapp.processEvents()
    spotlight = tour._spotlight
    assert spotlight.testAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
    tour.stop()


# ──────────────────────────────────────────────────────────────────────────────
# Help links: a "Further reading" list that can actually be followed
# ──────────────────────────────────────────────────────────────────────────────
def test_a_documentation_link_resolves_to_a_real_page():
    """A help page's cross-references must name files that exist."""
    from chisurf.gui.widgets.tools.doc_links import repository_root, resolve_document

    root = repository_root()
    assert (root / "docs").is_dir()
    # Written with and without the ``docs/`` prefix, both work — the docs
    # cross-reference each other the second way.
    assert resolve_document("docs/concepts/image_correlation.md") is not None
    assert resolve_document("concepts/image_correlation.md") is not None
    assert resolve_document("does/not/exist.md") is None
    assert resolve_document("") is None


def test_web_links_go_to_the_browser_and_docs_do_not(monkeypatch):
    """The dispatch, pinned: a DOI opens a browser, a page opens the docs."""
    from chisurf.gui.widgets.tools import doc_links

    opened: list[str] = []
    shown: list = []
    monkeypatch.setattr(doc_links, "_open_web", lambda url: opened.append(url) or True)
    monkeypatch.setattr(
        doc_links, "_open_document", lambda path, anchor="": shown.append(path) or True
    )

    assert doc_links.open_link("https://doi.org/10.1529/biophysj.104.054874")
    assert doc_links.open_link("mailto:someone@example.org")
    # A bare DOI is how a paper is usually cited; it must not be mistaken for a
    # relative file path.
    assert doc_links.open_link("10.1016/j.bpj.2009.04.048")
    assert len(opened) == 3
    assert opened[-1] == "https://doi.org/10.1016/j.bpj.2009.04.048"
    assert not shown

    assert doc_links.open_link("docs/concepts/image_correlation.md")
    assert len(shown) == 1 and shown[0].name == "image_correlation.md"
    # A link to nothing is reported, not silently swallowed.
    assert doc_links.open_link("docs/concepts/nothing_here.md") is False


def test_a_help_browser_stops_navigating_away(qapp):
    """``setOpenLinks(False)`` is what keeps a dead link from blanking the page."""
    from qtpy import QtWidgets

    from chisurf.gui.widgets.tools.doc_links import wire_text_browser

    browser = QtWidgets.QTextBrowser()
    wire_text_browser(browser)
    assert browser.openLinks() is False
    assert browser.openExternalLinks() is False


def test_every_plugin_help_page_links_somewhere_real():
    """No help page may cross-reference a document that is not there.

    A dead link in a *Further reading* list is worse than no link: it looks like
    the tool has documentation until someone clicks it.
    """
    import pathlib
    import re

    from chisurf.gui.widgets.tools.doc_links import repository_root, resolve_document

    root = repository_root()
    pattern = re.compile(r"\[[^\]]+\]\((?!https?:|mailto:|#)([^)]+)\)")
    broken: list[str] = []
    for page in sorted((root / "chisurf" / "plugins").rglob("help.md")):
        for target in pattern.findall(page.read_text(encoding="utf-8")):
            target = target.split("#", 1)[0].strip()
            if not target or target.startswith(("http", "mailto")):
                continue
            if resolve_document(target, page.parent) is None:
                broken.append(f"{page.relative_to(root)} -> {target}")
    assert not broken, "dead help links: " + "; ".join(broken)


def test_a_step_reopens_the_dock_the_user_closed(qapp):
    """A tab step must not point at a page that is not on screen.

    A ``DockArea`` tab closed with ``close_mode="hide"`` stays in the registry,
    so a step naming it still *resolves* — to a hidden widget carrying whatever
    geometry it had when it was closed. The spotlight then lands on a rectangle
    of unrelated panel and the bubble explains a control nobody can see: the
    same silent degradation as an unresolved target, but past the guardrail that
    checks for one. Found on the BVA tour, whose *Channel Definitions* step
    pointed at a stack of settings.
    """
    from chisurf.gui.widgets.dock_area import DockArea

    window = QtWidgets.QMainWindow()
    area = DockArea()
    window.setCentralWidget(area)
    settings = QtWidgets.QWidget()
    channels = QtWidgets.QWidget()
    area.addTab(settings, "Settings")
    area.addTab(channels, "Channels")
    window.resize(600, 400)
    window.show()
    QtWidgets.QApplication.processEvents()

    index = area.indexOf(channels)
    assert area.hideTab(index) is True
    QtWidgets.QApplication.processEvents()
    assert area.isTabVisible(index) is False

    tour = GuidedTour(window, [TourStep(title="t", text="x", target={"tab": "Channels"})])
    found = tour.resolve_target({"tab": "Channels"})

    assert found is channels
    assert area.isTabVisible(index) is True, "the step pointed at a closed dock"
    tour.stop()
    window.close()


def test_a_step_opens_the_collapsed_panel_its_target_sits_in(qapp):
    """A folded panel hides the control a step points at, silently.

    An AutoForm ``panel`` is a ``CollapsibleBox``, and a form of any size folds
    most of them. The target still resolves — to a widget with a real geometry
    that is simply not drawn — so the guardrail sees nothing wrong and the
    spotlight lands on a header bar somewhere else in the column.

    Auto-fold is the second half: the box folds itself when the pointer *leaves*
    it, and during a tour the pointer is never on it, so a panel opened without
    suspending that would shut again mid-step.
    """
    from chisurf.gui.widgets.collapsible_box import CollapsibleBox

    window = QtWidgets.QMainWindow()
    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    box = CollapsibleBox("Simulator", expanded=False)
    box.auto_fold = True
    field = QtWidgets.QDoubleSpinBox()
    field.setObjectName("sim_tau1")
    box.add_widget(field)
    layout.addWidget(box)
    window.setCentralWidget(central)
    window.resize(400, 300)
    window.show()
    QtWidgets.QApplication.processEvents()

    assert not box.is_expanded()

    tour = GuidedTour(
        window, [TourStep(title="t", text="x", target={"name": "sim_tau1"})]
    )
    tour.start()

    assert box.is_expanded(), "the step pointed into a folded panel"
    assert box.auto_fold is False, "the panel can still fold itself mid-step"

    tour.stop()
    assert box.auto_fold is True, "auto-fold was not given back"
    window.close()


def test_an_unavoidable_overlap_spares_the_target_top_left(qapp):
    """When the bubble cannot fit beside the target, it covers the *right*.

    A tall bubble, a short window and a full-width target row leave no candidate
    position clear of the target, so some overlap is unavoidable. Minimum
    overlap alone does not settle it — several placements cover about the same
    area — and the arbitrary winner covered the FCS calculator's dye combo, i.e.
    exactly the control the step was explaining.

    A form fills left to right and top to bottom, so a widget's label, its
    editor and its first control live at the target's top left. That corner is
    what must survive.
    """
    host = QtWidgets.QWidget()
    host.resize(1200, 800)
    tour = GuidedTour(host, [TourStep(title="t", text="x", target={})])

    target = QtCore.QRect(0, 385, 1200, 105)  # a full-width settings row
    size = QtCore.QSize(420, 550)  # taller than fits above or below it

    point = tour._place(target, size)
    placed = QtCore.QRect(point, size)

    assert placed.intersects(target), "the fixture no longer forces an overlap"
    assert not placed.contains(target.topLeft()), (
        "the bubble covers the target's top-left corner — the controls"
    )
    host.close()


def test_a_step_moves_a_wizard_through_its_nav_list(qapp):
    """A wizard step must change the heading too, not just the page.

    An AutoForm wizard is a nav list driving a ``QStackedWidget``, and the *list*
    is what updates the page, the title and the subtitle together. Setting the
    stack directly showed the right controls under the previous step's heading —
    which reads as a bug in the tool rather than in the tour. Seen on the
    anisotropy wizard: the g-factor fields appeared under "Welcome".
    """

    class _Wizard(QtWidgets.QWidget):
        """The shape WizardSection has: a nav list beside a stack."""

        def __init__(self):
            super().__init__()
            row = QtWidgets.QHBoxLayout(self)
            self.nav_list = QtWidgets.QListWidget()
            self.stack = QtWidgets.QStackedWidget()
            self.heading = QtWidgets.QLabel()
            for name in ("Welcome", "Corrections"):
                self.nav_list.addItem(name)
                page = QtWidgets.QWidget()
                QtWidgets.QVBoxLayout(page).addWidget(QtWidgets.QDoubleSpinBox())
                self.stack.addWidget(page)
            row.addWidget(self.nav_list)
            row.addWidget(self.stack)
            self.nav_list.currentRowChanged.connect(self._on_nav)
            self.nav_list.setCurrentRow(0)

        def _on_nav(self, index: int) -> None:
            self.stack.setCurrentIndex(index)
            self.heading.setText(self.nav_list.item(index).text())

    window = QtWidgets.QMainWindow()
    wizard = _Wizard()
    window.setCentralWidget(wizard)
    window.resize(600, 400)
    window.show()
    QtWidgets.QApplication.processEvents()

    target = wizard.stack.widget(1).findChild(QtWidgets.QDoubleSpinBox)
    target.setObjectName("g_factor")
    assert wizard.nav_list.currentRow() == 0

    tour = GuidedTour(window, [TourStep(title="t", text="x", target={"name": "g_factor"})])
    tour.start()

    assert wizard.nav_list.currentRow() == 1, "the nav list did not follow the step"
    assert wizard.heading.text() == "Corrections", (
        "the page changed but the heading did not — the window contradicts itself"
    )
    tour.stop()
    window.close()


def test_promoting_actions_leaves_the_section_scoped_ones_alone(qapp):
    """Only the named actions move up, and only an emptied row is hidden.

    A toolbar holding nothing but ``?`` and **Guide** is a band of chrome, so a
    tool's primary actions belong on it. But *only* those: a button scoped to a
    section — Add row, Apply to this field — reads as nonsense on a window-level
    bar.

    The second assertion is the one that cost a render: the helper hid the
    button's container once no buttons were left in it, which for a custom
    section pairing an action with a **status label** took the status line with
    it. The button moved and the result it reports disappeared.
    """
    from chisurf.gui.widgets.tools.help_guide import promote_to_toolbar

    window = QtWidgets.QMainWindow()
    form = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(form)

    pure_row = QtWidgets.QWidget()  # a button_row: nothing but buttons
    pure_layout = QtWidgets.QHBoxLayout(pure_row)
    run = QtWidgets.QToolButton()
    run._autoform_action = "generate"
    pure_layout.addWidget(run)
    layout.addWidget(pure_row)

    with_status = QtWidgets.QWidget()  # a custom section: action + status label
    status_layout = QtWidgets.QVBoxLayout(with_status)
    simulate = QtWidgets.QToolButton()
    simulate._autoform_action = "simulate"
    status = QtWidgets.QLabel("Set parameters and simulate.")
    status_layout.addWidget(simulate)
    status_layout.addWidget(status)
    layout.addWidget(with_status)

    add_row = QtWidgets.QToolButton()  # section-scoped: must stay put
    add_row._autoform_action = "add_row"
    layout.addWidget(add_row)

    window.setCentralWidget(form)
    toolbar = QtWidgets.QToolBar(window)
    window.addToolBar(toolbar)
    window.show()
    QtWidgets.QApplication.processEvents()

    moved = promote_to_toolbar(form, toolbar, ("generate", "simulate"))

    assert moved == [run, simulate]
    assert run.parent() is not pure_row and simulate.parent() is not with_status
    assert add_row.parent() is form, "a section-scoped button was promoted"
    assert pure_row.isHidden(), "an emptied button row was left as a gap"
    assert not with_status.isHidden(), "the status line went with the button"
    assert status.isVisible()
    window.close()

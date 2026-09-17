from qtpy import QtCore, QtWidgets

from chisurf.gui.widgets.dock_area import DockArea
from chisurf.gui.widgets.dock_area.dock_area import DockSplitter, DockTabWidget
from chisurf.gui.widgets.dock_area.dock_stacked_tab_widget import DockStackedTabWidget


def test_dock_area_basic(qtbot):
    """Test basic tab adding and switching index in DockArea."""
    dock_area = DockArea()
    qtbot.addWidget(dock_area)

    # Create test widgets
    w1 = QtWidgets.QWidget()
    w2 = QtWidgets.QWidget()
    w3 = QtWidgets.QWidget()

    # Add tabs
    dock_area.addTab(w1, "Tab 1")
    dock_area.addTab(w2, "Tab 2")
    dock_area.addTab(w3, "Tab 3")

    # Verify root widget is a DockTabWidget
    assert isinstance(dock_area._root_widget, DockTabWidget)
    assert dock_area._root_widget.count() == 3
    assert dock_area.currentIndex() == 0

    # Switch tab index and check signal
    signals = []

    def on_change(idx):
        signals.append(idx)

    dock_area.currentChanged.connect(on_change)

    dock_area._root_widget.setCurrentIndex(1)
    assert dock_area.currentIndex() == 1
    assert signals == [1]


def test_dock_area_split(qtbot):
    """Test split behavior and tree simplification/cleanup in DockArea."""
    dock_area = DockArea()
    qtbot.addWidget(dock_area)

    w1 = QtWidgets.QWidget()
    w2 = QtWidgets.QWidget()

    dock_area.addTab(w1, "Tab 1")
    dock_area.addTab(w2, "Tab 2")

    root_tw = dock_area._root_widget

    # Split: Remove Tab 2 (w2) and place in split to the right of root_tw
    root_tw.removeTab(1)
    new_tw = DockTabWidget(dock_area)
    new_tw.addTab(w2, "Tab 2")

    dock_area.split_tab_widget(root_tw, new_tw, "right")

    # Check that root widget is now a DockSplitter
    assert isinstance(dock_area._root_widget, DockSplitter)
    assert dock_area._root_widget.orientation() == QtCore.Qt.Horizontal
    assert dock_area._root_widget.count() == 2

    # Left widget should be root_tw, right should be new_tw
    assert dock_area._root_widget.widget(0) == root_tw
    assert dock_area._root_widget.widget(1) == new_tw

    # Remove last tab from root_tw, it should collapse the splitter and make new_tw the root widget
    root_tw.removeTab(0)
    dock_area.cleanup_empty_tab_widget(root_tw)

    assert dock_area._root_widget == new_tw
    assert isinstance(dock_area._root_widget, DockTabWidget)


def test_dock_area_restore(qtbot):
    """Test restoring split panels back to the main/primary tab group."""
    dock_area = DockArea()
    qtbot.addWidget(dock_area)

    w1 = QtWidgets.QWidget()
    w2 = QtWidgets.QWidget()

    dock_area.addTab(w1, "Tab 1")
    dock_area.addTab(w2, "Tab 2")

    root_tw = dock_area._root_widget

    # Split
    root_tw.removeTab(1)
    new_tw = DockTabWidget(dock_area)
    new_tw.addTab(w2, "Tab 2")
    dock_area.split_tab_widget(root_tw, new_tw, "right")

    assert isinstance(dock_area._root_widget, DockSplitter)

    # Restore Tab 2 back to the main tab widget
    dock_area.restore_tab(new_tw, 0)

    # Root splitter should be cleaned up and root widget should be back to DockTabWidget
    assert isinstance(dock_area._root_widget, DockTabWidget)
    assert dock_area._root_widget.count() == 2
    assert dock_area._root_widget.widget(0) == w1
    assert dock_area._root_widget.widget(1) == w2


def test_dock_area_close_hides_by_default_and_restores(qtbot):
    """Default close behavior should hide docks without destroying them."""
    dock_area = DockArea()
    qtbot.addWidget(dock_area)

    w1 = QtWidgets.QWidget()
    w2 = QtWidgets.QWidget()
    dock_area.addTab(w1, "Keep")
    dock_area.addTab(w2, "Hide")

    assert dock_area.count() == 2
    assert dock_area.visibleCount() == 2

    dock_area._request_close_tab(1)

    assert dock_area.count() == 2
    assert dock_area.visibleCount() == 1
    assert dock_area.hiddenIndexes() == [1]
    assert dock_area.widget(1) is w2
    assert w2.parentWidget() is dock_area
    assert dock_area.showTab(1) is True
    assert dock_area.visibleCount() == 2


def test_dock_area_does_not_close_last_visible_dock(qtbot):
    """The last visible dock must stay open."""
    dock_area = DockArea()
    qtbot.addWidget(dock_area)

    dock_area.addTab(QtWidgets.QWidget(), "Only")

    assert dock_area.canCloseTab(0) is False
    dock_area._request_close_tab(0)
    assert dock_area.visibleCount() == 1
    assert dock_area.hiddenIndexes() == []


def test_dock_area_remove_close_mode_removes_dock(qtbot):
    """Docks marked with remove close mode should be removed from registry."""
    dock_area = DockArea()
    qtbot.addWidget(dock_area)

    keep = QtWidgets.QWidget()
    files = QtWidgets.QWidget()
    dock_area.addTab(keep, "Keep")
    dock_area.addTab(files, "Files", close_mode="remove")

    dock_area._request_close_tab(1)

    assert dock_area.count() == 1
    assert dock_area.widget(0) is keep
    assert dock_area.hiddenIndexes() == []


def test_layout_restore_preserves_pages_missing_from_saved_layout(qtbot):
    """Restoring a partial layout must not destroy registered page widgets."""
    dock_area = DockArea()
    qtbot.addWidget(dock_area)

    keep = QtWidgets.QWidget()
    filter_page = QtWidgets.QWidget()
    filter_layout = QtWidgets.QVBoxLayout(filter_page)
    combo = QtWidgets.QComboBox(filter_page)
    combo.addItem("Test")
    filter_layout.addWidget(combo)

    dock_area.addTab(keep, "Keep")
    dock_area.addTab(filter_page, "Filter Settings")
    state = {
        "version": 1,
        "root": {
            "type": "tab",
            "tabs": [
                {
                    "widget_key": "Keep",
                    "tab_name": "Keep",
                    "tab_text": "Keep",
                }
            ],
            "current_index": 0,
        },
        "active_tab_widget": [],
        "current_index": 0,
    }

    assert dock_area.set_layout_state(state)
    QtWidgets.QApplication.processEvents()

    assert combo.currentText() == "Test"
    assert filter_page.parentWidget() is dock_area
    assert dock_area.hiddenIndexes() == [1]
    assert dock_area.showTab(1) is True
    assert combo.currentText() == "Test"
    assert dock_area.isTabVisible(1) is True


def test_dock_area_stacked_option_creates_stacked_tab_widget(qtbot):
    """A DockArea created with stacked_tabs=True uses DockStackedTabWidget."""
    dock_area = DockArea(stacked_tabs=True)
    qtbot.addWidget(dock_area)

    w1 = QtWidgets.QWidget()
    dock_area.addTab(w1, "Tab 1")

    assert isinstance(dock_area._root_widget, DockStackedTabWidget)


def test_dock_area_stacked_basic(qtbot):
    """Basic tab adding and switching works in stacked tab mode."""
    dock_area = DockArea(stacked_tabs=True)
    qtbot.addWidget(dock_area)

    w1 = QtWidgets.QWidget()
    w2 = QtWidgets.QWidget()
    w3 = QtWidgets.QWidget()

    dock_area.addTab(w1, "Tab 1")
    dock_area.addTab(w2, "Tab 2")
    dock_area.addTab(w3, "Tab 3")

    assert dock_area._root_widget.count() == 3
    assert dock_area.currentIndex() == 0

    signals = []

    def on_change(idx):
        signals.append(idx)

    dock_area.currentChanged.connect(on_change)
    dock_area._root_widget.setCurrentIndex(1)

    assert dock_area.currentIndex() == 1
    assert signals == [1]


def test_dock_area_stacked_layout_state_roundtrip(qtbot):
    """Layout state round-trips through split tab widgets in stacked mode."""
    dock_area = DockArea(stacked_tabs=True)
    qtbot.addWidget(dock_area)

    w1 = QtWidgets.QWidget()
    w2 = QtWidgets.QWidget()

    dock_area.addTab(w1, "Tab 1")
    dock_area.addTab(w2, "Tab 2")

    root_tw = dock_area._root_widget
    root_tw.removeTab(1)
    new_tw = DockStackedTabWidget(dock_area)
    new_tw.addTab(w2, "Tab 2")
    dock_area.split_tab_widget(root_tw, new_tw, "right")

    assert isinstance(dock_area._root_widget, DockSplitter)
    assert dock_area._root_widget.orientation() == QtCore.Qt.Horizontal
    assert dock_area._root_widget.count() == 2

    dock_area.restore_tab(new_tw, 0)

    assert isinstance(dock_area._root_widget, DockStackedTabWidget)
    assert dock_area._root_widget.count() == 2
    assert dock_area._root_widget.widget(0) is w1
    assert dock_area._root_widget.widget(1) is w2


def test_dock_area_stacked_close_hides_and_restores(qtbot):
    """Default close behavior hides docks without destroying them in stacked mode."""
    dock_area = DockArea(stacked_tabs=True)
    qtbot.addWidget(dock_area)

    w1 = QtWidgets.QWidget()
    w2 = QtWidgets.QWidget()
    dock_area.addTab(w1, "Keep")
    dock_area.addTab(w2, "Hide")

    assert dock_area.count() == 2
    assert dock_area.visibleCount() == 2

    dock_area._request_close_tab(1)

    assert dock_area.count() == 2
    assert dock_area.visibleCount() == 1
    assert dock_area.hiddenIndexes() == [1]
    assert dock_area.widget(1) is w2
    assert w2.parentWidget() is dock_area
    assert dock_area.showTab(1) is True
    assert dock_area.visibleCount() == 2


def test_dock_area_is_inside_client_content(qtbot):
    """Test is_inside_client_content correctly identifies clicks inside client widgets."""
    dock_area = DockArea()
    qtbot.addWidget(dock_area)

    w1 = QtWidgets.QWidget()
    child_btn = QtWidgets.QPushButton("Click Me", w1)
    layout = QtWidgets.QVBoxLayout(w1)
    layout.addWidget(child_btn)

    dock_area.addTab(w1, "Tab 1")
    dock_area.show()

    # Wait for the widget to be visible/exposed on screen
    qtbot.waitExposed(dock_area)

    # Get the global position of the center of child_btn
    global_pos = child_btn.mapToGlobal(child_btn.rect().center())

    # It should be identified as inside client content
    assert dock_area.is_inside_client_content(global_pos) is True

    # A position outside should be False
    outside_pos = QtCore.QPoint(-1000, -1000)
    assert dock_area.is_inside_client_content(outside_pos) is False


def _split_state(sizes):
    """Return a two-pane vertical layout asking for *sizes*."""
    return {
        "version": 1,
        "root": {
            "type": "splitter",
            "orientation": "vertical",
            "sizes": list(sizes),
            "children": [
                {
                    "type": "tab",
                    "tabs": [{"widget_key": "Top", "tab_name": "Top"}],
                    "current_index": 0,
                },
                {
                    "type": "tab",
                    "tabs": [{"widget_key": "Bottom", "tab_name": "Bottom"}],
                    "current_index": 0,
                },
            ],
        },
        "active_tab_widget": [0],
        "current_index": 0,
    }


def _restore(dock_area, sizes):
    top, bottom = QtWidgets.QTextEdit(), QtWidgets.QTextEdit()
    dock_area.addTab(top, "Top")
    dock_area.addTab(bottom, "Bottom")
    dock_area.set_layout_state(
        _split_state(sizes),
        key_func=lambda w: dock_area.tabText(dock_area.indexOf(w)),
    )
    # Shown, or the splitter never lays out and every share stays at its minimum
    # -- which is also the state the authored sizes are first applied in.
    dock_area.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    dock_area.show()
    return dock_area._root_widget


def test_authored_sizes_survive_the_resize_that_follows(qtbot):
    """An authored split has to hold once the window has a real size.

    A dock area is built before it is shown -- the splitter is about 100x30 --
    so ``setSizes`` clamps every share to the children's minimums, and the
    resize that follows redistributes by rules of Qt's own. An authored 80/20
    came out inverted, silently, in every layout that asked for a split.
    """
    dock_area = DockArea()
    qtbot.addWidget(dock_area)
    splitter = _restore(dock_area, [800, 200])
    assert isinstance(splitter, DockSplitter)

    dock_area.resize(600, 1000)
    qtbot.wait(50)
    top, bottom = splitter.sizes()
    assert top > bottom * 3, f"authored 80/20 came out {top}/{bottom}"


def test_the_proportions_hold_at_any_window_size(qtbot):
    """They are proportions, not pixels: a small window splits the same way."""
    dock_area = DockArea()
    qtbot.addWidget(dock_area)
    splitter = _restore(dock_area, [800, 200])

    ratios = []
    for height in (400, 900, 1400):
        dock_area.resize(600, height)
        qtbot.wait(30)
        top, bottom = splitter.sizes()
        ratios.append(top / max(top + bottom, 1))
    assert all(abs(r - 0.8) < 0.12 for r in ratios), ratios


def test_dragging_a_divider_wins_over_the_author(qtbot):
    """Once the user moves it, it is theirs -- the layout stops re-applying."""
    dock_area = DockArea()
    qtbot.addWidget(dock_area)
    splitter = _restore(dock_area, [800, 200])
    dock_area.resize(600, 1000)
    qtbot.wait(50)

    # What a drag does: move the handle, which emits splitterMoved.
    splitter.setSizes([300, 700])
    splitter.splitterMoved.emit(300, 1)
    dock_area.resize(600, 1200)
    qtbot.wait(50)

    top, bottom = splitter.sizes()
    assert bottom > top, f"the authored split came back as {top}/{bottom}"


def test_a_restored_dock_goes_back_to_the_stack_it_was_closed_from(qtbot):
    """A settings page must not reappear in the plot column.

    ``showTab`` used to hand the page to ``find_main_tab_widget``, i.e. whichever
    stack ``findChildren`` returned first. In a split layout that is arbitrary,
    and a page restored into the wrong column is technically visible and
    practically lost.
    """
    dock_area = DockArea()
    qtbot.addWidget(dock_area)

    settings = QtWidgets.QWidget()
    channels = QtWidgets.QWidget()
    plot = QtWidgets.QWidget()
    for widget, name in ((settings, "Settings"), (channels, "Channels"), (plot, "Plot")):
        dock_area.addTab(widget, name)

    def _tab(*names):
        return {
            "type": "tab",
            "current_index": 0,
            "tabs": [{"widget_key": n, "tab_name": n, "tab_text": n} for n in names],
        }

    assert dock_area.set_layout_state(
        {
            "version": 1,
            "root": {
                "type": "splitter",
                "orientation": "horizontal",
                "sizes": [400, 800],
                "children": [_tab("Settings", "Channels"), _tab("Plot")],
            },
            "active_tab_widget": [],
            "current_index": 0,
        },
        emit_change=False,
    )
    QtWidgets.QApplication.processEvents()

    left = dock_area._tab_widget_for_page(settings)
    right = dock_area._tab_widget_for_page(plot)
    assert left is not right, "the two columns collapsed; the fixture is wrong"

    index = dock_area.indexOf(channels)
    assert dock_area.hideTab(index) is True
    QtWidgets.QApplication.processEvents()
    assert dock_area.showTab(index) is True
    QtWidgets.QApplication.processEvents()

    assert dock_area._tab_widget_for_page(channels) is left, (
        "the restored page landed in the other column"
    )


def test_the_main_tab_widget_is_never_an_orphan(qtbot):
    """A stack dropped from the layout must not be offered as the main one.

    ``_build_widget_from_state`` calls ``deleteLater`` on a node that ended up
    with no tabs, and a deferred deletion is still a ``findChildren`` result. One
    of those used to be returned as *the* main tab widget, so a page restored
    into it rendered at its last standalone size on top of the real docks.
    """
    dock_area = DockArea()
    qtbot.addWidget(dock_area)
    page = QtWidgets.QWidget()
    dock_area.addTab(page, "Only")

    # The real path, not a hand-built orphan: a tab node naming a page that is
    # not there makes ``_build_widget_from_state`` create a stack, find nothing
    # to put in it, and ``deleteLater`` it. That stack is still a child.
    dock_area.set_layout_state(
        {
            "version": 1,
            "root": {
                "type": "splitter",
                "orientation": "horizontal",
                "children": [
                    {"type": "tab", "tabs": [{"tab_name": "Gone"}], "current_index": 0},
                    {"type": "tab", "tabs": [{"tab_name": "Only"}], "current_index": 0},
                ],
            },
            "active_tab_widget": [],
            "current_index": 0,
        },
        emit_change=False,
    )
    QtWidgets.QApplication.processEvents()

    real = dock_area._tab_widget_for_page(page)
    orphans = [tw for tw in dock_area._find_tab_widgets() if tw is not real and tw.count() == 0]
    assert orphans, "the fixture produced no orphaned stack"
    assert dock_area.find_main_tab_widget() is real


def _flush_deletes():
    """Run the deferred deletes an event loop would (``processEvents`` does not)."""
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


def test_a_saved_split_with_a_missing_pane_restores_without_a_one_child_splitter(qtbot):
    """A layout naming a page that is gone must not leave a splitter around one stack.

    Emptying that stack deleted the splitter while the area still held it as the
    root, and every later save failed with "wrapped C/C++ object of type
    DockSplitter has been deleted" -- what a lifetime fit window did once its
    model stopped offering a plot its saved layout named.
    """
    area = DockArea()
    qtbot.addWidget(area)
    pages = {}
    for name in ("fit", "table"):
        page = QtWidgets.QWidget()
        page.setProperty("k", name)
        area.addTab(page, name)
        pages[name] = page
    state = {
        "version": 1,
        "active_tab_widget": None,
        "current_index": 0,
        "root": {
            "type": "splitter",
            "orientation": "horizontal",
            "sizes": [1, 1],
            "children": [
                {"type": "tab", "tabs": [{"widget_key": "fit"}, {"widget_key": "table"}]},
                {"type": "tab", "tabs": [{"widget_key": "a plot that is gone"}]},
            ],
        },
    }
    key = lambda widget: widget.property("k")  # noqa: E731

    assert area.set_layout_state(state, key_func=key, emit_change=False)
    _flush_deletes()
    assert isinstance(area._root_widget, DockTabWidget)

    stack = area._root_widget
    for index in range(stack.count() - 1, -1, -1):
        stack.removeTab(index)
    area.cleanup_empty_tab_widget(stack)
    _flush_deletes()
    area.get_layout_state(key_func=key)


def test_emptying_the_last_stack_of_a_root_splitter_clears_the_root(qtbot):
    area = DockArea()
    qtbot.addWidget(area)
    page = QtWidgets.QWidget()
    area.addTab(page, "only")
    stack = area._root_widget
    splitter = DockSplitter(QtCore.Qt.Horizontal, area)
    area.replace_widget(stack, splitter)
    splitter.addWidget(stack)
    assert area._root_widget is splitter

    stack.removeTab(0)
    area.cleanup_empty_tab_widget(stack)
    _flush_deletes()

    assert area._root_widget is None
    area.get_layout_state()

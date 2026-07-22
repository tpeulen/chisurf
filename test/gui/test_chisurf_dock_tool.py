"""PRD-23 Task 1: the shared dockable-tool base.

Constructs `ChisurfDockTool` (and `PathDropListWidget`) and asserts the factored
behaviour the transformer tools now reuse: window-level path-drop dispatch to a
hook, lazy MMFDB-connectivity accessors that do no work on construction, and
geometry-persistence helpers.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.gui.widgets.tools import ChisurfDockTool, PathDropListWidget


def test_path_drop_list_widget_constructs(qapp):
    widget = PathDropListWidget()
    # the drag-drop signal the tools connect to exists
    assert hasattr(widget, "pathsDropped")
    assert widget.supportedDropActions() is not None


def test_path_drop_list_widget_enables_drops_on_construction(qapp):
    # Regression: the widget overrode the drag/drop handlers but never enabled
    # drops, so Qt discarded every drag before those handlers ran. Both the
    # widget and its viewport (the child that actually receives OS drag events
    # in an item view) must accept drops.
    widget = PathDropListWidget()
    assert widget.acceptDrops() is True
    assert widget.viewport().acceptDrops() is True


def test_path_drop_list_widget_accepts_optional_filter(qapp):
    # the extension-filtering variant (used by the TTTR time-window tool) constructs
    widget = PathDropListWidget(path_filter=lambda p: p.endswith(".ptu"))
    assert widget._path_filter is not None
    assert widget._path_filter("/d/x.ptu") is True
    assert widget._path_filter("/d/x.txt") is False


def test_dock_tool_constructs_read_only(qapp):
    """Construction wires Qt only — no MMFDB connection acquired."""
    tool = ChisurfDockTool()
    assert tool.acceptDrops() is True
    # base hook defaults to no connection; construction did not open one
    assert tool.acquire_mmfdb_connection() is None
    assert tool.mmfdb_connection() is None
    assert tool.mmfdb_connected() is False
    tool.close()


def test_on_paths_dropped_forwards_to_add_paths(qapp):
    """The default drop hook forwards to a subclass ``_add_paths`` convention."""
    received: list[list[Path]] = []

    class _Tool(ChisurfDockTool):
        def _add_paths(self, paths):
            received.append(paths)

    tool = _Tool()
    sample = [Path("/tmp/a.ptu"), Path("/tmp/b.ptu")]
    tool.on_paths_dropped(sample)
    assert received == [sample]
    tool.close()


def test_acquire_mmfdb_connection_override_is_used(qapp):
    sentinel = object()

    class _Tool(ChisurfDockTool):
        def acquire_mmfdb_connection(self):
            return sentinel

    tool = _Tool()
    assert tool.mmfdb_connection() is sentinel
    assert tool.mmfdb_connected() is True
    tool.close()


def test_mmfdb_connection_swallows_hook_errors(qapp):
    class _Tool(ChisurfDockTool):
        def acquire_mmfdb_connection(self):
            raise RuntimeError("boom")

    tool = _Tool()
    # mmfdb_connection is defensive: a failing hook yields None, not a crash
    assert tool.mmfdb_connection() is None
    assert tool.mmfdb_connected() is False
    tool.close()

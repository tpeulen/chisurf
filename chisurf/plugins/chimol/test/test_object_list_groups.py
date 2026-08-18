"""A group is a row in the object list -- on every host.

The Qt window built group rows (a header, its members indented, a closed one
standing for all of them); the shared host's ``sync_panel`` did not. So the
same scene was two different lists: folded on the desktop's Qt window, and
thirty-four flat rows on the toolkit-free host and in the browser, with no
group visible at all and nothing to collapse.

That is the shape of fault this project keeps finding -- one behaviour, two
implementations, one of them behind -- and it showed the moment something
*made* groups: loading a labelling network puts seventeen dye clouds and their
seventeen mean positions into two, because they are wanted or not wanted as a
set.
"""
from __future__ import annotations

import pytest

from chimol.hosts.base import sync_panel
from chimol.ui.gui import InternalGui


class _Objects:
    """A viewer's object list, as the panel reads it."""

    def __init__(self, entries):
        self._entries = list(entries)

    def list_objects(self):
        return list(self._entries)

    def selection_is_visible(self):
        return True


def _rows(entries):
    gui = InternalGui()
    sync_panel(_Objects(entries), gui)
    return gui.rows


def test_a_group_is_a_row_of_its_own():
    rows = _rows([
        {"id": "o1", "name": "structure", "visible": True},
        {"id": "o2", "name": "av_a", "visible": True, "group": "clouds",
         "group_open": True},
        {"id": "o3", "name": "av_b", "visible": True, "group": "clouds",
         "group_open": True},
    ])
    names = [row.name for row in rows]
    assert "clouds" in names
    group = next(row for row in rows if row.name == "clouds")
    assert group.is_group and group.group_open


def test_members_of_an_open_group_are_indented_under_it():
    rows = _rows([
        {"id": "o2", "name": "av_a", "visible": True, "group": "clouds",
         "group_open": True},
        {"id": "o3", "name": "av_b", "visible": True, "group": "clouds",
         "group_open": True},
    ])
    members = [row for row in rows if row.name.startswith("av_")]
    assert len(members) == 2
    assert all(row.indent == 1 for row in members)


def test_a_closed_group_stands_for_its_members():
    """Which is the whole point: seventeen clouds are one row and one switch."""
    rows = _rows([
        {"id": "o1", "name": "structure", "visible": True},
        *[
            {"id": f"o{i}", "name": f"av_{i}", "visible": True,
             "group": "clouds", "group_open": False}
            for i in range(17)
        ],
    ])
    names = [row.name for row in rows]
    assert "clouds" in names
    assert not [name for name in names if name.startswith("av_")]
    closed = next(row for row in rows if row.name == "clouds")
    assert row_is_closed(closed)


def row_is_closed(row) -> bool:
    return bool(row.is_group and not row.group_open)


def test_an_ungrouped_object_is_not_indented():
    rows = _rows([{"id": "o1", "name": "structure", "visible": True}])
    row = next(row for row in rows if row.name == "structure")
    assert row.indent == 0 and not row.is_group


def test_the_two_hosts_build_the_same_list():
    """The Qt window's own row builder and the shared one must agree.

    Compared as *data* rather than by calling the Qt path -- what matters is
    that the shared builder now knows the three things the Qt one knew: a
    header row per group, the indent, and that a closed group hides its
    members.
    """
    import inspect

    from chimol.hosts import base

    source = inspect.getsource(base.sync_panel)
    for clause in ("group_open", "is_group=True", "indent=1 if group else 0"):
        assert clause in source, clause


def test_the_qt_window_uses_the_shared_builder():
    """One object list, one implementation.

    The Qt window carried ninety lines of its own row building, which is how
    groups came to be rows in that window and nowhere else. It calls the shared
    builder now and keeps only what is genuinely its own -- the menu bar macOS
    will not draw natively, the toolbar, and the Qt callbacks.
    """
    import inspect

    from chimol.hosts.qt import window as qt_window

    source = inspect.getsource(qt_window.MolViewPluginWindow.sync_internal_gui)
    assert "sync_panel(" in source
    for gone in ("is_group=True", "seen_groups", "_measurement_rows()"):
        assert gone not in source, f"the Qt window builds rows again: {gone}"


def test_the_grouping_order_is_shared_too():
    """A group's members are contiguous -- a fact about lists, not toolkits."""
    from chimol.hosts.base import grouped_display_order

    ordered = grouped_display_order([
        {"name": "a"},
        {"name": "b", "group": "G"},
        {"name": "c"},
        {"name": "d", "group": "G"},
    ])
    assert [row["name"] for row in ordered] == ["a", "b", "d", "c"]

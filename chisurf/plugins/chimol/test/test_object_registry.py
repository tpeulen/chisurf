"""There is one object list, and every view of it consumes the same signal.

The architecture, and why it needed one
---------------------------------------
Everything on screen is a view of one list: the object panel, the sequence
strip, the density controls, the hierarchy, the Qt window's list, the browser's.
That list was a bare ``OrderedDict`` on the viewer, mutated by six of the
viewer's own methods and by two other modules reaching in, and it announced
nothing at all.

So each view was kept in step by whoever remembered. The loader called the host,
the Qt window called itself from four places it happened to think of, and the
commands that make an object without loading a file -- ``load_map``,
``molmap``, ``create``, ``delete`` -- called nobody. A density map therefore
never appeared in the object list on any host; with no row it could not be made
active; and the density panel, which edits "the active object's map", could not
be pointed back at the first of two maps. Three reported symptoms, one missing
signal.

The fix is not another call site. It is
:class:`~chimol.renderer.object_registry.ObjectRegistry`: the list counts its
own changes, and the views **consume** that count rather than being dispatched
to. Pull, not push -- every view here already repaints on a clock, so comparing
an integer costs nothing and cannot be forgotten the way a subscription can.

What this pins
--------------
* every kind of change bumps the revision, **including** the two mutations that
  reach in from outside the viewer -- which is why the registry is a
  ``MutableMapping`` and not a class with named methods over a private dict;
* a no-op does not bump it, or "changed" means nothing;
* reordering keeps the *same* registry, since rebinding the attribute throws
  away the counter every view is comparing against;
* all three hosts consume it;
* the list is **replayable**: every mutation is recorded, with what changed and
  to which object, so a history can be built on top rather than bolted through
  the six methods and two outside modules that mutate it. That is the reason
  the mapping protocol is the choke point rather than a set of named methods.
"""
from __future__ import annotations

import pytest

from chimol.renderer.object_registry import (
    Change,
    ObjectRegistry,
)


class _Entry:
    def __init__(self, name="x"):
        self.name = name
        self.visible = True


# ------------------------------------------------------------- the registry


def test_every_mutation_counts():
    registry = ObjectRegistry()
    start = registry.revision

    registry["a"] = _Entry("a")
    after_add = registry.revision
    assert after_add > start, "an addition did not count"

    registry["b"] = _Entry("b")
    assert registry.revision > after_add

    del registry["a"]
    after_delete = registry.revision
    assert after_delete > after_add, "a removal did not count"

    registry.clear()
    assert registry.revision > after_delete, "a clear did not count"


def test_the_mapping_protocol_is_the_choke_point():
    """Two modules outside the viewer mutate the list directly.

    ``cmd/interactions.py`` drops a mutagenesis preview with ``pop`` and
    ``renderer/session.py`` empties the list with ``clear``. Neither would call
    a named method it does not know about, so the mapping itself has to be what
    counts -- that is the whole reason this is a ``MutableMapping``.
    """
    registry = ObjectRegistry({"a": _Entry()})
    before = registry.revision
    registry.pop("a", None)
    assert registry.revision > before, "pop did not count"

    registry["b"] = _Entry()
    before = registry.revision
    registry.clear()
    assert registry.revision > before, "clear did not count"


def test_a_reorder_keeps_the_same_registry():
    """Rebinding to a fresh dict is what the viewer used to do.

    It loses the counter, so the next change reads as the first one and every
    view that had caught up believes it still is.
    """
    registry = ObjectRegistry({"a": _Entry(), "b": _Entry(), "c": _Entry()})
    identity = id(registry)
    before = registry.revision

    registry.reorder(["c", "a"])
    assert list(registry) == ["c", "a", "b"]
    assert id(registry) == identity
    assert registry.revision > before


def test_reordering_to_the_same_order_is_not_a_change():
    """A revision that moves for nothing makes every consumer do the work."""
    registry = ObjectRegistry({"a": _Entry(), "b": _Entry()})
    before = registry.revision
    registry.reorder(["a", "b"])
    assert registry.revision == before


def test_reading_never_counts():
    registry = ObjectRegistry({"a": _Entry()})
    before = registry.revision
    _ = registry["a"], len(registry), list(registry), registry.get("a"), "a" in registry
    assert registry.revision == before


# ------------------------------------------------------- through the viewer


@pytest.fixture(scope="module")
def measured():
    from toolkit_free import probe

    return probe('''
        app = open_app(size=(600, 460))
        viewer = app.viewer
        gui = app.renderer._internal_gui

        def revision():
            return viewer.objects_revision()

        emit("start", revision())
        app.cmd.do("fetch 148L")
        emit("structure", revision())
        app.cmd.do("molmap 148l, 8, sim")
        emit("map", revision())
        app.cmd.do("disable sim")
        emit("hidden", revision())
        app.cmd.do("zoom all")
        emit("noop", revision())
        app.cmd.do("delete sim")
        emit("deleted", revision())
        emit("rows", ",".join(r.name for r in gui.rows))
    ''')


def test_the_viewer_reports_every_kind_of_change(measured):
    """Loading, creating, hiding and deleting all move the revision."""
    order = ["start", "structure", "map", "hidden"]
    values = [int(measured[key]) for key in order]
    for earlier, later, label in zip(values, values[1:], order[1:]):
        assert later > earlier, f"{label} did not move the revision"


def test_a_command_that_changes_nothing_does_not_move_it(measured):
    """`zoom` is not an object change, and a signal that fires for it is noise."""
    assert int(measured["noop"]) == int(measured["hidden"])


def test_a_delete_moves_it_and_the_row_goes(measured):
    assert int(measured["deleted"]) > int(measured["noop"])
    assert "sim" not in measured["rows"].split(",")


# --------------------------------------------------------- every consumer


def test_all_three_hosts_consume_the_registry():
    """The rule is written once and used by each host, rather than three times.

    Checked by reading the source, deliberately: the browser host cannot be
    constructed here, and the property that matters is that no host is left
    keeping the list in step by hand.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "chimol"
    hosts = {
        "toolkit-free": root / "host" / "run.py",
        "Qt": root / "app" / "molview_main_window.py",
        "browser": root / "web" / "demo.py",
    }
    for label, path in hosts.items():
        text = path.read_text(encoding="utf-8")
        assert "consume_object_changes" in text, (
            f"the {label} host does not consume the object registry"
        )


# ---------------------------------------------------------------- history


def test_the_history_records_what_happened():
    """Not that something happened -- what, and to which object."""
    registry = ObjectRegistry()
    registry["a"] = _Entry()
    registry["b"] = _Entry()
    registry["a"] = _Entry()      # replaced, not added
    registry.touch("touch", "b", "hidden")
    del registry["b"]

    kinds = [(c.kind, c.object_id, c.detail) for c in registry.history()]
    assert kinds == [
        ("add", "a", ""),
        ("add", "b", ""),
        ("replace", "a", ""),
        ("touch", "b", "hidden"),
        ("remove", "b", ""),
    ], kinds


def test_the_history_is_addressed_by_revision():
    """A consumer holding revision r takes everything after r, and no more."""
    registry = ObjectRegistry()
    registry["a"] = _Entry()
    mark = registry.revision
    registry["b"] = _Entry()
    del registry["a"]

    since = registry.changes_since(mark)
    assert [c.object_id for c in since] == ["b", "a"]
    assert all(c.revision > mark for c in since)
    assert registry.changes_since(registry.revision) == ()


def test_a_consumer_can_tell_it_fell_too_far_behind():
    """A replayed history with holes in it is worse than a rebuild."""
    registry = ObjectRegistry(history=4)
    for index in range(10):
        registry[f"o{index}"] = _Entry()

    assert len(registry.history()) == 4
    assert registry.forgot_before() > 0
    # Someone holding revision 1 is behind the ring and must rebuild.
    assert 1 < registry.forgot_before()


def test_a_change_is_a_value():
    """Frozen, so a history cannot be edited by whoever reads it."""
    change = Change(revision=1, kind="add", object_id="a")
    with pytest.raises(Exception):
        change.kind = "remove"  # type: ignore[misc]


# ------------------------------------------------- measurements are objects


@pytest.fixture(scope="module")
def measured_measurements():
    from toolkit_free import probe

    return probe('''
        app = open_app(size=(600, 460))
        viewer = app.viewer
        gui = app.renderer._internal_gui
        errors = []
        app.cmd.set_error_callback(errors.append)

        app.cmd.do("fetch 148L")
        mark = viewer.objects_revision()
        app.cmd.do("distance d1, resi 10 and name ca, resi 40 and name ca")
        emit("errors", "; ".join(errors) or "none")
        emit("rows", ",".join(r.name for r in gui.rows))
        emit("changes", ";".join(
            f"{c.kind}:{c.object_id}:{c.detail}"
            for c in viewer.object_changes_since(mark)
        ))

        errors.clear()
        app.cmd.do("delete d1")
        emit("delete_errors", "; ".join(errors) or "none")
        emit("rows_after", ",".join(r.name for r in gui.rows))
    ''')


def test_a_measurement_is_listed_as_an_object(measured_measurements):
    """A `distance` has a name, a row and an on/off switch -- it is an object.

    The Qt window listed them; the toolkit-free window and the browser did not,
    so a measurement could be made there and never seen again.
    """
    assert measured_measurements["errors"] == "none"
    assert "d1" in measured_measurements["rows"].split(",")


def test_making_a_measurement_is_recorded(measured_measurements):
    """It changes the list, so it belongs in the list's history."""
    assert "measurements" in measured_measurements["changes"]


def test_deleting_a_measurement_works_and_removes_the_row(measured_measurements):
    """`delete` reported "Not found" for a name in the list it was read from."""
    assert measured_measurements["delete_errors"] == "none"
    assert "d1" not in measured_measurements["rows_after"].split(",")


# ------------------------------------------------------------ undo and redo


def test_undo_puts_an_object_back_where_it_was():
    """At its position, not at the end -- otherwise undoing reorders the list."""
    registry = ObjectRegistry()
    for name in ("a", "b", "c"):
        registry[name] = _Entry(name)

    del registry["b"]
    assert list(registry) == ["a", "c"]

    change = registry.undo()
    assert list(registry) == ["a", "b", "c"], "the entry came back in the wrong place"
    assert change.kind == "remove"


def test_redo_reapplies_it():
    registry = ObjectRegistry({"a": _Entry(), "b": _Entry()})
    del registry["b"]
    registry.undo()
    registry.redo()
    assert list(registry) == ["a"]


def test_a_new_change_ends_the_redo_branch():
    """As every undo stack does: the redos described a future that is gone."""
    registry = ObjectRegistry()
    registry["a"] = _Entry()
    registry["b"] = _Entry()
    registry.undo()
    assert registry.can_redo()

    registry["c"] = _Entry()
    assert not registry.can_redo(), "a redo survived a new change"


def test_undoing_does_not_stack_up_more_to_undo():
    """The classic loop: the inverse recorded as a change, undone forever."""
    registry = ObjectRegistry()
    registry["a"] = _Entry()
    registry["b"] = _Entry()

    depth = len(registry._undo)
    registry.undo()
    assert len(registry._undo) == depth - 1, "the inverse was recorded as a change"


def test_an_undo_still_moves_the_revision():
    """Views have to re-read: the list did change, however it got there."""
    registry = ObjectRegistry({"a": _Entry()})
    del registry["a"]
    before = registry.revision
    registry.undo()
    assert registry.revision > before


def test_undo_on_an_empty_stack_answers_none():
    registry = ObjectRegistry()
    assert registry.undo() is None
    assert registry.redo() is None


def test_a_visibility_touch_is_logged_but_not_undoable():
    """It does not record the value it replaced, so it cannot be inverted.

    Logged all the same -- the action list is a record of what happened, and
    leaving out the changes that cannot be undone would make it a record of
    something else.
    """
    registry = ObjectRegistry({"a": _Entry()})
    registry.touch("touch", "a", "hidden", label="hide a")
    assert registry.history()[-1].label == "hide a"
    assert not registry.can_undo()

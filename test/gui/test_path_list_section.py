"""The shared ``path_list`` AutoForm section — drops, buttons, and MMFDB.

Covers the unification: one drop-list section reused everywhere, now with a
"select from the MMFDB database" button so every file selector can pull from the
database (including S3-backed object stores, which resolve to a local path).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.gui.autoform.sections.path_list_section import PathListWidget


class _Model:
    """Minimal model holding a ``list[str]`` attribute the section binds to."""

    def __init__(self):
        self.files: list[str] = []
        self.updated = 0

    def update(self):
        self.updated += 1


def _button_texts(widget: PathListWidget) -> list[str]:
    from qtpy import QtWidgets

    return [b.text() for b in widget.findChildren(QtWidgets.QToolButton)]


def test_path_list_has_database_button_by_default(qapp):
    widget = PathListWidget(_Model(), "files")
    assert any("Database" in t for t in _button_texts(widget))


def test_path_list_database_button_can_be_disabled(qapp):
    widget = PathListWidget(_Model(), "files", mmfdb=False)
    assert not any("Database" in t for t in _button_texts(widget))


def test_add_from_mmfdb_commits_resolved_path(qapp, tmp_path, monkeypatch):
    # A resolved database path must flow through the same commit path as a drop:
    # written to the model attribute, de-duplicated, and model.update() called.
    sample = tmp_path / "from_db.ptu"
    sample.write_bytes(b"x")

    from chisurf.gui.widgets.mmfdb import picker

    monkeypatch.setattr(picker, "inprocess_client", lambda: object())
    monkeypatch.setattr(picker, "pick_local_paths", lambda *a, **k: [sample])

    model = _Model()
    widget = PathListWidget(model, "files", extensions=[".ptu"])
    widget._add_from_mmfdb()

    assert model.files == [str(sample)]
    assert model.updated >= 1


def test_add_from_mmfdb_without_database_is_quiet(qapp, monkeypatch):
    # No database available -> nothing added, no crash (the info dialog is
    # suppressed so the test does not block on a modal).
    from qtpy import QtWidgets

    from chisurf.gui.widgets.mmfdb import picker

    monkeypatch.setattr(picker, "inprocess_client", lambda: None)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    model = _Model()
    widget = PathListWidget(model, "files")
    widget._add_from_mmfdb()

    assert model.files == []


def test_public_api_add_paths_and_clear(qapp, tmp_path):
    """add_paths / paths / clear expose the list to standalone hosts."""
    f1 = tmp_path / "a.ptu"
    f1.write_bytes(b"1")
    f2 = tmp_path / "b.ptu"
    f2.write_bytes(b"2")
    model = _Model()
    widget = PathListWidget(model, "files", extensions=[".ptu"])

    widget.add_paths([f1, f2])
    assert widget.paths() == [str(f1), str(f2)]
    assert model.files == [str(f1), str(f2)]

    widget.clear()
    assert widget.paths() == []
    assert model.files == []


def test_selection_signal_and_select_first(qapp, tmp_path):
    """select_first auto-selects row 0; selectionChanged reports the selection."""
    f1 = tmp_path / "a.ptu"
    f1.write_bytes(b"1")
    f2 = tmp_path / "b.ptu"
    f2.write_bytes(b"2")
    model = _Model()
    widget = PathListWidget(model, "files", extensions=[".ptu"], select_first=True)

    seen: list[list[str]] = []
    widget.selectionChanged.connect(seen.append)

    widget.add_paths([f1, f2])
    # select_first picked row 0 and emitted it
    assert widget.selected_paths() == [str(f1)]
    assert seen and seen[-1] == [str(f1)]

    widget.select_index(1)
    assert widget.selected_paths() == [str(f2)]
    assert seen[-1] == [str(f2)]


def test_checkable_mode(qapp, tmp_path):
    """Checkable adds ticks (default checked), preserves state across refresh, All/None work."""
    from qtpy import QtCore

    fs = [tmp_path / f"f{i}.dat" for i in range(3)]
    for f in fs:
        f.write_bytes(b"x")
    model = _Model()
    w = PathListWidget(model, "files", extensions=[".dat"], checkable=True)

    seen: list[list[str]] = []
    w.checkChanged.connect(seen.append)

    w.add_paths(fs)
    assert w.checked_paths() == [str(f) for f in fs]  # default checked

    # uncheck the middle item
    w._list.item(1).setCheckState(QtCore.Qt.Unchecked)
    assert w.checked_paths() == [str(fs[0]), str(fs[2])]
    assert seen[-1] == [str(fs[0]), str(fs[2])]

    # check state survives a full-list refresh (adding a new file)
    f4 = tmp_path / "f4.dat"
    f4.write_bytes(b"x")
    w.add_paths([f4])
    assert str(fs[1]) not in w.checked_paths() and str(f4) in w.checked_paths()

    # All / None
    w._set_all_checked(False)
    assert w.checked_paths() == []
    w._set_all_checked(True)
    assert len(w.checked_paths()) == 4


def test_path_filter_overrides_extension_check(qapp, tmp_path):
    """A path_filter predicate accepts files a plain suffix test would reject (e.g. .ptu.gz)."""
    model = _Model()
    w = PathListWidget(
        model,
        "files",
        path_filter=lambda p: p.lower().endswith((".ptu", ".ptu.gz")),
    )
    assert w._accepts("/data/run.ptu") is True
    assert w._accepts("/data/run.ptu.gz") is True  # compressed — suffix is .gz
    assert w._accepts("/data/run.txt") is False


def test_replace_on_drop(qapp, tmp_path):
    """replace_on_drop makes a drop replace the list instead of appending."""
    fs = [tmp_path / f"f{i}.dat" for i in range(3)]
    for f in fs:
        f.write_bytes(b"x")
    model = _Model()
    w = PathListWidget(model, "files", extensions=[".dat"], replace_on_drop=True)
    w.add_paths([fs[0]])  # explicit add still appends
    w._on_dropped([fs[1], fs[2]])  # a drop replaces
    assert w.paths() == [str(fs[1]), str(fs[2])]


def test_allow_duplicates_keeps_repeats_and_removes_by_row(qapp, tmp_path):
    """allow_duplicates keeps the same path twice; removal drops only one occurrence."""
    a = tmp_path / "a.pdb"
    a.write_bytes(b"1")
    b = tmp_path / "b.pdb"
    b.write_bytes(b"2")
    model = _Model()
    w = PathListWidget(model, "files", extensions=[".pdb"], allow_duplicates=True)

    # a homodimer: same structure for body 0 and body 1, plus a distinct body 2
    w.add_paths([a, a, b])
    assert w.paths() == [str(a), str(a), str(b)]

    # select the *first* row and remove it -> only that occurrence goes
    w._list.setCurrentRow(0)
    w._remove_selected()
    assert w.paths() == [str(a), str(b)]


def test_allow_duplicates_rejects_checkable(qapp):
    """allow_duplicates and checkable are mutually exclusive (tick state keys on text)."""
    with pytest.raises(ValueError):
        PathListWidget(_Model(), "files", allow_duplicates=True, checkable=True)


def test_set_paths_loads_verbatim_including_missing(qapp, tmp_path):
    """set_paths stores the list exactly — no expansion, no existence filtering."""
    a = tmp_path / "a.pdb"
    a.write_bytes(b"1")
    missing = tmp_path / "gone.pdb"  # never created
    model = _Model()
    w = PathListWidget(model, "files", extensions=[".pdb"], allow_duplicates=True)

    w.set_paths([a, a, missing])
    assert w.paths() == [str(a), str(a), str(missing)]
    assert model.files == [str(a), str(a), str(missing)]


def test_rejected_paths_signal(qapp, tmp_path):
    """A path_filter rejection on drop surfaces via rejectedPaths (for host warnings)."""
    from chisurf.gui.widgets.tools.chisurf_dock_tool import PathDropListWidget

    good = tmp_path / "a.ptu"
    good.write_bytes(b"x")
    bad = tmp_path / "b.spc"
    bad.write_bytes(b"x")
    model = _Model()
    w = PathListWidget(model, "files", path_filter=lambda p: p.endswith(".ptu"))
    seen: list[list[str]] = []
    w.rejectedPaths.connect(seen.append)

    # simulate the low-level widget's split of a drop into accepted/rejected
    inner = w._list
    assert isinstance(inner, PathDropListWidget)
    inner.pathsDropped.emit([good])
    inner.pathsRejected.emit([bad])
    assert w.paths() == [str(good)]
    assert seen and seen[-1] == [str(bad)]


def test_a_list_filled_programmatically_reaches_the_widget(qapp, tmp_path):
    """``AutoForm.sync_fields()`` must re-read this section from its model.

    A workflow handing a panel the files it produced, or a restored project,
    writes the model attribute directly. Without a sync the model held the paths
    while the list on screen stayed empty — which reads as "the hand-off did not
    happen", and sent the user off to pick the files again by hand.
    """
    a = tmp_path / "m000.bur"
    a.write_bytes(b"x")
    model = _Model()
    w = PathListWidget(model, "files")
    assert w.paths() == []

    model.files = [str(a)]  # exactly what a hand-off does
    # ``paths()`` reads the model, so it is already right; the *visible* list is
    # the thing that was left behind, and it is the only thing the user sees.
    assert w._list.count() == 0, "nothing has told the widget yet"

    w.sync()
    assert w._list.count() == 1
    assert w._list.item(0).text() == str(a)


def test_the_section_advertises_itself_for_sync(qapp):
    """``sync_fields()`` only visits widgets that mark themselves refreshable."""
    model = _Model()
    w = PathListWidget(model, "files")
    assert getattr(w, "AUTOFORM_REFRESH", False) is True
    assert callable(getattr(w, "sync", None))


# -- drop guards (chisurf.gui.widgets.dropguard) -----------------------------
#
# A section names no guards by default, so every test above (all of which
# construct a plain PathListWidget) is itself a regression check that nothing
# changed for the common case. These pin the opt-in behaviour specifically.

_SPC = (
    Path(__file__).resolve().parents[2]
    / "chisurf"
    / "plugins"
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "m000.spc"
)


def test_no_guards_option_leaves_a_dropped_vendor_file_untouched(qapp, tmp_path):
    """The default: naming no guard is exactly today's behaviour."""
    sample = tmp_path / "m000.ptu"
    sample.write_bytes(b"not a real container")
    model = _Model()
    w = PathListWidget(model, "files")

    w._on_dropped([sample])

    assert model.files == [str(sample)]
    assert not sample.with_suffix(".pto").exists()


@pytest.mark.skipif(not _SPC.exists(), reason="no BH SPC test data")
def test_guards_option_converts_a_dropped_vendor_file(qapp, tmp_path, monkeypatch):
    """``guards=["tttr_to_pto"]`` runs the guard on a drop before committing."""
    from chisurf.core.fio import staging

    cfg = dict(staging.DEFAULTS)
    cfg["drop_guards"] = {"tttr_to_pto": "always_keep"}
    monkeypatch.setattr(staging, "_settings", lambda: cfg)
    monkeypatch.setattr(
        "chisurf.plugins.core.tttr_to_pto.gui.guard.set_data_loading_settings",
        lambda *a, **k: True,
    )

    sample = tmp_path / _SPC.name
    sample.write_bytes(_SPC.read_bytes())
    model = _Model()
    w = PathListWidget(model, "files", guards=["tttr_to_pto"])

    w._on_dropped([sample])

    assert model.files == [str(sample.with_suffix(".pto"))]
    assert sample.exists()  # always_keep: the source survives

"""The burst-MLE file list on the unified AutoForm path list.

Covers the migration of the bespoke ``FileListWidget`` onto the shared
``PathListWidget``: the drop-only change callback (a programmatic ``add_file``
must stay silent so the wizard's own ``load_burst_data`` is not double-called),
the checked-file accessor, drop-enable routing, and the burstwise folder
expander.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.burst.burst_mle_analysis.utils import (
    FileListWidget,
    expand_mle_folder,
)


def test_add_file_is_silent_but_drop_fires_callback(qapp, tmp_path):
    """add_file must not call back (the wizard loads explicitly); a drop must."""
    a = tmp_path / "a.spc"
    a.write_bytes(b"1")
    b = tmp_path / "b.spc"
    b.write_bytes(b"2")

    calls: list[int] = []
    fw = FileListWidget(file_added_callback=lambda: calls.append(1))

    # programmatic add: file lands in the list, callback stays silent
    fw.add_file(str(a))
    assert [str(p) for p in fw.get_selected_files()] == [str(a)]
    assert calls == []

    # a user drop commits then fires the callback exactly once
    fw._list.pathsDropped.emit([b])
    assert calls == [1]
    assert str(b) in [str(p) for p in fw.get_selected_files()]


def test_get_selected_files_tracks_check_state(qapp, tmp_path):
    """get_selected_files returns the *checked* files as Path objects, in order."""
    from qtpy import QtCore

    fs = [tmp_path / f"f{i}.spc" for i in range(3)]
    for f in fs:
        f.write_bytes(b"x")
    fw = FileListWidget()
    fw.add_file(str(fs[0]))
    fw.add_file(str(fs[1]))
    fw.add_file(str(fs[2]))
    assert fw.get_selected_files() == [Path(f) for f in fs]  # default checked

    fw._list.item(1).setCheckState(QtCore.Qt.Unchecked)
    assert fw.get_selected_files() == [Path(fs[0]), Path(fs[2])]


def test_set_accept_drops_routes_to_inner_list(qapp):
    """Toggling accept-drops routes to the inner list (per-detector drop gating)."""
    fw = FileListWidget()
    fw.setAcceptDrops(False)
    assert fw._list.acceptDrops() is False
    fw.setAcceptDrops(True)
    assert fw._list.acceptDrops() is True


def test_clear_is_silent(qapp, tmp_path):
    """A programmatic clear empties the list without firing the drop callback."""
    a = tmp_path / "a.spc"
    a.write_bytes(b"1")
    calls: list[int] = []
    fw = FileListWidget(file_added_callback=lambda: calls.append(1))
    fw.add_file(str(a))
    fw.clear()
    assert fw.get_selected_files() == []
    assert calls == []


def test_expand_mle_folder_prefers_bur(tmp_path):
    """A folder with .bur index files expands to those; otherwise to TTTR files."""
    # burstwise folder: .bur files win even if other files are present
    bur_dir = tmp_path / "bursts"
    (bur_dir / "sub").mkdir(parents=True)
    (bur_dir / "sub" / "m001.bur").write_bytes(b"x")
    (bur_dir / "sub" / "m000.bur").write_bytes(b"x")
    (bur_dir / "note.txt").write_text("ignored")
    out = expand_mle_folder(bur_dir)
    assert [Path(p).name for p in out] == ["m000.bur", "m001.bur"]  # sorted

    # no .bur -> supported TTTR extensions (a .txt is not one)
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "note.txt").write_text("ignored")
    assert expand_mle_folder(plain) == []

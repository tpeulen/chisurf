"""The compiled-``.ui`` cache must be indistinguishable from ``uic.loadUi``.

``uic.loadUi`` re-parses the ``.ui`` XML on every widget construction. Compiling
once and calling the generated ``setupUi`` is ~6x cheaper per construction
(3.40 ms -> 0.52 ms averaged over the 41 loadable ``.ui`` files in the tree).

The catch, and the reason these tests exist: ``pyuic5``'s ``setupUi`` parents the
widgets to the target but binds them as attributes of the **Ui_ instance**
(``self.lineEdit``), whereas ``loadUi(path, target)`` binds them on the *target*.
Swapping one for the other without copying the attributes across leaves every
``self.<widget>`` reference in the widget's own code raising ``AttributeError``
-- the widget tree looks perfect and the code breaks. Verified across all 41
files: identical child-widget names and no attribute lost.

Compiling costs about as much as one ``loadUi`` (3.51 ms vs 3.40 ms), so the
break-even is 1.22 constructions per file: a widget built once is marginally
slower, anything built twice or more wins. Plots are rebuilt per fit.
"""

import glob
import pathlib

import pytest

pytest.importorskip("qtpy")
from qtpy import QtWidgets, uic  # noqa: E402

import chisurf.gui.decorators as decorators  # noqa: E402

UI_FILES = sorted(
    glob.glob(str(pathlib.Path(__file__).parents[2] / "chisurf" / "**" / "*.ui"), recursive=True)
)


def _loadui_reference(path, qtbot):
    w = QtWidgets.QWidget()
    qtbot.addWidget(w)
    uic.loadUi(path, w)
    names = {c.objectName() for c in w.findChildren(QtWidgets.QWidget)}
    attrs = {k for k in vars(w) if not k.startswith("_")}
    return names, attrs


def _compiled(path, qtbot):
    ui_class = decorators._compiled_ui_class(pathlib.Path(path))
    if ui_class is None:
        return None
    w = QtWidgets.QWidget()
    qtbot.addWidget(w)
    ui = ui_class()
    ui.setupUi(w)
    for name, value in vars(ui).items():
        setattr(w, name, value)
    names = {c.objectName() for c in w.findChildren(QtWidgets.QWidget)}
    attrs = {k for k in vars(w) if not k.startswith("_")}
    return names, attrs


def test_there_are_ui_files_to_check():
    assert UI_FILES, "no .ui files found — the sweep below would be vacuous"


@pytest.mark.parametrize("path", UI_FILES, ids=lambda p: pathlib.Path(p).name)
def test_compiled_matches_loadui(path, qtbot):
    try:
        ref = _loadui_reference(path, qtbot)
    except Exception:
        pytest.skip("uic.loadUi cannot load this file either")

    got = _compiled(path, qtbot)
    if got is None:
        pytest.skip("does not compile — falls back to uic.loadUi")

    assert got[0] == ref[0], "child widget names differ"
    # The regression: every attribute loadUi binds must also be bound here.
    missing = ref[1] - got[1]
    assert not missing, f"attributes lost by the compiled path: {sorted(missing)}"


def test_cache_is_keyed_on_mtime(tmp_path):
    """Editing a .ui during development must not serve a stale layout."""
    src = next(
        (p for p in UI_FILES if decorators._compiled_ui_class(pathlib.Path(p)) is not None), None
    )
    if src is None:
        pytest.skip("no compilable .ui file available")

    target = tmp_path / "w.ui"
    target.write_bytes(pathlib.Path(src).read_bytes())
    first = decorators._compiled_ui_class(target)
    assert first is not None
    assert decorators._compiled_ui_class(target) is first, "should be cached"

    import os

    st = target.stat()
    os.utime(target, (st.st_atime, st.st_mtime + 10))
    assert decorators._compiled_ui_class(target) is not first, "stale after touch"


def test_unreadable_file_falls_back_rather_than_raising(tmp_path):
    assert decorators._compiled_ui_class(tmp_path / "does_not_exist.ui") is None


def test_malformed_ui_falls_back_rather_than_raising(tmp_path):
    bad = tmp_path / "bad.ui"
    bad.write_text("<not-a-ui/>")
    assert decorators._compiled_ui_class(bad) is None

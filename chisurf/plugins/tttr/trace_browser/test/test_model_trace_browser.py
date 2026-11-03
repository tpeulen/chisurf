"""The Qt-free Trace Browser model: scan, filter, metadata, traces, caches, hand-offs.

Everything runs on a temporary COPY of repository sample data: the browser writes
``.trace_browser_meta.json`` and a ``.tttr_trace_cache`` folder beside the data and
Delete moves files to ``.trash``, so repo data is never opened in place.
"""

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
BH132 = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
BH630 = REPO / "test" / "data" / "tttr" / "BH" / "630_256" / "BH_SPC630_256.spc"

from chisurf.plugins.tttr.trace_browser.gui.model import (  # noqa: E402
    FILTER_LABELS,
    TraceBrowserModel,
)

# Setup as the detector wizard returns it ("ALEX Suite (auto)"): detectors only matter here.
SETUP = {
    "detectors": {
        "G|G": {"chs": [1], "micro_time_ranges": [(616, 3784)]},
        "R|G": {"chs": [0], "micro_time_ranges": [(616, 3784)]},
        "R|R": {"chs": [0], "micro_time_ranges": [(4278, 7762)]},
    }
}


@pytest.fixture
def real_dir(tmp_path):
    """Temp copy of two real BH files: m000.spc, m001.spc and sub/m002.spc."""
    if not BH132.exists() or not BH630.exists():
        pytest.skip("sample TTTR data missing")
    shutil.copy(BH132, tmp_path / "m000.spc")
    shutil.copy(BH132, tmp_path / "m001.spc")
    (tmp_path / "sub").mkdir()
    shutil.copy(BH630, tmp_path / "sub" / "m002.spc")
    return tmp_path


@pytest.fixture
def fake_dir(tmp_path):
    """Temp folder of unreadable stand-in files (listed as non-image) plus metadata."""
    for rel in [
        "a.ptu",
        "b.PTU",
        "c.spc",
        "d.txt",
        "sub/e.ht3",
        "sub/.trash/f.ptu",
        ".trash/g.ptu",
        "deep/x/y.pt3",
        "h.h5",
    ]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"not a real tttr file")
    (tmp_path / ".trace_browser_meta.json").write_text(
        json.dumps(
            {
                "a.ptu": {"rating": 3, "annotation": "hello"},
                "sub/e.ht3": {"rating": 1},
                "c.spc": {"rating": 0},
                "b.PTU": {"rating": 2},
                "deep/x/y.pt3": {"rating": 2},
            }
        )
    )
    return tmp_path


def _names(rows):
    return sorted((r["name"], r["rating"]) for r in rows)


#: (name, rating) of the photon files in ``fake_dir`` (``d.txt`` and ``.trash`` are never listed).
FAKE_RATINGS = {
    "a.ptu": 3,
    "b.PTU": 2,
    "c.spc": 0,
    "sub/e.ht3": 1,
    "deep/x/y.pt3": 2,
    "h.h5": 0,
}
#: The rating filters in FILTER_LABELS order: All, >= 1, >= 2, >= 3, only 0.
KEEPS = (
    lambda r: True,
    lambda r: r >= 1,
    lambda r: r >= 2,
    lambda r: r >= 3,
    lambda r: r == 0,
)


def expected_rows(recursive, idx):
    """The rows a scan must show: top level only unless recursive, then the filter's ratings."""
    return sorted(
        (name, rating)
        for name, rating in FAKE_RATINGS.items()
        if (recursive or "/" not in name) and KEEPS[idx](rating)
    )


@pytest.mark.parametrize("recursive", [False, True])
@pytest.mark.parametrize("idx", range(5))
def test_scan_and_filter_list_the_rated_photon_files(fake_dir, recursive, idx):
    m = TraceBrowserModel()
    m.include_subfolders = recursive
    m.filter_index = idx
    assert m.open_folder(fake_dir)
    assert _names(m.rows) == expected_rows(recursive, idx)
    # .trash content is never listed
    assert not any(".trash" in r["path"] for r in m.files)


def test_notes_and_rows_carry_metadata(fake_dir):
    m = TraceBrowserModel()
    m.open_folder(fake_dir)
    row = next(r for r in m.rows if r["name"] == "a.ptu")
    assert (row["rating"], row["notes"], row["size"]) == (3, "hello", 20)
    assert row["size_text"] == "0.0 MB"


def test_filter_relaxes_from_all_scanned_files(fake_dir):
    m = TraceBrowserModel()
    m.filter_index = 3
    m.open_folder(fake_dir)
    assert [r["name"] for r in m.rows] == ["a.ptu"]
    m.set_rating_filter(FILTER_LABELS[0])
    assert len(m.rows) == 4 and m.rating_filter == "All"


@pytest.mark.parametrize(
    "filetype, expected",
    [
        ("PTU", [".ptu"]),
        ("HT3", [".ht3"]),
        ("SPC-130", [".spc"]),
        ("PHOTON_HDF5", [".h5", ".hdf5"]),
    ],
)
def test_setup_filetype_restricts_extensions(filetype, expected):
    # A container type lists the extensions of its own files only.
    m = TraceBrowserModel()
    m.setup_filetype = filetype
    assert sorted(m.allowed_exts()) == expected
    m.setup_filetype = "Auto"
    assert {".ptu", ".spc"} <= m.allowed_exts()


def test_apply_setup_selects_the_union_of_channels():
    m = TraceBrowserModel()
    m.apply_setup(SETUP)
    assert m.selected_channels == [0, 1]
    m.apply_setup({"detectors": {}})
    assert m.selected_channels is None


def test_api_list_files_is_not_the_model_scan(fake_dir):
    """``api.io.list_files`` lists differently, so the model scans the folder itself."""
    from chisurf.plugins.tttr.trace_browser.api.io import list_files

    api_names = sorted(r["name"] for r in list_files(str(fake_dir)))
    m = TraceBrowserModel()
    m.open_folder(fake_dir)
    model_names = sorted(r["name"] for r in m.rows)
    # api: fixed extension set without .spc/.h5; model: every extension tttrlib reads
    assert api_names == ["a.ptu", "b.PTU"]
    assert model_names == ["a.ptu", "b.PTU", "c.spc", "h.h5"]
    # api lists inside .trash when recursive, the model never does
    rec = sorted(r["path"] for r in list_files(str(fake_dir), recursive=True))
    assert any(".trash" in p for p in rec)


def test_rating_and_notes_round_trip_through_metadata(fake_dir):
    m = TraceBrowserModel()
    m.open_folder(fake_dir)
    path = fake_dir / "c.spc"
    m.set_rating(path, 5)
    m.set_notes(path, "keep this one")
    assert (m.get_rating(path), m.get_notes(path)) == (5, "keep this one")
    on_disk = json.loads((fake_dir / ".trace_browser_meta.json").read_text())
    assert on_disk["c.spc"] == {"rating": 5, "annotation": "keep this one"}
    fresh = TraceBrowserModel()
    fresh.open_folder(fake_dir)
    row = next(r for r in fresh.rows if r["name"] == "c.spc")
    assert (row["rating"], row["notes"]) == (5, "keep this one")
    # a subfolder file is keyed by its relative path
    m.include_subfolders = True
    m.scan()
    m.set_rating(fake_dir / "sub" / "e.ht3", 4)
    assert (
        json.loads((fake_dir / ".trace_browser_meta.json").read_text())["sub/e.ht3"]["rating"] == 4
    )


def test_rating_change_refilters_rows(fake_dir):
    m = TraceBrowserModel()
    m.filter_index = 3
    m.open_folder(fake_dir)
    m.set_rating(fake_dir / "a.ptu", 1)
    assert m.rows == []
    m.set_rating(fake_dir / "c.spc", 3)
    assert [r["name"] for r in m.rows] == ["c.spc"]


def test_clear_keeps_files_and_metadata(fake_dir):
    m = TraceBrowserModel()
    m.open_folder(fake_dir)
    m.set_selection([fake_dir / "a.ptu"])
    m.clear()
    assert m.rows == [] and m.files == [] and m.selected_files == []
    assert (fake_dir / "a.ptu").exists() and (fake_dir / ".trace_browser_meta.json").exists()


def test_clear_caches_removes_memory_and_disk_cache(fake_dir):
    m = TraceBrowserModel()
    m.open_folder(fake_dir)
    cache = fake_dir / ".tttr_trace_cache"
    cache.mkdir()
    (cache / "x.npz").write_bytes(b"x")
    m._trace_mem_cache[(fake_dir / "a.ptu", "sig")] = (1, 2, [])
    m._is_image_cache[fake_dir / "a.ptu"] = False
    assert m.clear_caches() == 1
    assert not cache.exists() and not m._trace_mem_cache and not m._is_image_cache
    assert m.clear_caches() == 0


def test_selection_and_y_range(fake_dir):
    m = TraceBrowserModel()
    m.open_folder(fake_dir)
    m.set_selection([fake_dir / "a.ptu", fake_dir / "nope.ptu"])
    assert m.selected_files == [str(fake_dir / "a.ptu")]
    assert m.first_selected() == fake_dir / "a.ptu"
    m.y_min, m.y_max = 500.0, 100.0
    assert m.y_range == (100.0, 500.0)


def test_open_folder_rejects_a_file(fake_dir):
    m = TraceBrowserModel()
    assert not m.open_folder(fake_dir / "a.ptu")
    assert "Not a folder" in m.error_text


def test_observers_are_notified(fake_dir):
    m = TraceBrowserModel()
    events = []
    m.add_observer(events.append)
    m.open_folder(fake_dir)
    assert "files" in events and "rows" in events


# ---- traces (computed by the Qt-free binner, core.binning) -----------------------------
def test_the_trace_is_each_detectors_gated_photons_per_window(real_dir):
    """Against the trace's definition computed from the file (``conftest.expected_trace``)."""
    import numpy as np

    from chisurf.plugins.tttr.trace_browser.test.conftest import expected_trace

    m = TraceBrowserModel()
    m.image_probe = lambda p: False
    m.apply_setup(SETUP)
    m.open_folder(real_dir)
    for ms in (10.0, 1.0):
        ta, pad, labels = m.compute_trace_cached(real_dir / "m000.spc", ms)
        want_t, want = expected_trace(real_dir / "m000.spc", SETUP, ms / 1000.0)
        assert labels == list(SETUP["detectors"])
        np.testing.assert_array_equal(pad, want)
        np.testing.assert_allclose(ta, want_t)


def test_load_trace_uses_and_fills_the_disk_cache(real_dir):
    m = TraceBrowserModel()
    m.image_probe = lambda p: False
    m.apply_setup(SETUP)
    m.open_folder(real_dir)
    f = real_dir / "m000.spc"
    assert m.load_trace_cache(f, 10.0) is None
    assert m.show_file(f)
    assert m.current_file == f and m.trace["counts"].shape == (6233, 3)
    cached = m.load_trace_cache(f, 10.0)
    assert cached is not None and cached[1].shape == (6233, 3)
    assert list((real_dir / ".tttr_trace_cache").glob("m000_*.npz"))
    # the signature separates bin windows and files
    assert m.trace_signature(f, 0.25) != m.trace_signature(f, 0.75)
    assert m.trace_signature(f, 10.0) == m.trace_signature(f, 10.0)


def test_precompute_all_traces_reports_progress(real_dir):
    m = TraceBrowserModel()
    m.image_probe = lambda p: False
    m.apply_setup(SETUP)
    m.open_folder(real_dir)
    steps = []
    n = m.precompute_all_traces(lambda i, total, p: steps.append((i, total, p and p.name)))
    assert n == 1 or n == 2  # m000 and m001 are identical files but cached separately
    assert steps[-1][2] is None
    assert m.precompute_all_traces() == 0  # everything cached now


def test_trace_job_runs_on_a_snapshot(real_dir):
    """Heavy methods run inside SnapshotJob and the result is copied back.

    The trace is not cached: the Qt-free binner (``core.binning``) computes it on the
    worker thread.
    """
    import time

    from chisurf.emtk.jobs import SnapshotJob

    m = TraceBrowserModel()
    m.image_probe = lambda p: False
    m.apply_setup(SETUP)
    m.open_folder(real_dir)
    assert m.load_trace_cache(real_dir / "m000.spc", 10.0) is None  # nothing cached
    m.files, m.rows, m.selected_files = [], [], []
    job = SnapshotJob(m)
    assert job.start("scan")
    for _ in range(600):
        if job.poll() or not job.busy:
            break
        time.sleep(0.05)
    assert job.error == "" and len(m.rows) == 2
    assert job.start("show_file", str(real_dir / "m000.spc"))
    for _ in range(600):
        if job.poll() or not job.busy:
            break
        time.sleep(0.05)
    assert job.error == "" and m.current_file == real_dir / "m000.spc"
    assert m.trace["counts"].shape == (6233, 3)


# ---- listing, persistence, probing ---------------------------------------------------------------
def test_the_model_lists_the_rated_photon_files_for_every_filter(fake_dir):
    m = TraceBrowserModel()
    for recursive in (False, True):
        for idx in range(5):
            m.include_subfolders, m.filter_index = recursive, idx
            m.open_folder(fake_dir)
            assert _names(m.rows) == expected_rows(recursive, idx)
    assert m.current_folder == fake_dir
    # the setup file type drives the extensions
    m.setup_filetype = "PTU"
    assert m.allowed_exts() == {".ptu"}


def test_rating_and_notes_persist_through_the_model(fake_dir):
    """A rating set and flushed is read back by a new model on the same folder."""
    w = TraceBrowserModel()
    w.open_folder(fake_dir)
    w.set_rating(fake_dir / "c.spc", 4)
    w.flush_meta()
    m = TraceBrowserModel()
    m.open_folder(fake_dir)
    assert m.get_rating(fake_dir / "c.spc") == 4


def test_the_default_image_probe_says_no_image(real_dir, fake_dir):
    """The sample point measurement and an unreadable stand-in file are not images."""
    m = TraceBrowserModel()
    for p in (real_dir / "m000.spc", fake_dir / "a.ptu"):
        assert m.probe_image(p) is False


def test_fractional_bin_widths_have_distinct_cache_signatures():
    """0.25 and 0.75 ms must not collapse to one cache signature (no integer truncation)."""
    m = TraceBrowserModel()
    p = pathlib.Path(__file__)
    assert m.trace_signature(p, 0.25) != m.trace_signature(p, 0.75)
    # and the form takes them: >= 3 decimals and a minimum below 1 ms
    spec = json.loads((HERE.parent / "gui" / "trace_browser_emtk.view.json").read_text())

    def find(node):
        if isinstance(node, dict):
            if node.get("attr") == "window_ms":
                return node
            node = list(node.values())
        for child in node if isinstance(node, list) else []:
            found = find(child)
            if found:
                return found

    field = find(spec)
    assert field["minimum"] < 1.0 and field["decimals"] >= 3


# ---- the import surface and Qt-freedom -----------------------------------------------------------
def test_import_paths_resolve_and_the_qt_workspace_is_gone():
    import chisurf.plugins.tttr.trace_browser as pkg
    from chisurf.plugins.tttr.trace_browser import (  # noqa: F401
        META_FILENAME,
        get_tttr_supported_exts,
    )

    assert META_FILENAME == ".trace_browser_meta.json"
    assert pkg.name == "Spectroscopy:Single-Molecule:Trace Browser"
    assert pkg.cli_entrypoint.startswith("trace-browser=")
    for gone in ("TraceBrowser", "StarCombo", "StarRatingWidget", "NoHoverSelectTable"):
        with pytest.raises(AttributeError):
            getattr(pkg, gone)
    with pytest.raises(AttributeError):
        pkg.does_not_exist


def test_model_module_is_qt_free():
    script = """
import importlib.abc, sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel
m = TraceBrowserModel(); m.client
bad = sorted(x for x in sys.modules if x == 'chisurf.gui' or x.startswith('chisurf.gui.'))
assert not bad, bad[:5]
print('QT-FREE OK')
"""
    import os

    env = dict(
        os.environ, PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")])
    )
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0 and "QT-FREE OK" in done.stdout, done.stdout + done.stderr[-1500:]


def test_a_single_molecule_file_is_not_an_image_and_a_scan_is():
    """tttrlib builds a CLSMImage from any TTTR; only a non-empty pixel stack is an image.

    With the old ``is not None`` test every readable TTTR was classed as an image and hidden,
    so the browser listed no file at all (tttrlib 0.27.0).
    """
    import pathlib

    pytest.importorskip("tttrlib")
    root = pathlib.Path(__file__).resolve().parents[5] / "test" / "data"
    molecule = root / "tttr" / "BH" / "132" / "BH_SPC132.spc"
    scan = root / "clsm" / "Leica_SP8.ptu"
    if not (molecule.exists() and scan.exists()):
        pytest.skip("sample files missing")
    model = TraceBrowserModel()
    assert model.probe_image(molecule) is False
    assert model.probe_image(scan) is True


def test_the_scan_lists_a_real_single_molecule_file_and_hides_a_scan(tmp_path):
    import pathlib
    import shutil

    pytest.importorskip("tttrlib")
    root = pathlib.Path(__file__).resolve().parents[5] / "test" / "data"
    molecule = root / "tttr" / "BH" / "132" / "BH_SPC132.spc"
    scan = root / "clsm" / "Leica_SP8.ptu"
    if not (molecule.exists() and scan.exists()):
        pytest.skip("sample files missing")
    shutil.copy(molecule, tmp_path / molecule.name)  # a temp copy: the browser writes beside files
    shutil.copy(scan, tmp_path / scan.name)
    model = TraceBrowserModel()
    model.open_folder(tmp_path)
    assert [r["name"] for r in model.rows] == [molecule.name]

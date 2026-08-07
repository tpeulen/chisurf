"""The PDA burst-slice resolvers, which had no test when they used pandas.

Both of them answer one question — *which photons of which TTTR file does this
``.bur`` say a burst is* — and both were a frame pipeline
(``dropna``/``.loc``/``groupby``) inside a GUI method, so neither could be
exercised without a window. The shared reader is a plain function now, and this
pins it against the pandas expression it replaced, on real burst tables.
"""

from __future__ import annotations

import glob
import pathlib

import numpy as np
import pytest

BUR_FILES = sorted(glob.glob("modules/ndxplorer/test/mfd/**/*.bur", recursive=True))
pytestmark = pytest.mark.skipif(not BUR_FILES, reason="no .bur fixtures available")


def _reference(path):
    """What the frame pipeline computed, expressed directly."""
    import pandas as pd

    frame = pd.read_csv(path, sep="\t")
    names = {c.lower(): c for c in frame.columns}
    first = frame[names["first file"]].astype(str).str.strip()
    last = frame[names["last file"]].astype(str).str.strip()
    keep = (first == last) & (first != "")
    return (
        first[keep].to_numpy(dtype=object),
        frame.loc[keep, names["first photon"]].astype(float).astype("int64").to_numpy(),
        frame.loc[keep, names["last photon"]].astype(float).astype("int64").to_numpy() + 1,
    )


@pytest.mark.parametrize("path", BUR_FILES[:8])
def test_the_reader_matches_the_frame_pipeline_it_replaced(path):
    from chisurf.gui.widgets.experiments.pda2c.controller import read_bur_bursts

    names, starts, stops = read_bur_bursts(pathlib.Path(path))
    ref_names, ref_starts, ref_stops = _reference(path)
    np.testing.assert_array_equal(names, ref_names)
    np.testing.assert_array_equal(starts, ref_starts)
    np.testing.assert_array_equal(stops, ref_stops)


def test_last_photon_is_inclusive_in_the_format_and_exclusive_in_the_slice(tmp_path):
    """The off-by-one the format invites: a .bur names the last photon, a slice
    names the one after it."""
    from chisurf.gui.widgets.experiments.pda2c.controller import read_bur_bursts

    path = tmp_path / "t.bur"
    path.write_text(
        "First Photon\tLast Photon\tFirst File\tLast File\n"
        "10\t19\tm000.spc\tm000.spc\n"
    )
    _, starts, stops = read_bur_bursts(path)
    assert (int(starts[0]), int(stops[0])) == (10, 20)


def test_a_burst_spanning_two_measurements_is_dropped(tmp_path):
    """It has no single photon stream to slice, so there is no right answer --
    and taking First File would silently attribute the other file's photons."""
    from chisurf.gui.widgets.experiments.pda2c.controller import read_bur_bursts

    path = tmp_path / "t.bur"
    path.write_text(
        "First Photon\tLast Photon\tFirst File\tLast File\n"
        "0\t9\tm000.spc\tm000.spc\n"
        "10\t19\tm000.spc\tm001.spc\n"
    )
    names, starts, _ = read_bur_bursts(path)
    assert list(names) == ["m000.spc"] and list(starts) == [0]


def test_the_header_capitalisation_is_not_fixed(tmp_path):
    """Different programs write this format with different casing."""
    from chisurf.gui.widgets.experiments.pda2c.controller import read_bur_bursts

    path = tmp_path / "t.bur"
    path.write_text(
        "FIRST PHOTON\tlast photon\tFirst File\tLAST FILE\n"
        "3\t7\ta.spc\ta.spc\n"
    )
    names, starts, stops = read_bur_bursts(path)
    assert (list(names), int(starts[0]), int(stops[0])) == (["a.spc"], 3, 8)


def test_a_file_without_the_four_columns_declines(tmp_path):
    """None, not an exception and not an empty answer that reads as "no bursts"."""
    from chisurf.gui.widgets.experiments.pda2c.controller import read_bur_bursts

    path = tmp_path / "t.bur"
    path.write_text("a\tb\n1\t2\n")
    assert read_bur_bursts(path) is None


def _analysis_folder(tmp_path, bur_name, rows):
    """Build a minimal MFD layout: TTTR files beside a ``bi4_bur`` folder."""
    bur_dir = tmp_path / "bi4_bur"
    bur_dir.mkdir(parents=True, exist_ok=True)
    header = "First Photon\tLast Photon\tFirst File\tLast File\n"
    body = "".join(f"{a}\t{b}\t{f}\t{f}\n" for a, b, f in rows)
    (bur_dir / bur_name).write_text(header + body)
    for name in {f for _, _, f in rows}:
        (tmp_path / name).write_bytes(b"\x00" * 8)
    return bur_dir / bur_name


def _resolver():
    """The resolver, unbound from its widget — it needs two attributes."""
    import types

    from chisurf.gui.widgets.experiments.pda2c.controller import Pda2cTTTRWidget

    stub = types.SimpleNamespace(_tttr_exts=(".spc", ".ptu", ".ht3"))
    stub._merge_intervals = lambda m: Pda2cTTTRWidget._merge_intervals(stub, m)
    return lambda burs: Pda2cTTTRWidget._resolve_tttr_and_slices_from_bur(stub, burs)


def test_one_bur_naming_one_file_resolves_by_stem(tmp_path):
    bur = _analysis_folder(tmp_path, "m000.bur", [(0, 9, "m000.spc"), (20, 29, "m000.spc")])
    files, slices = _resolver()([str(bur)])
    assert [pathlib.Path(f).name for f in files] == ["m000.spc"]
    assert list(slices.values()) == [[(0, 10), (20, 30)]]


def test_a_bur_naming_two_files_groups_each_ones_bursts(tmp_path):
    """The path the frame pipeline used ``groupby`` for. A .bur that references
    more than one measurement has to send each burst to the right stream — the
    one thing this resolver exists to get right."""
    bur = _analysis_folder(
        tmp_path,
        "mixed.bur",
        [(0, 9, "a.spc"), (5, 14, "b.spc"), (100, 109, "a.spc")],
    )
    _, slices = _resolver()([str(bur)])
    by_name = {pathlib.Path(k).name: v for k, v in slices.items()}
    assert by_name == {"a.spc": [(0, 10), (100, 110)], "b.spc": [(5, 15)]}


def test_a_bur_whose_files_are_absent_resolves_to_nothing(tmp_path):
    """Declining is right, and it must not raise: a folder can legitimately hold
    burst tables whose measurements live elsewhere."""
    bur_dir = tmp_path / "bi4_bur"
    bur_dir.mkdir(parents=True)
    (bur_dir / "x.bur").write_text(
        "First Photon\tLast Photon\tFirst File\tLast File\n0\t9\tgone.spc\tgone.spc\n"
    )
    files, slices = _resolver()([str(bur_dir / "x.bur")])
    assert files == [] and slices == {}

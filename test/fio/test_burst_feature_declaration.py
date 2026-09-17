"""The declared .bur schema reproduces the hardcoded one it replaced.

`generate_burst_dataframe` used to spell its column set twice in code
(header list + positional filler); it now iterates
`burst_features.yaml` (the general rule: analysis I/O and computed
features are declared in settings, never hardcoded). The .bur layout is a
*format* -- merged column-wise, header names parsed back by the MFD reader
and ndxplorer -- so the declaration-driven table must equal the hardcoded
one **cell for cell**, sentinels, blank column, interleaved zeros and all.
The pre-declaration builder is transcribed below whole as the frozen
reference.
"""

import numpy as np

from chisurf.core.datastore import column_names, numeric_column, row_count
from chisurf.core.fio.fluorescence.burst import (
    _micro_time_mask,
    burst_feature_declaration,
    generate_burst_dataframe,
    mean_micro_time_ns,
    micro_time_resolution_ns,
)


class _Header:
    macro_time_resolution = 1e-7
    micro_time_resolution = 1e-11


class _Tttr:
    """The five attributes `generate_burst_dataframe` reads, synthetic."""

    def __init__(self, n=4000, seed=2):
        rng = np.random.default_rng(seed)
        self.macro_times = np.cumsum(rng.integers(1, 50, n)).astype(np.uint64)
        self.micro_times = rng.integers(0, 4096, n).astype(np.uint16)
        self.routing_channel = rng.choice([0, 2], size=n).astype(np.int8)
        self.header = _Header()

    def __len__(self):
        return len(self.macro_times)


DETECTORS = {
    "green": {"chs": [0], "micro_time_ranges": [(0, 2048)]},
    "red": {"chs": [2], "micro_time_ranges": []},
}
WINDOWS = {"prompt": (0, 2000), "delay": (2000, 4096)}


def _reference_dataframe_cells(start_stop, filename, tttr, windows, detectors):
    """The pre-declaration builder, transcribed whole (columns + rows), plus the
    one addition made since: each PIE window x detector stream's photon count
    beside its rate (0 for an empty stream).
    """
    import pathlib

    file_name_only = pathlib.Path(filename).name
    macro, micro, rout = (tttr.macro_times, tttr.micro_times, tttr.routing_channel)
    res = tttr.header.macro_time_resolution
    n_ph = len(tttr)

    static_cols = [
        "First Photon",
        "Last Photon",
        "Duration (ms)",
        "Mean Macro Time (ms)",
        "Number of Photons",
        "Count Rate (KHz)",
        "Confidence (sigma)",
        "First File",
        "Last File",
    ]
    det_cols = []
    for d in detectors:
        det_cols += [
            f"First Photon ({d})",
            f"Last Photon ({d})",
            f"Duration ({d}) (ms)",
            f"Mean Macrotime ({d}) (ms)",
            f"Number of Photons ({d})",
            f"{d.capitalize()} Count Rate (KHz)",
        ]
    win_cols = []
    for w, (r0, r1) in windows.items():
        for d in detectors:
            win_cols.append(f"S {w} {d} (kHz) | {r0}-{r1}")
            win_cols.append(f"S {w} {d} (photons) | {r0}-{r1}")
    micro_cols = [f"Mean Microtime ({d}) (ns)" for d in detectors]
    micro_ns = micro_time_resolution_ns(tttr)
    cols = static_cols + det_cols + win_cols + micro_cols + [""]

    idx = {c: i for i, c in enumerate(cols)}
    det_global = {
        d: np.isin(rout, info["chs"]) & _micro_time_mask(micro, info["micro_time_ranges"])
        for d, info in detectors.items()
    }
    win_global = {w: (micro >= r0) & (micro < r1) for w, (r0, r1) in windows.items()}
    zero_row = [0] * len(cols)
    zero_row[-1] = ""
    out = [zero_row.copy()] if len(start_stop) else []
    for burst_index, (start, stop) in enumerate(start_stop):
        if stop <= start or stop >= n_ph or start < 0:
            continue
        row = zero_row.copy()
        dur = (macro[stop] - macro[start]) * res * 1e3
        npix = stop - start + 1
        row[idx["First Photon"]] = start
        row[idx["Last Photon"]] = stop
        row[idx["Duration (ms)"]] = dur
        row[idx["Mean Macro Time (ms)"]] = ((macro[stop] + macro[start]) / 2) * res * 1e3
        row[idx["Number of Photons"]] = npix
        row[idx["Count Rate (KHz)"]] = (npix / dur) if dur > 0 else np.nan
        row[idx["First File"]] = file_name_only
        row[idx["Last File"]] = file_name_only
        sl = slice(start, stop + 1)
        micro_sl = micro[sl]
        for d in detectors:
            idxs = np.nonzero(det_global[d][sl])[0]
            row[idx[f"Mean Microtime ({d}) (ns)"]] = mean_micro_time_ns(micro_sl, idxs, micro_ns)
            if idxs.size == 0:
                row[idx[f"First Photon ({d})"]] = -1
                row[idx[f"Last Photon ({d})"]] = -1
                row[idx[f"Duration ({d}) (ms)"]] = -1.0
                row[idx[f"Mean Macrotime ({d}) (ms)"]] = -1.0
                row[idx[f"Number of Photons ({d})"]] = 0
                row[idx[f"{d.capitalize()} Count Rate (KHz)"]] = -1.0
            else:
                abs0, abs1 = start + idxs[0], start + idxs[-1]
                d_ms = (macro[abs1] - macro[abs0]) * res * 1e3
                row[idx[f"First Photon ({d})"]] = abs0
                row[idx[f"Last Photon ({d})"]] = abs1
                row[idx[f"Duration ({d}) (ms)"]] = d_ms
                row[idx[f"Mean Macrotime ({d}) (ms)"]] = (
                    ((macro[abs1] + macro[abs0]) / 2) * res * 1e3
                )
                row[idx[f"Number of Photons ({d})"]] = idxs.size
                row[idx[f"{d.capitalize()} Count Rate (KHz)"]] = (
                    (idxs.size / d_ms) if d_ms > 0 else np.nan
                )
        for w in windows:
            for d in detectors:
                idxs = np.nonzero(det_global[d][sl] & win_global[w][sl])[0]
                key = f"S {w} {d} (kHz) | {windows[w][0]}-{windows[w][1]}"
                row[idx[f"S {w} {d} (photons) | {windows[w][0]}-{windows[w][1]}"]] = idxs.size
                if idxs.size == 0:
                    row[idx[key]] = -1.0
                else:
                    abs0, abs1 = start + idxs[0], start + idxs[-1]
                    d_ms = (macro[abs1] - macro[abs0]) * res * 1e3
                    row[idx[key]] = (idxs.size / d_ms) if d_ms > 0 else np.nan
        out.append(row)
        out.append(zero_row.copy())
    return cols, out


def _bursts(tttr):
    # A mix: ordinary bursts, a one-sided detector burst, an all-red span,
    # and out-of-range pairs the filler must skip.
    return [(10, 60), (100, 101), (200, 350), (500, 4001), (-2, 5), (700, 700), (800, 950)]


def test_declared_schema_equals_the_hardcoded_one_cell_for_cell():
    tttr = _Tttr()
    got = generate_burst_dataframe(_bursts(tttr), "m000.spc", tttr, WINDOWS, DETECTORS)
    want_cols, want_rows = _reference_dataframe_cells(
        _bursts(tttr), "m000.spc", tttr, WINDOWS, DETECTORS
    )

    assert list(column_names(got)) == want_cols
    assert row_count(got) == len(want_rows)
    want = list(zip(*want_rows))  # to columns
    for j, name in enumerate(want_cols):
        if name in ("First File", "Last File", ""):
            continue  # string columns: compared via the header set
        col = numeric_column(got, name if name else j)
        np.testing.assert_allclose(
            np.asarray(col, dtype=float),
            np.asarray(want[j], dtype=float),
            rtol=0,
            atol=0,
            err_msg=f"column {name!r} moved under the declaration",
        )


def test_a_dropped_column_actually_drops(monkeypatch, tmp_path):
    """The point of the declaration: schema drift without a code change."""
    import chisurf.core.fio.fluorescence.burst as B

    decl = {
        "groups": [
            {
                "scope": "static",
                "columns": [
                    {"column": "First Photon", "source": "first_photon"},
                    {"column": "Photons", "source": "n_photons"},
                ],
            },
            {
                "scope": "detector",
                "columns": [
                    {"column": "N ({detector})", "source": "n_photons"},
                ],
            },
        ],
        "trailing_blank": False,
    }
    monkeypatch.setattr(B, "_BURST_FEATURES_DECLARATION", decl)
    tttr = _Tttr()
    got = generate_burst_dataframe(
        [(10, 60)], "m.spc", tttr, WINDOWS, DETECTORS, include_interleaved_zeros=False
    )
    assert list(column_names(got)) == ["First Photon", "Photons", "N (green)", "N (red)"]
    assert int(numeric_column(got, "Photons")[0]) == 51


def test_the_shipped_declaration_is_well_formed():
    decl = burst_feature_declaration()
    assert decl["trailing_blank"] is True
    scopes = [g["scope"] for g in decl["groups"]]
    assert scopes == ["static", "detector", "window_detector", "detector"]
    for g in decl["groups"]:
        for e in g["columns"]:
            assert set(e) == {"column", "source", "term"}

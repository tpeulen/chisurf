"""Regenerate the synthetic legacy burstwise sample the plugin tests read.

The tests used to read a pulled copy of a real Paris/SoftCorr analysis folder
(87 stems) from an agent scratch cache that prunes itself; when it went, every
end-to-end test skipped. This writes a small, deterministic stand-in with the
same layout and the legacy file contract the importer parses:

- ``bi4_bur/<stem>_0.bur``, ``bg4/<stem>_0.bg4``, ``br4/<stem>_0.br4``: tab
  separated, trailing-tab header, a zero filler row before every data row,
  ``First File``/``Last File`` string columns in the burst table;
- ``BIDs/<stem>_0.ht3.bst``: photon start/stop index per burst;
- ``Info/Paris_info.txt``: ``section<TAB>key:<TAB>value`` lines;
- ``<name>.mti``: original TTTR path (Windows share) and duration in seconds.

Column names are the legacy spellings, including the irregular ones the
renamer must map (``Mean Macrotime (ms)``, double spaces).

Run ``python chisurf/plugins/burst/burstwise_import/tests/data/make_burstwise_sample.py``
from the repository root; the output is byte-identical across runs.
"""

from __future__ import annotations

import pathlib

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SAMPLE = HERE / "burstwise" / "burstwise_All 0.1066#60"
STEMS = [f"Split_44_132_75murea_sm-{i:04d}" for i in range(3)]
N_BURSTS = (6, 5, 7)

BUR_COLUMNS = [
    "First Photon", "Last Photon", "Duration (ms)", "Mean Macrotime (ms)",
    "Number of Photons", "Number of Photons (green)", "Number of Photons (red)",
    "Count Rate (KHz)", "Green Count Rate (KHz)", "Red Count Rate (KHz)",
    "Proximity Ratio", "First File", "Last File",
]
BG4_COLUMNS = [
    "Tau (green)", "2I*  (green)", "gamma (green)", "r0 (green)", "rho (green)",
    "MLE Fitted (green)", "r Scatter (green)", "r Experimental (green)",
]
BR4_COLUMNS = [c.replace("green", "red") for c in BG4_COLUMNS]


def _fmt(value) -> str:
    """Format one cell the way the legacy writer did (plain decimal)."""
    if isinstance(value, str):
        return value
    return f"{value:.6g}"


def _write_table(path: pathlib.Path, columns: list[str], rows: list[list]) -> None:
    """Write a zero-interleaved legacy table with a trailing-tab header."""
    lines = ["\t".join(columns) + "\t"]
    for row in rows:
        zero = ["" if isinstance(v, str) else "0" for v in row]
        lines.append("\t".join(zero) + "\t")
        lines.append("\t".join(_fmt(v) for v in row) + "\t")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    """Write the sample under ``burstwise/burstwise_All 0.1066#60``."""
    rng = np.random.default_rng(20261020)
    mti_lines = []
    for stem, n in zip(STEMS, N_BURSTS):
        raw = f"{stem}.ht3"
        start = np.sort(rng.integers(0, 2_000_000, n))
        n_g = rng.integers(40, 120, n)
        n_r = rng.integers(20, 80, n)
        n_ph = n_g + n_r
        dur = rng.uniform(0.5, 3.0, n)
        bur, bg4, br4, bst = [], [], [], []
        for i in range(n):
            first, last = int(start[i]), int(start[i] + n_ph[i] - 1)
            bur.append([
                first, last, dur[i], first * 1.25e-5 + dur[i] / 2,
                int(n_ph[i]), int(n_g[i]), int(n_r[i]),
                n_ph[i] / dur[i], n_g[i] / dur[i], n_r[i] / dur[i],
                n_r[i] / n_ph[i], raw, raw,
            ])
            for table, tau in ((bg4, rng.uniform(1.5, 4.0)), (br4, rng.uniform(0.8, 3.5))):
                table.append([
                    tau, rng.uniform(0.5, 3.0), rng.uniform(0.0, 0.1),
                    0.38, rng.uniform(0.5, 3.0), 1,
                    rng.uniform(0.0, 0.05), rng.uniform(0.0, 0.4),
                ])
            bst.append(f"{first}\t{last}")
        _write_table(SAMPLE / "bi4_bur" / f"{stem}_0.bur", BUR_COLUMNS, bur)
        _write_table(SAMPLE / "bg4" / f"{stem}_0.bg4", BG4_COLUMNS, bg4)
        _write_table(SAMPLE / "br4" / f"{stem}_0.br4", BR4_COLUMNS, br4)
        (SAMPLE / "BIDs").mkdir(parents=True, exist_ok=True)
        (SAMPLE / "BIDs" / f"{stem}_0.ht3.bst").write_text("\n".join(bst) + "\n")
        mti_lines.append(f"N:\\Singlem\\exp\\{raw}\t{rng.uniform(20, 40):.4f}")
    (SAMPLE / "Split_44_132_75murea_sm.mti").write_text("\n".join(mti_lines) + "\n")
    info = [
        "Burst search\tThreshold:\t0.1066",
        "Burst search\tMinimum photons:\t60",
        "Burst search\tSelection:\tAll",
        "Channels\tGreen:\t0,8",
        "Channels\tRed:\t1,9",
        "TAC\tTAC range (ns):\t50",
    ]
    (SAMPLE / "Info").mkdir(parents=True, exist_ok=True)
    (SAMPLE / "Info" / "Paris_info.txt").write_text("\n".join(info) + "\n")


if __name__ == "__main__":
    main()

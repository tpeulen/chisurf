"""A burstwise folder with a known content, for the browser's tests and captures.

``<root>/bi4_bur/m000.bur`` and ``m001.bur`` (zero-interleaved, as the burst reader
expects), 150 bursts each: a low-FRET population (E ≈ 0.25, S ≈ 0.5), a high-FRET one
(E ≈ 0.75, S ≈ 0.5) and donor-only bursts (E ≈ 0.02, S ≈ 0.95), in a fixed ratio of
2 : 2 : 1, with per-colour photon counts and a duration.
"""

from __future__ import annotations

import pathlib

import numpy as np

COLUMNS = [
    "First Photon",
    "Last Photon",
    "Duration (ms)",
    "Number of Photons",
    "Number of Photons (green)",
    "Number of Photons (red)",
    "E",
    "S",
]
#: (E, S) centre of each population, and its share out of 5.
POPULATIONS = (((0.25, 0.5), 2), ((0.75, 0.5), 2), ((0.02, 0.95), 1))


def build(root: pathlib.Path, per_file: int = 150, files: int = 2, seed: int = 11) -> pathlib.Path:
    """Write the burst tables under *root*; return *root* (the folder to open)."""
    rng = np.random.default_rng(seed)
    folder = root / "bi4_bur"
    folder.mkdir(parents=True, exist_ok=True)
    pattern = [i for i, (_c, share) in enumerate(POPULATIONS) for _ in range(share)]
    for f in range(files):
        lines = ["\t".join(COLUMNS)]
        first = 0
        for b in range(per_file):
            (e, s), _share = POPULATIONS[pattern[b % len(pattern)]]
            n = int(rng.integers(40, 400))
            e_b = float(np.clip(rng.normal(e, 0.05), 0.0, 1.0))
            s_b = float(np.clip(rng.normal(s, 0.04), 0.0, 1.0))
            red = int(round(n * e_b))
            last = first + n - 1
            row = [first, last, round(n / 120.0, 3), n, n - red, red, round(e_b, 4), round(s_b, 4)]
            lines += ["\t".join("0" for _ in COLUMNS), "\t".join(str(v) for v in row)]
            first = last + 1
        (folder / f"m{f:03d}.bur").write_text("\n".join(lines) + "\n")
    return root

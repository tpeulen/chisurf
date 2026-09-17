"""Cut a small MATLAB-produced fixture out of ebFRET's shipped session file.

ebFRET's ``datasets/simulated-K04-N350-ebfret-session.mat`` was saved by the
MATLAB GUI (compiled MEX forward-backward and Viterbi) after running the
analysis to convergence. The K = 4 analysis of its first 12 series -- prior,
posteriors, statistics, lower bounds, Viterbi paths and the cropped, clipped
signal -- is written to ``tests/data/ebfret_session_k4.json`` so the port can be
checked against a real MATLAB run without the 1.7 MB session in the tree.

Usage::

    python extract_session_fixture.py path/to/simulated-K04-N350-ebfret-session.mat
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import scipy.io as sio

N_SERIES = 12
FIELDS = ("mu", "beta", "W", "nu", "A", "pi")
EXPECT = ("z", "z1", "zz", "x", "xx")
OUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "ebfret_session_k4.json"


def _arr(value) -> list:
    """Return a numeric value as a nested list of floats."""
    return np.asarray(value, dtype=float).tolist()


def main(path: str) -> None:
    """Write the fixture from the session at ``path``."""
    mat = sio.loadmat(path, squeeze_me=True, struct_as_record=False)
    series, analysis, controls = mat["series"], mat["analysis"][3], mat["controls"]
    clip = (float(controls.clip.min), float(controls.clip.max))
    out = {
        "source": "ebFRET simulated-K04-N350-ebfret-session.mat, analysis(4), series 1..%d"
        % N_SERIES,
        "clip": clip,
        "restarts": int(controls.restarts),
        "run_precision": float(controls.run_precision),
        "prior": {k: _arr(getattr(analysis.prior, k)) for k in FIELDS},
        "total_lowerbound": float(np.sum(analysis.lowerbound)),
        "series": [],
    }
    for n in range(N_SERIES):
        s = series[n]
        x = np.asarray(s.signal, dtype=float)[int(s.crop.min) - 1 : int(s.crop.max)]
        x = np.clip(x, *clip)
        out["series"].append(
            {
                "signal": _arr(x),
                "posterior": {k: _arr(getattr(analysis.posterior[n], k)) for k in FIELDS},
                "expect": {k: _arr(getattr(analysis.expect[n], k)) for k in EXPECT},
                "lowerbound": float(analysis.lowerbound[n]),
                "restart": int(analysis.restart[n]),
                "viterbi_state": _arr(analysis.viterbi[n].state),
                "viterbi_mean": _arr(analysis.viterbi[n].mean),
            }
        )
    OUT.write_text(json.dumps(out, separators=(",", ":")))


if __name__ == "__main__":
    main(sys.argv[1])

"""Real FCS repeats for the merger: test/data/tttr/BH/132/BH_SPC132.spc (62 s, SPC-130) cut into six 10 s chunks,
each cross-correlated (routing channels 0+1 against 8+9) with tttrlib and written as a Kristine .cor chunk.

usage: python make_chunks.py <out_dir>   (run from the repo root); importable as build(out_dir) -> out_dir
"""
import pathlib
import sys

import numpy as np

SPC = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")


def build(out_dir, n_chunks=6, seconds=10.0):
    import tttrlib

    from chisurf.core.fluorescence.fcs.merge import save_mean_correlation

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tttr = tttrlib.TTTR(str(SPC.resolve()), "SPC-130")
    resolution = tttr.header.macro_time_resolution
    times = np.asarray(tttr.macro_times, dtype=np.float64) * resolution
    for k in range(n_chunks):
        idx = np.flatnonzero((times >= k * seconds) & (times < (k + 1) * seconds))
        chunk = tttr[int(idx[0]):int(idx[-1]) + 1]
        correlator = tttrlib.Correlator(tttr=chunk, channels=([0, 1], [8, 9]), n_bins=7, n_casc=25)
        x, y = np.asarray(correlator.x_axis), np.asarray(correlator.correlation)    # x in seconds
        keep = (x > 0) & np.isfinite(y)
        channels = np.asarray(chunk.routing_channels)
        counts_a, counts_b = int(np.isin(channels, (0, 1)).sum()), int(np.isin(channels, (8, 9)).sum())
        save_mean_correlation({"x": x[keep], "y": y[keep], "ey": np.zeros(keep.sum()), "duration": seconds,
                               "count_rate": (counts_a + counts_b) / 2.0 / seconds / 1000.0},
                              out_dir / f"chnk-{k:04}.cor")
    return out_dir


if __name__ == "__main__":
    print(build(sys.argv[1]))

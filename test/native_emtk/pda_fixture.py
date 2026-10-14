"""A synthetic two-colour PDA dataset shared by the emtk shell model tests."""


def make_pda_curve():
    """A synthetic two-colour PDA dataset (an S1S2 histogram of 60 photons at most), the PDA reader's shape."""
    import numpy as np
    from scipy import stats

    import chisurf.core.fluorescence.tcspc as tcspc
    from chisurf.core.data import DataCurve

    nmax, nmin = 60, 5
    n = np.arange(nmax + 1)
    ps = stats.poisson.pmf(n, mu=20.0).astype(float)
    ps /= ps.sum()
    s1s2 = np.zeros((nmax + 1, nmax + 1), dtype=float)
    for count in range(nmin, nmax + 1):
        g = np.arange(count + 1)
        s1s2[g, count - g] += ps[count] * stats.binom.pmf(g, count, 0.6) * 1000.0
    ny, nx = s1s2.shape
    rr, cc = np.indices((ny, nx))
    y = s1s2.ravel(order="C")
    pda = {
        "maximum_number_of_photons": nmax,
        "minimum_number_of_photons": nmin,
        "minimum_time_window_length": 2e-3,
        "segmentation": "time-bins",
        "observation_time": 2e-3,
        "channels": ([0], [1]),
        "s1s2": s1s2,
        "ps": ps,
        "row_indices": rr.ravel().tolist(),
        "col_indices": cc.ravel().tolist(),
        "ndim": 2,
        "shape": (ny, nx),
        "size": int(y.size),
        "tttr_indices": None,
    }
    return DataCurve(
        name="synthetic-pda",
        load_filename_on_init=False,
        pda=pda,
        y=y,
        x=np.arange(y.size),
        ey=tcspc.counting_noise(y),
    )

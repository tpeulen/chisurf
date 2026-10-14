from __future__ import annotations

import os

import numpy as np

from chisurf import typing
from chisurf.core.fio.fluorescence.fcs.definitions import FCSDataset


def read_dat(filename: str, verbose: bool = False) -> typing.List[FCSDataset]:
    """Read a PicoQuant .dat FCS file.

    Parameters
    ----------
    filename : str
        Path to the .dat file.
    verbose : bool
        If True, print progress.

    Returns
    -------
    list of dict
        List of FCS dataset dictionaries.
    """
    if verbose:
        print(f"Reading PicoQuant data file: {filename}")
    correlations: typing.List[FCSDataset] = list()
    d = np.loadtxt(filename, skiprows=2, encoding="latin1").T
    n_corr = d.shape[0] // 3
    for i in range(n_corr):
        correlation_time = d[i * 3 + 0]
        correlation_amplitude = d[i * 3 + 1]
        err = d[i * 3 + 2]
        # data points without error should
        # not contribute to analysis. Hence, set err to
        # large value
        err[err == 0] = 1e12
        correlation_weight = 1.0 / err
        corr: FCSDataset = {
            "filename": filename,
            # The file's stem; [1] (the extension) named every curve ".dat_<i>".
            "measurement_id": f"{os.path.splitext(os.path.basename(filename))[0]}_{i}",
            "correlation_times": correlation_time.tolist(),
            "correlation_amplitudes": correlation_amplitude.tolist(),
            "correlation_amplitude_weights": correlation_weight.tolist(),
        }
        correlations.append(corr)
    return correlations

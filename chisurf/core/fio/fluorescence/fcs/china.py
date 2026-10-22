import numpy as np

try:
    from tttrlib.matfile import loadmat
except ImportError:  # the Pyodide wheel ships only the compiled extension

    def loadmat(*args, **kwargs):
        raise RuntimeError(
            "MAT-file support needs tttrlib.matfile, which this build does not "
            "ship (the Pyodide wheel carries only the compiled extension)."
        )


import chisurf as cs
import chisurf.core.fluorescence.fcs
from chisurf import typing
from chisurf.core.fio.fluorescence.fcs.definitions import FCSDataset


def read_china_mat(
    filename: str, skip_points: int = 4, verbose: bool = False
) -> typing.List[FCSDataset]:
    """Read a China .mat FCS file and return FCS datasets.

    Parameters
    ----------
    filename : str
        Path to the .mat file.
    skip_points : int
        Number of initial points to skip.
    verbose : bool
        If True, print progress.

    Returns
    -------
    list of FCSDataset
        List of FCS datasets.
    """
    m = loadmat(filename)
    n_measurements = m["AA"].shape[1]
    # save intensity traces
    if verbose:
        print(f"Reading from file: {filename}")

    # (intensity trace key(s), correlation key) per correlation kind.
    correlation_keys: list[tuple[str | list[str], str]] = [
        ("IntA", "AA"),
        ("IntB", "BB"),
        (["IntA", "IntB"], "AAxB"),
    ]
    correlations: typing.List[FCSDataset] = list()

    for intensity_key, correlation_key in correlation_keys:
        correlation_time = m[correlation_key][:, 0]

        for measurement_number in range(1, n_measurements):
            correlation_amplitude = m[correlation_key][:, measurement_number] + 1.0
            if isinstance(intensity_key, list):
                k = intensity_key[0]
                intensity = np.zeros_like(m[k][:, measurement_number])
                intensity_time = m[k][:, 0]
                for k in intensity_key:
                    intensity += m[k][:, measurement_number]
            else:
                intensity_time = m[intensity_key][:, 0]
                intensity = m[intensity_key][:, measurement_number]
            aquisition_time = intensity_time[-1]
            mean_count_rate = intensity.sum() / (aquisition_time * 1000.0)
            w = 1.0 / cs.core.fluorescence.fcs.noise(
                correlation_time,
                correlation_amplitude,
                aquisition_time,
                mean_count_rate=mean_count_rate,
                skip_points=skip_points,
            )
            correlations.append(
                {
                    "filename": filename,
                    "measurement_id": f"{correlation_key}_{measurement_number}",
                    "acquisition_time": float(aquisition_time),
                    "mean_count_rate": float(mean_count_rate),
                    "correlation_times": correlation_time.tolist(),
                    "correlation_amplitudes": correlation_amplitude.tolist(),
                    "correlation_amplitude_weights": w.tolist(),
                    "intensity_trace_times": intensity_time.tolist(),
                    "intensity_trace": intensity.tolist(),
                }
            )
    return correlations

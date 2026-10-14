from __future__ import annotations

import yaml

import chisurf.core.base
import chisurf.core.fio as io
from chisurf import typing
from chisurf.core.fio.fluorescence.fcs.definitions import FCSDataset


def write_yaml(filename: str, data: typing.List[FCSDataset], verbose: bool = False) -> None:
    """

    :param filename: the filename
    :param correlation_amplitude: an array containing the amplitude of the
    correlation function
    :param correlation_amplitude_uncertainty: an estimate for the
    uncertainty of the correlation amplitude
    :param correlation_time: an array containing the correlation times
    :param mean_countrate: the mean countrate of the experiment in kHz
    :param acquisition_time: the acquisition of the FCS experiment in
    seconds
    :return:
    """
    if verbose:
        print("Writing yaml .yaml to file: ", filename)
    txt = yaml.dump(
        data=[chisurf.core.base.to_elementary(obj=dict(d), skip_qt_widgets=True) for d in data]
    )
    with io.zipped.open_maybe_zipped(filename=filename, mode="w") as fp:
        fp.write(txt)


def read_yaml(filename: str, verbose: bool = False) -> typing.List[FCSDataset]:
    """Read a YAML FCS file.

    Parameters
    ----------
    filename : str
        Path to the YAML file.
    verbose : bool
        If True, print progress.

    Returns
    -------
    list of FCSDataset
        List of FCS datasets.

    Notes
    -----
    The inverse of :func:`write_yaml`. It was an empty stub returning ``None``
    while ``read_fcs`` offered it as the ``"yaml"`` reader, so loading such a
    file raised a TypeError on the ``None``.
    """
    if verbose:
        print("Reading yaml .yaml from file: ", filename)
    with io.zipped.open_maybe_zipped(filename=filename, mode="r") as fp:
        data = yaml.safe_load(fp)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError(f"{filename} holds no list of FCS datasets")
    datasets: typing.List[FCSDataset] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError(f"{filename}: an FCS dataset must be a mapping, got {entry!r}")
        entry.setdefault("filename", filename)
        missing = {"measurement_id", "correlation_times", "correlation_amplitudes"} - set(entry)
        if missing:
            raise ValueError(f"{filename}: an FCS dataset lacks {', '.join(sorted(missing))}")
        # Checked above: the required keys of an FCSDataset are present.
        datasets.append(typing.cast(FCSDataset, entry))
    return datasets

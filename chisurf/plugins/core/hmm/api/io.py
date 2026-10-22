"""Reading binned traces for hidden-Markov-model analysis.

Click-free on purpose: the GUI's view model loads traces through this module,
and the web release ships no :mod:`click` -- a GUI that reached for the CLI
module for one loader made the tool unopenable there (``ModuleNotFoundError:
No module named 'click'``). The CLI imports this; nothing imports the CLI.
"""

from __future__ import annotations

import pathlib

import numpy as np

__all__ = ["load_trace"]


def load_trace(path: str) -> np.ndarray:
    """Load a binned trace from ``.npy`` or a delimited text file.

    Parameters
    ----------
    path : str
        File to read. ``.npy`` is loaded as-is; anything else is parsed as
        delimited text, comma-separated if the first non-comment line contains
        a comma.

    Returns
    -------
    numpy.ndarray
        Trace of shape ``(n_bins, n_channels)``.
    """
    file = pathlib.Path(path)
    if file.suffix.lower() == ".npy":
        data = np.load(file)
    else:
        text = file.read_text().splitlines()
        sample = next((line for line in text if line and not line.startswith("#")), "")
        data = np.loadtxt(file, delimiter="," if "," in sample else None)
    return data if data.ndim == 2 else data[:, None]

"""Save a dataset to a file and load it back: the dataset list's *Save* and *Load*.

``ExperimentalData.save(file_type="pkl")`` wrote nothing (the base class supports only YAML and
JSON and returned silently for any other type), and a dataset object cannot be pickled whole (its
reader and experiment hold native handles). Both shells go through these two functions instead:
the file is a pickle of the trusted cached-dataset record the server's ``dataset.load`` takes
(:func:`chisurf.core.api._extract_curve_data`), which carries the arrays, the mask, the name and
the reader's configuration but not the native objects.
"""

from __future__ import annotations

import os
import pickle
import uuid
from typing import Any


def save_dataset(dataset: Any, filename: str) -> str:
    """Write *dataset* to *filename* (``.pkl`` appended when it has no suffix); return the path.

    Parameters
    ----------
    dataset : object
        A curve or a group of curves.
    filename : str
        Target path.

    Raises
    ------
    ValueError
        When the dataset has no curve data to record.
    """
    from chisurf.core.api import _extract_curve_data

    record = _extract_curve_data(dataset)
    if record is None:
        raise ValueError("the dataset has no curve data to save")
    path = str(filename)
    if not os.path.splitext(path)[1]:
        path += ".pkl"
    with open(path, "wb") as handle:
        pickle.dump(record, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return path


def load_dataset(filename: str) -> Any:
    """Read a dataset written by :func:`save_dataset`, under fresh identifiers.

    A loaded copy never shares a unique identifier with the dataset it was saved from, which may
    still be in the session. The file is unpickled, so only open files you saved yourself.
    """
    from chisurf.server.services.datasets import _prepare_cached_dataset, _restore_cached_dataset

    with open(filename, "rb") as handle:
        record = pickle.load(handle)  # noqa: S301 - the user's own saved dataset
    dataset = _restore_cached_dataset(_prepare_cached_dataset(record))
    for item in (dataset, *(list(dataset) if hasattr(dataset, "__iter__") else [])):
        item.unique_identifier = str(uuid.uuid4())
    return dataset

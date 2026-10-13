from __future__ import annotations

import numpy as np

from chisurf import typing


class _FCSDatasetOptional(typing.TypedDict, total=False):
    """Keys a reader may omit (set later by masking / trace naming)."""

    mask: np.ndarray
    intensity_trace_name: str


class FCSDataset(_FCSDatasetOptional):
    filename: str
    measurement_id: str
    acquisition_time: float
    mean_count_rate: float
    correlation_times: np.ndarray
    correlation_amplitudes: np.ndarray
    correlation_amplitude_weights: np.ndarray
    intensity_trace_times: np.ndarray
    intensity_trace: np.ndarray
    meta_data: typing.Dict

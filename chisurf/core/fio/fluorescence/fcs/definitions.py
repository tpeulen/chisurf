from __future__ import annotations

import numpy as np

from chisurf import typing

#: A correlation axis or amplitude column: readers hand out arrays or plain lists.
Column = typing.Union[np.ndarray, typing.List[float]]


class _FCSDatasetOptional(typing.TypedDict, total=False):
    """Keys a reader may omit.

    Only the curve itself is guaranteed. Weights are computed by
    :func:`chisurf.core.fio.fluorescence.fcs.read_fcs` when a reader has none;
    acquisition time, count rate and the intensity trace exist only where the
    instrument's file records them (``None`` where a format has the field but
    no value); ``meta_data`` is folded into the curve's metadata and removed.
    """

    correlation_amplitude_weights: Column
    acquisition_time: float
    mean_count_rate: float
    intensity_trace_times: Column | None
    intensity_trace: Column | None
    meta_data: typing.Dict
    mask: Column
    intensity_trace_name: str
    #: Auto- or cross-correlation, where the instrument file says.
    correlation_type: str
    #: Two-detector files: the summed rate, what ``mean_count_rate`` means
    #: (``"per_detector_mean"``) and how many detectors fed it.
    mean_count_rate_total: float
    mean_count_rate_semantics: str
    detector_count: int


class FCSDataset(_FCSDatasetOptional):
    """One correlation curve as an FCS reader returns it."""

    filename: str
    measurement_id: str
    correlation_times: Column
    correlation_amplitudes: Column

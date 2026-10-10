"""The acquisition as a ChiSurf dataset, so its fit window is an ordinary one.

:class:`AcquisitionDataset` is a :class:`~chisurf.core.data.DataCurve` whose
curve is the first live decay window and which carries the latest pipeline
snapshot (:meth:`~chisurf.plugins.core.acq.pipeline.AcquisitionPipeline.snapshot`,
the only thread-safe crossing out of the acquisition thread). The pages of the
Acquisition model read the snapshot through :attr:`AcquisitionDataset.live`.

The pipeline is single-threaded. A stream started with :meth:`start_stream` runs
on a worker thread that pushes photon words and publishes snapshots on a queue;
:meth:`AcquisitionDataset.refresh`, called from the GUI thread, drains it. A
dataset whose pipeline is idle pulls ``pipeline.snapshot()`` itself.
"""

from __future__ import annotations

import queue
import threading
from typing import Any

import numpy as np

from chisurf.core.data import DataCurve

#: Name of the model the dataset is opened with (``AcquisitionModel.name``).
MODEL_NAME = "Acquisition"


class AcquisitionDataset(DataCurve):
    """Live decay curve plus the pipeline snapshot behind the fit-window pages."""

    def __init__(self, *args: Any, name: str = "Acquisition", n_bins: int = 4096,
                 tac_dt_ns: float = 0.004069, **kwargs: Any) -> None:
        """Create an empty dataset; data arrives with :meth:`set_snapshot`.

        Parameters
        ----------
        name : str
            Dataset name.
        n_bins : int
            Number of micro-time bins of the empty initial curve.
        tac_dt_ns : float
            Bin width of the micro-time axis in nanoseconds.
        """
        from chisurf.plugins.core.acq.gui.live_plots import LivePlots

        x = np.arange(int(n_bins), dtype=float) * float(tac_dt_ns)
        kwargs.setdefault("load_filename_on_init", False)
        super().__init__(*args, x=x, y=np.zeros_like(x), name=name, **kwargs)
        self.snapshot: dict[str, Any] | None = None
        self.live = LivePlots()
        self.live.tac_dt_ns = float(tac_dt_ns)
        self.pipeline: Any | None = None
        #: The fit window's fit, and the API that owns it; set by :func:`open_demo`.
        self.fit: Any | None = None
        self.api: Any | None = None
        self._events: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._seen_photons = -1

    # -- the pipeline crossing ------------------------------------------------ #
    @property
    def pipeline_snapshot(self) -> dict[str, Any] | None:
        """The latest snapshot (``None`` before the first)."""
        return self.snapshot

    @property
    def streaming(self) -> bool:
        """Whether a worker thread is still pushing photons."""
        return self._thread is not None and self._thread.is_alive()

    def set_snapshot(self, snapshot: dict[str, Any] | None) -> None:
        """Take a pipeline snapshot: remember it, rebuild the series, move the curve."""
        if snapshot is None:
            return
        self.snapshot = snapshot
        self.live.set_snapshot(snapshot)
        self._seen_photons = int(snapshot.get("total_photons", 0))
        decays = snapshot.get("decay_data") or []
        if len(decays):
            y = np.asarray(decays[0], dtype=float)
            x = np.arange(len(y), dtype=float) * float(self.live.tac_dt_ns)
            self.set_data(x=x, y=y, ey=np.sqrt(np.maximum(y, 1.0)))

    def refresh(self) -> bool:
        """Bring the dataset up to date from the pipeline; return whether it changed.

        Drains the worker's queue (the newest snapshot wins); with no worker, pulls
        ``pipeline.snapshot()`` when the pipeline has seen more photons than the
        dataset. Call from the thread that owns the GUI.
        """
        latest = None
        while True:
            try:
                latest = self._events.get_nowait()
            except queue.Empty:
                break
        if latest is None and self.pipeline is not None and not self.streaming:
            if int(self.pipeline.total_photons) != self._seen_photons:
                latest = self.pipeline.snapshot()
        if latest is None:
            return False
        self.set_snapshot(latest)
        return True

    def update_fit(self) -> bool:
        """Recompute the fit window's fit (and so redraw its pages) through the API."""
        if self.api is None or self.fit is None:
            return False
        result = self.api.fit_update(fit_uid=str(self.fit.unique_identifier))
        return bool(result.get("ok"))

    def start_stream(self, words: Any, config: Any, *, pause_s: float = 0.0005,
                     chunk: int = 256, every: int = 8) -> None:
        """Push *words* through a new pipeline on a worker thread.

        Parameters
        ----------
        words : numpy.ndarray
            Raw ``uint32`` device words.
        config : PipelineConfig
            Pipeline configuration (record type, routing channels, ...).
        pause_s : float
            Pause between chunks, so the stream is watched rather than finished
            before the window opens.
        chunk, every : int
            Words per push, and chunks per published snapshot.
        """
        from chisurf.plugins.core.acq.pipeline import AcquisitionPipeline

        self.stop_stream()
        self._cancel = threading.Event()
        self.live.apply_to_config(config)
        self.pipeline = pipeline = AcquisitionPipeline(config)
        relay = _Relay(self._events)
        self._thread = threading.Thread(
            target=_run, args=(pipeline, words, relay, self._cancel, pause_s, chunk, every),
            name="acq-demo-stream", daemon=True)
        self._thread.start()

    def stop_stream(self) -> None:
        """Cancel and join the worker, if any."""
        self._cancel.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

    def close(self) -> None:
        """Stop streaming (the pipeline closes its sink)."""
        self.stop_stream()


class _Relay:
    """Adapt ``events.put(("snapshot", data))`` to a queue of bare snapshots."""

    def __init__(self, target: queue.Queue) -> None:
        self.target = target

    def put(self, item: tuple[str, Any]) -> None:
        """Forward the payload of a ``("snapshot", data)`` event."""
        self.target.put(item[1])


def _run(pipeline: Any, words: Any, relay: _Relay, cancel: threading.Event,
         pause_s: float, chunk: int, every: int) -> None:
    """Worker body: stream, flush, publish the final snapshot."""
    from chisurf.plugins.core.acq.gui.live_plots import stream_words

    stream_words(pipeline, words, relay, every=every, chunk=chunk, cancel=cancel, pause_s=pause_s)
    pipeline.flush()
    relay.put(("snapshot", pipeline.snapshot()))


def open_demo(main: Any = None, *, stream: bool = True) -> AcquisitionDataset:
    """Simulate the demo stream, register it as a dataset and open its fit window.

    The dataset goes through ``cs.api.load_dataset``; ``cs.api.add_fit`` with the
    Acquisition model announces ``fit.added``, which the main window answers with
    the fit window. Headless, the dataset and the fit exist and the window does not.

    Parameters
    ----------
    main : object, optional
        Unused host handle, kept so a plugin can pass its window.
    stream : bool
        Start the photon stream. ``False`` registers an idle dataset.

    Returns
    -------
    AcquisitionDataset
        The registered dataset.

    Raises
    ------
    RuntimeError
        If the dataset or the fit could not be registered.
    """
    import chisurf as cs
    from chisurf.core.experiments import types as experiment_types
    from chisurf.core.models.acquisition import AcquisitionModel
    from chisurf.plugins.core.acq import demo
    from chisurf.plugins.core.acq.pipeline import PipelineConfig, record_type_for_device

    class _Device:
        device_type = "SIMULATION"

    params = demo.simulation_params()
    dataset = AcquisitionDataset(name="Acquisition demo", n_bins=params["N_tac_channels"],
                                 tac_dt_ns=params["tac_dt"])
    experiment = experiment_types["tcspc"]
    if AcquisitionModel.name not in experiment.model_names:
        experiment.add_model_class(AcquisitionModel)
    dataset.experiment = experiment
    # Two detection channels: draw only their decays, on a log axis where a
    # two-species decay is readable.
    for window in range(len(dataset.live._config_channels)):
        setattr(dataset.live, f"decay_show{window}", window < int(params["N_channels"]))
    dataset.live.decay_log_y = True
    config = PipelineConfig(record_type=record_type_for_device(_Device()),
                            n_microtime_bins=params["N_tac_channels"])
    api = getattr(cs, "api", None)
    if api is None:
        from chisurf.core.api import ChiSurfAPI

        api = ChiSurfAPI(mode="local")
    datasets, fits = len(api.list_datasets()), len(api.list_fits())
    result = api.load_dataset(dataset=dataset, name="Acquisition demo")
    if (isinstance(result, dict) and not result.get("ok", True)) or (
        len(api.list_datasets()) <= datasets
    ):
        raise RuntimeError(f"could not register the acquisition dataset: {result!r}")
    added = api.add_fit(dataset_indices=[len(api.list_datasets()) - 1], model_name=MODEL_NAME)
    if (isinstance(added, dict) and not added.get("ok", True)) or len(api.list_fits()) <= fits:
        raise RuntimeError(f"could not add the Acquisition fit: {added!r}")
    dataset.api, dataset.fit = api, api._state.fits[-1]
    dataset.fit.name = MODEL_NAME
    if stream:
        dataset.start_stream(demo.words(demo.make_demo()), config)
    return dataset

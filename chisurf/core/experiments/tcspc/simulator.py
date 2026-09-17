from __future__ import annotations

import numpy as np

import chisurf.core.data
import chisurf.core.fluorescence
import chisurf.core.fluorescence.decay
import chisurf.core.fluorescence.tcspc
from chisurf import typing

from .reader import TCSPCReader


def gaussian_irf(time_axis: np.ndarray, mean: float = 5.0, sigma: float = 0.2) -> np.ndarray:
    """Return a peak-normalised Gaussian instrument response.

    Parameters
    ----------
    time_axis : numpy.ndarray
        Time axis of the decay histogram in nanoseconds.
    mean : float
        Position of the IRF maximum in nanoseconds.
    sigma : float
        Width of the IRF in nanoseconds; non-positive widths are clamped to a
        narrow but finite value so the response stays a valid photon-count
        distribution.

    Returns
    -------
    numpy.ndarray
        Gaussian response scaled to a maximum of one.
    """
    from chisurf.core.fluorescence.tcspc.irf import FWHM_TO_SIGMA, synthetic_irf

    s = float(sigma) if float(sigma) > 0.0 else 1e-3
    irf = synthetic_irf(time_axis, float(mean), s / FWHM_TO_SIGMA, norm=False)
    max_value = float(np.max(irf)) if irf.size else 0.0
    return irf / max_value if max_value > 0.0 else irf


def resolve_irf(
    time_axis: np.ndarray, irf: typing.Any = None, mean: float = 5.0, sigma: float = 0.2
) -> np.ndarray:
    """Return an instrument response sampled on *time_axis*.

    A curve-like ``irf`` (anything carrying ``x``/``y``, e.g. a
    :class:`~chisurf.core.data.DataCurve`) is interpolated onto the time axis;
    a plain array is used as-is when its length matches. Everything else falls
    back to a Gaussian defined by *mean* and *sigma*.

    Parameters
    ----------
    time_axis : numpy.ndarray
        Time axis of the decay histogram in nanoseconds.
    irf : object, optional
        Measured IRF as a curve or as a bare intensity array.
    mean : float
        Mean of the Gaussian fallback in nanoseconds.
    sigma : float
        Width of the Gaussian fallback in nanoseconds.

    Returns
    -------
    numpy.ndarray
        Peak-normalised response of the same length as *time_axis*.
    """
    t = np.asarray(time_axis, dtype=np.float64)
    if irf is not None:
        x_irf = np.asarray(getattr(irf, "x", []), dtype=np.float64).ravel()
        y_irf = np.asarray(getattr(irf, "y", irf), dtype=np.float64).ravel()
        if x_irf.size > 1 and y_irf.size == x_irf.size:
            order = np.argsort(x_irf)
            response = np.interp(t, x_irf[order], y_irf[order], left=0.0, right=0.0)
        elif x_irf.size == 0 and y_irf.size == t.size:
            response = y_irf.copy()
        else:
            response = np.zeros(0, dtype=np.float64)
        max_value = float(np.max(response)) if response.size else 0.0
        if max_value > 0.0:
            return response / max_value
    return gaussian_irf(t, mean=mean, sigma=sigma)


def simulate_decay(
    lifetime_spectrum: typing.Any,
    n_tac: int = 4096,
    dt: float = 0.0141,
    p0: float = 10000.0,
    irf: typing.Any = None,
    irf_mean: float = 5.0,
    irf_sigma: float = 0.2,
    add_noise: bool = True,
    seed: int = None,
) -> typing.Tuple[np.ndarray, np.ndarray]:
    """Simulate a TCSPC decay histogram.

    This is *the* generator behind the simulator setup: the deterministic decay
    is built from the interleaved lifetime spectrum and convolved with the
    instrument response by the canonical
    :func:`chisurf.core.fluorescence.decay.synthetic_decay`, scaled to the
    requested peak count and finally Poisson-sampled — so the reader-level
    ``read()`` path (**+ Data**) and the panel's **Simulate**/**Add** buttons
    return the same curve for the same settings.

    ``allow_rise_terms=True`` keeps this acquisition simulator's ability to
    model rise terms (negative amplitudes) and zero-lifetime components, which
    the strict default of the interactive generator rejects.

    Parameters
    ----------
    lifetime_spectrum : array_like
        Interleaved ``(amplitude, lifetime, ...)`` spectrum; lifetimes in
        nanoseconds. An empty or odd-length spectrum yields a zero decay.
    n_tac : int
        Number of TAC bins (time channels).
    dt : float
        Time resolution per bin in nanoseconds.
    p0 : float
        Peak photon count the deterministic decay is scaled to. Non-positive
        values leave the decay unscaled.
    irf : object, optional
        Measured IRF (curve or array); a Gaussian is used when absent.
    irf_mean : float
        Mean of the Gaussian fallback IRF in nanoseconds.
    irf_sigma : float
        Width of the Gaussian fallback IRF in nanoseconds.
    add_noise : bool
        Poisson-sample the scaled decay to obtain photon counts.
    seed : int, optional
        Seed for the Poisson sampling; makes a simulation reproducible.

    Returns
    -------
    (numpy.ndarray, numpy.ndarray)
        Time axis in nanoseconds and the simulated decay.
    """
    n = int(max(1, int(n_tac)))
    x = np.arange(n, dtype=np.float64) * float(dt)
    spectrum = np.asarray(lifetime_spectrum, dtype=np.float64).ravel()
    if spectrum.size < 2:
        return x, np.zeros(n, dtype=np.float64)

    response = resolve_irf(x, irf, mean=irf_mean, sigma=irf_sigma)
    y = chisurf.core.fluorescence.decay.synthetic_decay(
        n_bins=n,
        lifetimes=spectrum[1::2],
        amplitudes=spectrum[0::2],
        bin_width=float(dt),
        start_bin=0,
        irf=response,
        normalize=False,
        allow_rise_terms=True,
    )
    y = np.clip(np.asarray(y, dtype=np.float64), 0.0, None)

    y_max = float(np.max(y)) if y.size else 0.0
    if y_max > 0.0 and float(p0) > 0.0:
        y = y * (float(p0) / y_max)

    if add_noise and np.any(y > 0.0):
        y = chisurf.core.fluorescence.decay.sample_decay_shot_noise(y, seed=seed)
    return x, y


def simulate_decay_channels(
    lifetime_spectrum: typing.Any,
    anisotropy_spectrum: typing.Any = None,
    *,
    n_tac: int = 4096,
    dt: float = 0.0141,
    p0: float = 10000.0,
    g_factor: float = 1.0,
    l1: float = 0.0,
    l2: float = 0.0,
    irf: typing.Any = None,
    irf_mean: float = 5.0,
    irf_sigma: float = 0.2,
    add_noise: bool = True,
    seed: int = None,
) -> typing.Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Simulate the polarized VV/VH pair of a decay with anisotropy.

    The channel twin of :func:`simulate_decay`: the same ideal (peak-scaled,
    IRF-convolved) magic-angle decay is split into the parallel and
    perpendicular channels with the fit stack's forward model
    (:func:`~chisurf.core.fluorescence.anisotropy.decay.vm_rt_to_vv_vh`)
    before the IRF convolution, and a finite-count observation is Poisson
    sampled per channel from one generator with the budget split
    proportionally — so the pair keeps the anisotropy in its ratio.

    Parameters
    ----------
    lifetime_spectrum : array-like
        Interleaved (amplitude, lifetime, ...) spectrum; lenient like
        :func:`simulate_decay` (rise terms allowed).
    anisotropy_spectrum : array-like, optional
        Interleaved rotation spectrum (b_1, rho_1, ...). Empty means no
        anisotropy (VV = VM, VH = VM / g).
    n_tac : int
        Number of TAC bins.
    dt : float
        Time resolution per bin in nanoseconds.
    p0 : float
        Peak photon count of the magic-angle decay before channel split.
    g_factor : float
        Parallel/perpendicular detection sensitivity ratio.
    l1, l2 : float
        Polarization mixing factors of the two channels.
    irf : DataCurve or array, optional
        Measured IRF; falls back to the Gaussian defined by *irf_mean* /
        *irf_sigma* (see :func:`resolve_irf`).
    irf_mean, irf_sigma : float
        Gaussian fallback IRF parameters (ns).
    add_noise : bool
        Poisson-sample both channels.
    seed : int, optional
        Seed for the shared Poisson generator.

    Returns
    -------
    (numpy.ndarray, numpy.ndarray, numpy.ndarray)
        ``(x, vv, vh)`` — the time axis (ns) and the two channel histograms.
    """
    from chisurf.core.fluorescence.anisotropy.decay import anisotropy_rt
    from chisurf.core.fluorescence.decay import synthetic_decay
    from chisurf.core.fluorescence.tcspc.convolve import convolve_decay

    n = int(max(1, int(n_tac)))
    x = np.arange(n, dtype=np.float64) * float(dt)
    spectrum = np.atleast_1d(np.asarray(lifetime_spectrum, dtype=np.float64)).ravel()
    if spectrum.size < 2:
        return x, np.zeros(n, dtype=np.float64), np.zeros(n, dtype=np.float64)
    # Ideal magic-angle decay (unscaled; the peak convention of
    # :func:`simulate_decay` is applied after convolution). The interleaved
    # spectrum is split exactly like :func:`simulate_decay` splits it.
    vm = synthetic_decay(
        n,
        lifetimes=spectrum[1::2],
        amplitudes=spectrum[0::2],
        bin_width=float(dt),
        normalize=False,
        allow_rise_terms=True,
    )
    vm = np.clip(np.asarray(vm, dtype=np.float64), 0.0, None)

    rot = np.atleast_1d(
        np.asarray([] if anisotropy_spectrum is None else anisotropy_spectrum, dtype=np.float64)
    ).ravel()
    rt = anisotropy_rt(x, rot)
    # The channel model of ``vm_rt_to_vv_vh`` applied to the already-computed
    # r(t) (identical algebra; the helper would re-derive the same r(t)):
    #     VV = vm (1 + (2 - 3 l1) r),    VH = vm (1 - (1 - 3 l2) r) / G
    vv = vm * (1.0 + (2.0 - 3.0 * float(l1)) * rt)
    vh = vm * (1.0 - (1.0 - 3.0 * float(l2)) * rt) / float(g_factor)

    response = resolve_irf(x, irf, mean=irf_mean, sigma=irf_sigma)
    vm_ref = vm
    if response.size:
        vm_ref = np.asarray(convolve_decay(vm, response, 0, n, float(dt)), dtype=float)
        vv = np.maximum(np.asarray(convolve_decay(vv, response, 0, n, float(dt)), dtype=float), 0.0)
        vh = np.maximum(np.asarray(convolve_decay(vh, response, 0, n, float(dt)), dtype=float), 0.0)

    # Scale the magic-angle reference's peak to p0 and apply the same factor
    # to both channels, so their ratio — the anisotropy — survives, and an
    # empty rotation spectrum reproduces :func:`simulate_decay` exactly.
    ref_max = float(np.max(vm_ref)) if vm_ref.size else 0.0
    if ref_max > 0.0 and float(p0) > 0.0:
        scale = float(p0) / ref_max
        vv = vv * scale
        vh = vh * scale

    if add_noise and np.any(vv + vh > 0.0):
        rng = np.random.default_rng(seed)
        vv = chisurf.core.fluorescence.decay.sample_decay_shot_noise(vv, rng=rng)
        vh = chisurf.core.fluorescence.decay.sample_decay_shot_noise(vh, rng=rng)
    return x, vv, vh


class TCSPCSimulatorSetup(TCSPCReader):
    name = "TCSPC-Simulator"

    def __init__(
        self,
        *args,
        n_tac: int = 4096,
        dt: float = 0.0141,
        p0: float = 10000.0,
        rep_rate: float = 10.0,
        lifetime_spectrum: typing.List[float] = None,
        instrument_response_function: chisurf.core.data.DataCurve = None,
        irf_mean: float = 5.0,
        irf_sigma: float = 0.2,
        add_noise: bool = True,
        seed: int = None,
        sample_name: str = "TCSPC-Dummy",
        polarization: str = "vm",
        rotation_spectrum: typing.List[float] = None,
        **kwargs,
    ):
        """Initialize a TCSPC simulator.

        Parameters
        ----------
        n_tac : int
            Number of TAC bins (time channels).
        dt : float
            Time resolution per bin in nanoseconds.
        p0 : float
            Initial peak photon count.
        rep_rate : float
            Laser repetition rate in MHz.
        lifetime_spectrum : list of float, optional
            Lifetime components for the simulated decay.
        instrument_response_function : DataCurve, optional
            IRF to convolve with the decay.
        irf_mean : float
            Mean of the Gaussian IRF used when no IRF curve is set, in ns.
        irf_sigma : float
            Width of the Gaussian IRF used when no IRF curve is set, in ns.
        add_noise : bool
            Poisson-sample the simulated decay.
        seed : int, optional
            Seed of the Poisson sampling; makes the simulation reproducible.
        sample_name : str
            Name for the simulated dataset.
        """
        super().__init__(*args, **kwargs)
        self.experiment = kwargs.get("experiment", None)
        if lifetime_spectrum:
            # Mirror the spectrum into the controller's line edit when a GUI
            # controller is attached. Headless/API use has no controller.
            line_edit = getattr(self.controller, "lineEdit_2", None)
            if line_edit is not None:
                line_edit.setText(",".join([str(x) for x in lifetime_spectrum]))
        self.instrument_response_function = instrument_response_function
        self.sample_name = sample_name
        if lifetime_spectrum is None:
            self.lifetime_spectrum = np.array([], dtype=np.float64)
        else:
            self.lifetime_spectrum = np.array(lifetime_spectrum, dtype=np.float64)
        self.n_tac = n_tac
        self.dt = dt
        self.p0 = p0
        self.rep_rate = rep_rate
        self.irf_mean = irf_mean
        self.irf_sigma = irf_sigma
        self.add_noise = add_noise
        self.seed = seed
        # -- anisotropy --------------------------------------------------
        # Detection mode: 'vm' (magic angle) or 'vv/vh' (polarized pair).
        # The rotation spectrum is interleaved (b_1, rho_1, b_2, rho_2, ...).
        # g_factor / l1 / l2 are the TCSPCReader's own calibration attributes;
        # when the polarization is a VV/VH pair they are what a fit reads from
        # the dataset's reader, exactly as after a VV/VH file load.
        self.polarization = str(polarization).lower()
        if rotation_spectrum is None:
            self.rotation_spectrum = np.array([], dtype=np.float64)
        else:
            self.rotation_spectrum = np.array(rotation_spectrum, dtype=np.float64)
        # ``polarization`` is the TCSPCReader's own attribute; the reader's
        # ``is_vv_vh`` flag mirrors it so anything that inspects the setup
        # (e.g. context help) sees a consistent pair.
        self.is_vv_vh = self.polarization != "vm"

    def simulate(self) -> typing.Tuple[np.ndarray, np.ndarray]:
        """Simulate a magic-angle decay from the setup's current parameters.

        Returns
        -------
        (numpy.ndarray, numpy.ndarray)
            Time axis in nanoseconds and the simulated photon counts.
        """
        return simulate_decay(
            self.lifetime_spectrum,
            n_tac=self.n_tac,
            dt=self.dt,
            p0=self.p0,
            irf=self.instrument_response_function,
            irf_mean=self.irf_mean,
            irf_sigma=self.irf_sigma,
            add_noise=self.add_noise,
            seed=self.seed,
        )

    def simulate_channels(
        self,
    ) -> typing.Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Simulate the polarized VV/VH pair for the current parameters.

        Uses :func:`simulate_decay_channels` — the channel twin of
        :func:`simulate_decay` — with the setup's rotation spectrum and the
        anisotropy calibration (``g_factor``, ``l1``, ``l2``).

        Returns
        -------
        (numpy.ndarray, numpy.ndarray, numpy.ndarray)
            ``(x, vv, vh)`` — time axis (ns) and the two channel histograms.
        """
        return simulate_decay_channels(
            self.lifetime_spectrum,
            self.rotation_spectrum,
            n_tac=self.n_tac,
            dt=self.dt,
            p0=self.p0,
            g_factor=self.g_factor,
            l1=self.l1,
            l2=self.l2,
            irf=self.instrument_response_function,
            irf_mean=self.irf_mean,
            irf_sigma=self.irf_sigma,
            add_noise=self.add_noise,
            seed=self.seed,
        )

    def simulate_aniso(
        self,
    ) -> typing.Tuple[np.ndarray, np.ndarray]:
        """Return the ideal anisotropy decay r(t) of the rotation spectrum.

        Returned on the simulation time axis; plotted next to the channels
        (the VM decay itself carries no anisotropy, but r(t) is the sample's).
        """
        from chisurf.core.fluorescence.anisotropy.decay import anisotropy_rt

        x = np.arange(int(max(1, self.n_tac)), dtype=float) * float(self.dt)
        return x, anisotropy_rt(x, self.rotation_spectrum)

    def read(self, filename: str = None, *args, **kwargs) -> chisurf.core.data.DataCurveGroup:
        """Generate a simulated TCSPC decay curve.

        The curve is produced by :meth:`simulate`, i.e. by the same generator
        the simulator panel's **Simulate**/**Add** buttons use, so identical
        settings yield identical data on both paths.

        Parameters
        ----------
        filename : str, optional
            Ignored; the simulated curve uses ``self.sample_name``.

        Returns
        -------
        chisurf.core.data.DataCurveGroup
            Group containing the simulated decay.
        """
        if filename is None:
            filename = self.sample_name
        name = kwargs.get("name", filename)

        if self.polarization != "vm":
            # Polarized simulation: two stacked curves (VV, VH) in one group —
            # the same structure the VV/VH CSV reader produces, so a fit over
            # it becomes a fit group with vv/vh polarizations by position, and
            # the calibration arrives through this reader's g/l1/l2.
            x, vv, vh = self.simulate_channels()
            curves = []
            for suffix, y in (("VV", vv), ("VH", vh)):
                curves.append(
                    chisurf.core.data.DataCurve(
                        x=x,
                        y=y,
                        ey=chisurf.core.fluorescence.tcspc.counting_noise(y),
                        setup=self,
                        data_reader=self,
                        name=f"{name} {suffix}",
                        experiment=self.experiment,
                    )
                )
            return chisurf.core.data.DataCurveGroup(
                curves, experiment=self.experiment, data_reader=self
            )

        x, y = self.simulate()
        # ``data_reader`` is the back-reference a new fit needs to auto-range
        # the curve (``data_reader.autofitrange(data)``). Without it the fit
        # opens at range (0, 0) and fitting is a silent no-op.
        data_set = chisurf.core.data.DataCurve(
            x=x,
            y=y,
            ey=chisurf.core.fluorescence.tcspc.counting_noise(y),
            setup=self,
            data_reader=self,
            name=name,
            experiment=self.experiment,
        )
        return chisurf.core.data.DataCurveGroup(
            [data_set], experiment=self.experiment, data_reader=self
        )

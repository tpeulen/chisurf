from __future__ import annotations

import numpy as np

import chisurf.core.data
import chisurf.core.fluorescence
import chisurf.core.fluorescence.decay
import chisurf.core.fluorescence.tcspc

from chisurf import typing

from .reader import TCSPCReader


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
            sample_name: str = 'TCSPC-Dummy',
            **kwargs
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
        sample_name : str
            Name for the simulated dataset.
        """
        super().__init__(*args, **kwargs)
        self.experiment = kwargs.get('experiment', None)
        if lifetime_spectrum:
            # Mirror the spectrum into the controller's line edit when a GUI
            # controller is attached. Headless/API use has no controller.
            line_edit = getattr(self.controller, 'lineEdit_2', None)
            if line_edit is not None:
                line_edit.setText(','.join([str(x) for x in lifetime_spectrum]))
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

    def read(self, filename: str = None, *args, **kwargs) -> chisurf.core.data.DataCurveGroup:
        """Generate a simulated TCSPC decay curve.

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
        name = kwargs.get('name', filename)
        x = np.arange(self.n_tac) * self.dt
        # The decay is generated through the canonical generator
        # ``core.fluorescence.decay.synthetic_decay`` — the same entry point the
        # interactive Synthetic Decay tool uses — so the exponential/convolution
        # math is shared, not duplicated. ``allow_rise_terms=True`` keeps this
        # acquisition simulator's ability to model rise terms (negative
        # amplitudes) and zero-lifetime components, which the strict default
        # rejects. ``normalize=False`` returns the raw decay, which is then
        # amplitude-normalised (÷Σamp) to reproduce the previous builder call's
        # ``normalize=True`` exactly (by linearity), without mutating the spectrum.
        # ``counting_noise`` is the fitting-weight error model, not shot noise.
        spectrum = np.asarray(self.lifetime_spectrum, dtype=np.float64)
        if spectrum.size >= 2:
            amps = spectrum[0::2]
            taus = spectrum[1::2]
            y = chisurf.core.fluorescence.decay.synthetic_decay(
                n_bins=int(self.n_tac),
                lifetimes=taus,
                amplitudes=amps,
                bin_width=float(self.dt),
                start_bin=0,
                normalize=False,
                allow_rise_terms=True,
            )
            amp_sum = float(np.sum(amps))
            if amp_sum != 0.0:
                y = y / amp_sum
        else:
            y = np.zeros(self.n_tac, dtype=np.float64)
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
            experiment=self.experiment
        )
        return chisurf.core.data.DataCurveGroup(
            [data_set],
            experiment=self.experiment,
            data_reader=self
        )

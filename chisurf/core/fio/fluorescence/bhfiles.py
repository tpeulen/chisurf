"""
Becker & Hickl file readers.

This module provides readers for various Becker & Hickl file formats:
- SdtFile: Reader for .sdt files containing time-correlated single photon counting data
- BeckerHicklSetReader: Reader for .set files containing SPC setup parameters

Both readers provide access to timing parameters and other metadata from Becker & Hickl
SPC hardware. ``SdtFile`` is the one implementation in
:mod:`chisurf.core.fio.fluorescence.sdtfile`, re-exported here: a second copy
of it in this module had fallen behind (it rejected every "Setup & Data" file
and broke on current NumPy) while the SDT import used the maintained one.
"""

import re
from pathlib import Path

from chisurf.core.fio.fluorescence.sdtfile import SdtFile

__all__ = ["SdtFile", "BeckerHicklSetReader"]


class BeckerHicklSetReader:
    """
    Reader for Becker & Hickl SPC .set files.

    Attributes
    ----------
    params : dict
        Dictionary of raw SPC parameters, e.g. {'SP_SYN_FQ': -50.98, 'SP_TAC_TC': 1.83e-11, ...}

    Properties
    ----------
    macro_time_resolution : float
        Sync period in seconds (coarse time bin width).
    micro_time_resolution : float
        TAC conversion factor in nanoseconds (micro-time channel width).
    tac_range : float
        Full TAC span in seconds.
    """

    _LINE_REGEX = re.compile(
        r"SP_([A-Z0-9_]+),"  # parameter name
        r"([FI]),"  # field kind: F=float, I=int
        r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\]"  # value
    )

    def __init__(self, filepath):
        """
        Parameters
        ----------
        filepath : str or Path
            Path to the .set file.
        """
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"File not found: {self.filepath}")
        self.params = {}
        self._read()

    def _read(self):
        """Internal: read file, decode, and parse SP_ parameters."""
        raw = self.filepath.read_bytes()
        text = raw.decode("latin1", errors="ignore")
        for name, t, val in self._LINE_REGEX.findall(text):
            if t == "F":
                self.params[name] = float(val)
            else:  # 'I'
                self.params[name] = int(val)

    def get_param(self, name, default=None):
        """
        Get raw SPC parameter.

        Parameters
        ----------
        name : str
            Parameter name without the "SP_" prefix (e.g. "SYN_FQ").
        default : any
            Value to return if not found.

        Returns
        -------
        float or int or default
        """
        return self.params.get(name, default)

    @property
    def macro_time_resolution(self):
        """
        Coarse (macro) time resolution in seconds:
          Δt_macro = 1 / |SP_SYN_FQ| (SP_SYN_FQ in MHz)
        """
        fq = self.get_param("SYN_FQ")
        if fq is None or fq == 0:
            return None
        return 1.0 / (abs(fq) * 1e6)

    @property
    def micro_time_resolution(self):
        """
        Fine (micro) time resolution in nanoseconds:
          = SP_TAC_TC * 1e9
        """
        tac_tc = self.get_param("TAC_TC")
        if tac_tc is None:
            return None
        return tac_tc * 1e9

    @property
    def tac_range(self):
        """
        Full TAC span in seconds:
          = SP_TAC_R
        """
        return self.get_param("TAC_R")

    def summary(self):
        """Print a quick overview of the key timing parameters."""
        print(f"File: {self.filepath}")
        print(f"  SP_SYN_FQ (MHz):          {self.get_param('SYN_FQ')}")
        print(f"  Macro-time resolution:    {self.macro_time_resolution * 1e9:.3f} ns")
        print(f"  SP_TAC_TC (s):            {self.get_param('TAC_TC'):.3e} s")
        print(f"  Micro-time resolution:    {self.micro_time_resolution:.3f} ns")
        print(f"  SP_TAC_R (s):             {self.tac_range:.3e} s")
        print(f"  TAC full-scale range:     {self.tac_range * 1e9:.3f} ns")

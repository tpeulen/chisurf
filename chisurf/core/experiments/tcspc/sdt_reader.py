"""Headless scientific configuration for the shipped SDT reader surface."""

import json
from pathlib import Path

import numpy as np

from chisurf.core.data import DataCurve, ExperimentDataCurveGroup
from chisurf.core.fio.fluorescence.sdtfile import SdtFile
from chisurf.core.fluorescence.tcspc import counting_noise
from chisurf.core.support.i18n import tr

from .reader import TCSPCReader


class SDTReader(TCSPCReader):
    """Read the same measured SDT curves without retaining a QWidget controller."""

    def __init__(self, *args, curve_nbr=0, filename="", **kwargs):
        """Initialize portable SDT curve-selection configuration."""
        self._sdt = None
        self._filename = ""
        self._curve_nbr = int(curve_nbr)
        super().__init__(*args, **kwargs)
        self.filename = filename

    @property
    def filename(self) -> str:
        """Return the loaded SDT source used by the existing import route."""
        return self._filename

    @filename.setter
    def filename(self, value: str) -> None:
        """Configure a source without requiring file access during restoration."""
        self._filename = str(value or "")
        self._sdt = None

    @property
    def curve_nbr(self) -> int:
        """Return the selected preview index without filtering import."""
        return self._curve_nbr

    @curve_nbr.setter
    def curve_nbr(self, value: int) -> None:
        """Select a measured preview and refresh its file calibration."""
        value = int(value)
        if self._sdt is not None and not 0 <= value < len(self._sdt.data):
            raise IndexError("SDT preview curve is out of range")
        self._curve_nbr = value
        if self._sdt is not None:
            self._update_calibration()

    @property
    def times(self) -> np.ndarray:
        """Return the selected preview's time axis in nanoseconds."""
        if self._sdt is None:
            return np.array([], dtype=np.float64)
        return np.asarray(self._sdt.times[self.curve_nbr] * 1e9, dtype=np.float64)

    @property
    def ph_counts(self) -> np.ndarray:
        """Return the selected measured histogram for preview consumers."""
        if self._sdt is None:
            return np.array([], dtype=np.float64)
        return np.asarray(self._sdt.data[self.curve_nbr][0], dtype=np.float64)

    @property
    def file_info(self) -> str:
        """Return the decoded identification fields shown by the legacy reader."""
        if self._sdt is None:
            return tr("No SDT file loaded.")
        return "\n".join(
            f"{name}: {value.decode('ascii', errors='replace').strip(chr(4))}"
            for name, value in vars(self._sdt.info).items()
        )

    def curve_options(self) -> list[int]:
        """Return exactly the preview indices present in the loaded file."""
        return list(range(len(self._sdt.data))) if self._sdt is not None else []

    def _update_calibration(self) -> None:
        """Update reader calibration from the selected block's descriptor."""
        self.dt = float(self.times[1] - self.times[0])
        measurement = self._sdt.block_measure_info(self.curve_nbr)
        period_ns = float(np.asarray(measurement["rep_t"]).ravel()[0])
        self.rep_rate = 1000.0 / period_ns
        self.excitation_repetition_rate = self.rep_rate

    def load_file(self, filename: str) -> None:
        """Load a file for preview without adding any datasets to the session."""
        if not filename:
            raise ValueError("An SDT filename is required")
        source = SdtFile(filename)
        if not source.data:
            raise ValueError("SDT file has no measured curves")
        self._sdt = source
        self._filename = str(filename)
        if not 0 <= self.curve_nbr < len(source.data):
            self._curve_nbr = 0
        self._update_calibration()

    def view_spec(self):
        """Return the dedicated SDT source, information and calibration form."""
        spec = json.loads(Path(__file__).with_name("tcspc_sdt.view.json").read_text())
        spec["title"] = tr(spec["title"])
        for section in spec["sections"]:
            for declaration in (section, section.get("options", {})):
                for key in ("label", "description"):
                    if key in declaration:
                        declaration[key] = tr(declaration[key])
        return spec

    def read(self, filename=None, **kwargs):
        """Decode SDT measurements explicitly when their source remains available."""
        self.load_file(filename if filename is not None else self.filename)
        sdt = self._sdt
        curves = []
        for index, raw in enumerate(sdt.data):
            x = np.asarray(sdt.times[index] * 1e9, dtype=np.float64)
            y = np.asarray(raw[0], dtype=np.float64)
            measurement = sdt.block_measure_info(index)
            period_ns = float(np.asarray(measurement["rep_t"]).ravel()[0])
            curve = DataCurve(
                x=x,
                y=y,
                ey=counting_noise(decay=y),
                name=f"{self.filename} _ {index}",
                data_reader=self,
            )
            curve.meta_data["excitation_period_ns"] = period_ns
            curves.append(curve)

        # Selection controls the displayed calibration, never the imported set.
        group = ExperimentDataCurveGroup(curves)
        self._annotate_anisotropy_calibration(group)
        return group

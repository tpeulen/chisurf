from __future__ import annotations

import os
import struct
from typing import Dict, Any, List

import numpy as np

import chisurf.core.data
import chisurf.core.fio
import chisurf.core.fluorescence


class PQResReader:
    """
    Reader for PicoQuant SymPhoTime .pqres result files (PTU-style header).
    Parses metadata tags and decodes values into native Python types.
    Provides NumPy curve access.
    """

    tyEmpty8 = 0xFFFF0008
    tyBool8 = 0x00000008
    tyInt8 = 0x10000008
    tyBitSet64 = 0x11000008
    tyColor8 = 0x12000008
    tyFloat8 = 0x20000008
    tyTDateTime = 0x21000008
    tyFloat8Array = 0x2001FFFF
    tyAnsiString = 0x4001FFFF
    tyWideString = 0x4002FFFF
    tyBinaryBlob = 0xFFFFFFFF

    def __init__(self, filepath: str):
        """Initialize PQResReader with a .pqres file path.

        Parameters
        ----------
        filepath : str
            Path to the .pqres file.
        """
        self.filepath = filepath
        self.tags = {}
        self.data_offset = None
        self._read_header()

    def _read_header(self):
        """Read and parse the PQRES file header (tags)."""
        with open(self.filepath, 'rb') as f:
            magic = f.read(8)
            if magic[:7] != b'PQRESLT':
                raise ValueError("Invalid magic. Not a PQRES file.")
            version = f.read(8).rstrip(b'\x00').decode('ascii', errors='ignore')
            self.tags['Version'] = version

            while True:
                tag_data = f.read(48)
                if len(tag_data) < 48:
                    break
                ident_raw, idx, typ, value = struct.unpack('<32s i I Q', tag_data)
                ident = ident_raw.split(b'\x00')[0].decode('ascii', errors='ignore')
                if ident == "Header_End":
                    break
                self.tags[ident] = self._interpret_tag(f, typ, value)

            self.data_offset = f.tell()
            self.tags['_data_offset'] = self.data_offset

    def _interpret_tag(self, f, typ, value):
        """Interpret a single tag value from the binary header.

        Parameters
        ----------
        f : file-like
            Open file handle positioned at tag data.
        typ : int
            Tag type identifier.
        value : int
            Raw tag value or size.

        Returns
        -------
        object
            Decoded Python value.
        """
        if typ == self.tyEmpty8:
            return None
        elif typ == self.tyBool8:
            return bool(value)
        elif typ in (self.tyInt8, self.tyBitSet64, self.tyColor8):
            return int(value)
        elif typ == self.tyFloat8:
            return struct.unpack('<d', struct.pack('<Q', value))[0]
        elif typ == self.tyTDateTime:
            dt = struct.unpack('<d', struct.pack('<Q', value))[0]
            return (dt - 25569) * 86400
        elif typ == self.tyFloat8Array:
            count = value // 8
            data = f.read(count * 8)
            return np.frombuffer(data, dtype='<f8', count=count)
        elif typ == self.tyAnsiString:
            data = f.read(value)
            return data.rstrip(b'\x00').decode('ascii', errors='ignore')
        elif typ == self.tyWideString:
            data = f.read(value)
            return data.decode('utf-16le', errors='ignore').rstrip('\x00')
        elif typ == self.tyBinaryBlob:
            f.seek(value, 1)
            return f"<{value} bytes blob>"
        else:
            return f"<Unsupported type 0x{typ:X}>"

    def get_tag(self, name, default=None):
        """Get a tag value by name.

        Parameters
        ----------
        name : str
            Tag name.
        default : any, optional
            Default value if tag not found.

        Returns
        -------
        any
            Tag value or default.
        """
        return self.tags.get(name, default)

    def list_tags(self):
        """Return non-internal tag names."""
        return [k for k in self.tags if not k.startswith('_')]

    def read_raw_data(self):
        """Read raw binary data starting at the data offset.

        Returns
        -------
        bytes
            Raw data after the header.
        """
        with open(self.filepath, 'rb') as f:
            f.seek(self.data_offset)
            return f.read()

    def get_curves(self) -> Dict[str, Dict[str, Any]]:
        """Extract named X/Y curve data from the tag dictionary.

        Returns
        -------
        dict of str to dict
            Mapping from curve name to dict with 'X', 'Y', 'StdDev', 'Weight'.
        """
        curves = {}
        for k in self.tags:
            if k.endswith("X"):
                base = k[:-1]
                x = self.tags.get(f"{base}X")
                y = self.tags.get(f"{base}Y")
                if isinstance(x, (np.ndarray, list, tuple)) and isinstance(y, (np.ndarray, list, tuple)) and len(x) == len(y):
                    curves[base] = {
                        "label": base,
                        "X": np.array(x),
                        "Y": np.array(y),
                        "StdDev": np.array(self.tags.get(f"{base}StdDevY", [])),
                        "Weight": np.array(self.tags.get(f"{base}WeightY", [])),
                    }
        return curves

    def __repr__(self):
        """Return a string representation of the PQResReader."""
        lines = [f"<PQResReader: {self.filepath}>",
                 f"Version: {self.tags.get('Version')}",
                 f"Data offset: {self.data_offset}",
                 f"Tags ({len(self.list_tags())}):"]
        for k in self.list_tags():
            v = self.tags[k]
            v_str = repr(v)
            lines.append(f"  {k}: {v_str[:100]}{'...' if len(v_str) > 100 else ''}")
        return "\n".join(lines)


#: Suffixes SymPhoTime uses for the per-point error and weight of a curve.
_COMPANION_SUFFIXES = ("StdDev", "Weight")

#: Substrings marking a tag as a correlation curve rather than, say, the
#: overall TCSPC decay that the same result file also carries.
_CORRELATION_MARKERS = ("FCS", "FCCS")


def _is_correlation_curve(name: str, curves: dict) -> bool:
    """Whether *name* is a correlation curve rather than a companion or a decay.

    Every array in the file is stored as a ``<base>X`` / ``<base>Y`` pair, so
    the per-point standard deviations and weights look exactly like curves. A
    companion is recognised by its suffix, and the remaining tags are kept only
    when they name a correlation — the same file also holds the overall decay,
    which is 25 000 points of TCSPC and not an FCS curve.
    """
    if any(name.endswith(suffix) for suffix in _COMPANION_SUFFIXES):
        return False
    return any(marker in name for marker in _CORRELATION_MARKERS)


def _companion(curves: dict, base: str, suffix: str, size: int):
    """Return the ``StdDev``/``Weight`` array belonging to *base*, or ``None``.

    The cross-correlation is stored as ``VarFCCSCurve`` while its companions
    are named ``VarFCSCurve...`` — one C short — so the direct name is tried
    first and that spelling second.
    """
    for candidate in (f"{base}{suffix}", f"{base.replace('FCCS', 'FCS')}{suffix}"):
        curve = curves.get(candidate)
        if curve is None:
            continue
        values = np.asarray(curve["Y"], dtype=np.float64)
        if values.size == size:
            return values
    return None


def read_pqres_fcs(filename: str, verbose: bool = False, **kwargs) -> list:
    """Read the FCS curves of a PicoQuant SymPhoTime ``.pqres`` result file.

    Returns the same shape every other FCS reader returns — one dict per
    correlation curve — so ``read_fcs`` builds the curves, applies the shared
    weight handling and attaches the reader, exactly as it does for the text
    formats. Returning ready-made ``DataCurve`` objects instead (as this
    function used to) meant the dispatcher's curve builder was handed something
    it could not read, and a ``.pqres`` file could not be loaded at all.

    Parameters
    ----------
    filename : str
        Path to the ``.pqres`` file.
    verbose : bool, optional
        Accepted for signature compatibility with the other readers.
    **kwargs
        Ignored; present so the dispatcher can pass its common arguments.

    Returns
    -------
    list of dict
        One entry per curve, with ``correlation_times``,
        ``correlation_amplitudes``, ``correlation_amplitude_weights``,
        ``measurement_id`` and ``filename``.
    """
    reader = PQResReader(filename)
    curves = reader.get_curves()
    out = []
    for name in sorted(curves):
        if not _is_correlation_curve(name, curves):
            continue
        curve = curves[name]
        x = np.asarray(curve["X"], dtype=np.float64)
        y = np.asarray(curve["Y"], dtype=np.float64)
        std = _companion(curves, name, "StdDev", y.size)
        # SymPhoTime stores the per-point standard deviation; the FCS stack
        # weights by 1/sigma. Where it is absent or zero the dispatcher falls
        # back to Suren photon-noise weights.
        if std is not None and np.any(std > 0):
            weights = np.zeros_like(std)
            np.divide(1.0, std, out=weights, where=std > 0)
        else:
            weights = np.ones_like(y)
        out.append({
            "filename": filename,
            "measurement_id": str(name),
            "correlation_times": x,
            "correlation_amplitudes": y,
            "correlation_amplitude_weights": weights,
            "acquisition_time": reader.get_tag("MeasDesc_AcquisitionTime", 0.0),
        })
    return out


def read_pqres_tcspc(filename: str, data_reader: chisurf.core.experiments.core.reader.ExperimentReader = None, 
                    experiment: chisurf.core.experiments.core.experiment.Experiment = None, 
                    dt: float = 1.0, rebin: typing.Tuple[int, int] = (1, 1), **kwargs) -> chisurf.core.data.DataCurveGroup:
    """
    Read a PicoQuant SymPhoTime .pqres TCSPC result file and return a DataCurveGroup.
    For TCSPC data, the x values are multiplied by 1e9 to convert from seconds to nanoseconds.
    Applies binning according to the rebin parameter.

    Parameters
    ----------
    filename : str
        Path to the .pqres file
    data_reader : chisurf.core.experiments.core.reader.ExperimentReader, optional
        Data reader to use for reading the file
    experiment : chisurf.core.experiments.core.experiment.Experiment, optional
        Experiment to associate with the data
    dt : float, optional
        Time resolution in nanoseconds, by default 1.0
    rebin : tuple of int, optional
        Rebinning factors for x and y axes, by default (1, 1)
    **kwargs
        Additional keyword arguments to pass to the DataCurve constructor

    Returns
    -------
    chisurf.core.data.DataCurveGroup
        A DataCurveGroup containing all curves in the .pqres file
    """
    # Import here to avoid circular imports
    import chisurf.core.data
    from chisurf import typing

    # Load data
    rebin_x, rebin_y = rebin

    reader = PQResReader(filename)
    curves = reader.get_curves()

    # Create a DataCurveGroup to hold all curves
    curve_group = chisurf.core.data.DataCurveGroup([])

    # Add each curve to the group
    for name, curve_data in curves.items():
        # Convert x values from seconds to nanoseconds (multiply by 1e9)
        x = curve_data["X"] * 1e9
        y = curve_data["Y"]

        # Apply rebinning if needed
        if rebin_y > 1:
            # Calculate new length after rebinning
            new_length = len(y) // rebin_y
            # Reshape and sum along the rebinning axis
            y = y[:new_length * rebin_y].reshape(-1, rebin_y).sum(axis=1)
            # Adjust time axis
            x = x[:new_length * rebin_y:rebin_y]

        # Use zeros for x error
        ex = np.zeros_like(x)
        # For TCSPC data, use Poisson error (sqrt(y)) as this is appropriate for photon counting
        ey = np.sqrt(y)

        # Create a DataCurve for this curve
        data_curve = chisurf.core.data.DataCurve(
            x=x, 
            y=y, 
            ex=ex, 
            ey=ey,
            filename=filename,
            data_reader=data_reader,
            experiment=experiment,
            name=name,
            load_filename_on_init=False,
            **kwargs
        )

        # Add the curve to the group
        curve_group.append(data_curve)

    return curve_group

"""
The :py:mod:`chisurf.core.fio` module contains all classes, functions and modules relevant for file input and outputs.
In particular three kinds of file-types are handled:

1. Comma-separated files :py:mod:`chisurf.core.fio.ascii`
2. PDB-file :py:mod:`chisurf.core.fio.pdb`
3. TTTR-files containing photon data :py:mod:`chisurf.core.fio.photons`
4. XYZ-files containing coordinates :py:mod:`chisurf.core.fio.xyz`
5. DX-files containing densities :py:mod:`chisurf.core.fio.dx`
6. SDT-files containing time-resolved fluorescence decays :py:mod:`chisurf.core.fio.bhfiles`

"""

import importlib
import lzma
from typing import Any

import numpy as np

from .zipped import *

#: Attributes served lazily by :func:`__getattr__`, mapped to the submodule
#: that defines them. Importing the reader packages eagerly would pull the
#: whole fluorescence/pandas/scipy stack into every consumer of this package
#: -- including light ones such as :mod:`chisurf.core.fio.ascii` -- which
#: dominated GUI startup time.
_LAZY_SUBMODULES = ("fluorescence", "vv_vh")
_LAZY_ATTRIBUTES = {
    "write_vv_vh": "vv_vh",
    "read_vv_vh": "vv_vh",
}


def __getattr__(name: str) -> Any:
    """Import reader submodules and their exports on first attribute access."""
    if name in _LAZY_SUBMODULES:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    if name in _LAZY_ATTRIBUTES:
        module = importlib.import_module(f"{__name__}.{_LAZY_ATTRIBUTES[name]}")
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List module contents including the lazily-imported names."""
    return sorted({*globals(), *_LAZY_SUBMODULES, *_LAZY_ATTRIBUTES})


def compress_numpy_array(array):
    """
    Compresses a NumPy array and returns a dictionary containing the compressed data,
    shape, and data type information.

    Parameters
    - array: NumPy array to be compressed.

    Returns
    - Dictionary containing compressed array, shape, and dtype.
    """
    # Convert the array to bytes
    array_bytes = array.tobytes()

    # Compress the bytes using lzma
    compressed_bytes = lzma.compress(array_bytes)

    # Convert compressed bytes to a base64-encoded string for JSON
    compressed_string = compressed_bytes.hex()

    # Create a dictionary to store the compressed data
    compressed_data = {
        "compressed_array": compressed_string,
        "shape": array.shape,
        "dtype": str(array.dtype),
    }

    return compressed_data


def decompress_numpy_array(compressed_data):
    """
    Decompresses a NumPy array from the compressed data dictionary.

    Parameters
    - compressed_data: Dictionary containing compressed array, shape, and dtype.

    Returns
    - Reconstructed NumPy array.
    """
    # Convert the base64-encoded string back to bytes
    compressed_string = compressed_data["compressed_array"]
    compressed_bytes = bytes.fromhex(compressed_string)

    # Decompress the bytes using lzma
    decompressed_bytes = lzma.decompress(compressed_bytes)

    # Convert the decompressed bytes back to a NumPy array
    shape = compressed_data["shape"]
    dtype = np.dtype(compressed_data["dtype"])
    reconstructed_array = np.frombuffer(decompressed_bytes, dtype=dtype).reshape(shape)

    return reconstructed_array

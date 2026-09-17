"""tttrlib must use the *environment's* HDF5, not a second one.

``find_package(HDF5)`` also looks for an installed HDF5 **CMake config
package**, which on macOS finds Homebrew's and outranks the environment. The
extension then carries its own HDF5 into a process that already loads this
environment's (through h5py/PyTables), and whichever initialises first wins:
writing a Photon-HDF5 file aborted the whole interpreter — SIGABRT, no Python
traceback, taking the test session with it — unless something happened to
import h5py first. The failure followed *import order*, so it looked flaky.

These tests pin the runtime, not the build: they fail on a tttrlib that links a
foreign HDF5, whichever way it got built.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import sysconfig

import pytest

tttrlib = pytest.importorskip("tttrlib")


def test_writing_photon_hdf5_does_not_abort_without_h5py(tmp_path):
    """A fresh interpreter that imports only tttrlib can write an HDF5 file.

    Run out-of-process on purpose: the failure this guards against is a native
    ``abort()``, which no ``pytest.raises`` can catch, and it only appears when
    tttrlib's HDF5 initialises first.
    """
    script = (
        "import tttrlib, numpy as np, sys\n"
        "t = tttrlib.TTTR()\n"
        "n = 100\n"
        "m = np.arange(n, dtype=np.uint64)\n"
        "c = np.zeros(n, dtype=np.int8)\n"
        "t.append_events(m, np.zeros(n, dtype=np.uint16), c, c, False, 0)\n"
        f"t.write_hdf_file(r'{tmp_path / 'probe.photon.h5'}')\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=300
    )
    assert result.returncode == 0, (
        "tttrlib aborted while writing Photon-HDF5 with no other HDF5 consumer "
        f"imported (exit {result.returncode}); it is probably linked against a "
        f"second HDF5.\nstdout: {result.stdout}\nstderr: {result.stderr[-2000:]}"
    )
    assert (tmp_path / "probe.photon.h5").exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="otool is macOS-only")
def test_tttrlib_links_the_environment_hdf5():
    """The extension's HDF5 must live in this environment, not in /opt/homebrew."""
    import _tttrlib

    otool = subprocess.run(["otool", "-L", _tttrlib.__file__], capture_output=True, text=True)
    if otool.returncode != 0:  # no developer tools: the runtime test still covers it
        pytest.skip("otool unavailable")

    hdf5_lines = [ln.strip() for ln in otool.stdout.splitlines() if "hdf5" in ln.lower()]
    assert hdf5_lines, "tttrlib links no HDF5 at all"

    prefix = pathlib.Path(sysconfig.get_paths()["data"]).resolve()
    for line in hdf5_lines:
        path = line.split(" (")[0]
        if path.startswith("@rpath/") or path.startswith("@loader_path/"):
            continue  # resolved through the module's rpath, which points here
        assert pathlib.Path(path).resolve().is_relative_to(prefix), (
            f"tttrlib links an HDF5 outside this environment: {path!r}. Two HDF5 "
            "runtimes in one process abort on the first Photon-HDF5 write; "
            "rebuild with -DHDF5_ROOT=<prefix> -DHDF5_NO_FIND_PACKAGE_CONFIG_FILE=TRUE."
        )

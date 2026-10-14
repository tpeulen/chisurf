"""What the workspace says about the machine it runs on, without Qt.

The lines the Qt window painted as a watermark over its empty workspace (OS, RAM,
Python, ChiSurf and library versions, thread and tttrlib environment, the log level)
and the process's CPU and memory use. The emtk shell draws them in its Start
document (:meth:`chisurf.emtk.main_app.EmtkShellApp._draw_start`). ``psutil`` is
optional: without it the RAM, CPU and memory figures are left out, never raised.
"""

from __future__ import annotations

import datetime
import logging
import os
import platform
from importlib import metadata


def _version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except Exception:  # noqa: BLE001 - not installed, or another name
        return None


def _ram() -> str | None:
    try:
        import psutil

        return f"{psutil.virtual_memory().total / 1024.0**3:.1f} GB"
    except Exception:  # noqa: BLE001 - psutil is optional
        return None


def system_info_lines() -> list[str]:
    """The machine, the versions and the environment, a line each.

    Returns
    -------
    list of str
        ``"OS: …"``, ``"RAM: …"``, ``"Python: …"``, ``"Date: …"``, ``"ChiSurf: …"``,
        the numpy and tttrlib versions, the thread and tttrlib environment variables
        that are set, and ``"Log level: …"``.
    """
    import chisurf

    name, release = platform.system(), platform.release()
    if name == "Windows" and (release == "11" or platform.version().startswith("10.0.26")):
        os_info = f"Windows 11 ({platform.version()})"
    else:
        os_info = f"{name} {release}".strip() or "Unknown OS"
    lines = [f"OS: {os_info}"]
    ram = _ram()
    if ram:
        lines.append(f"RAM: {ram}")
    lines.append(f"Python: {platform.python_version()}")
    lines.append(f"Date: {datetime.date.today():%Y-%m-%d}")
    lines.append(f"ChiSurf: {getattr(chisurf, '__version__', '?')}")
    for package in ("numpy", "tttrlib", "emtk"):
        version = _version(package)
        if version:
            lines.append(f"{package}: {version}")
    for title, names in (
        ("Env(tttr)", ("TTTRLIB_VERBOSE", "TTTRLIB_DATA", "TTTRLIB_USE_OPENMP", "TTTRLIB_NUM_THREADS")),
        ("Threads", ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "MKL_THREADING_LAYER")),
    ):
        short = {"MKL_NUM_THREADS": "MKL", "OMP_NUM_THREADS": "OMP", "MKL_THREADING_LAYER": "MKL_LAYER"}
        parts = [f"{short.get(n, n)}={os.environ[n]}" for n in names if os.environ.get(n)]
        if parts:
            lines.append(f"{title}: " + ", ".join(parts))
    level = logging.getLogger().getEffectiveLevel()
    lines.append(f"Log level: {logging.getLevelName(level)} ({level})")
    return lines


def process_usage() -> tuple[float, float] | None:
    """``(cpu percent, resident memory in MB)`` of this process and its children.

    Returns
    -------
    tuple of float or None
        ``None`` when ``psutil`` is not installed. The CPU figure is psutil's
        non-blocking reading (the share since the previous call; 0 on the first).
    """
    try:
        import psutil

        process = psutil.Process()
        members = [process]
        try:
            members += process.children(recursive=True)
        except Exception:  # noqa: BLE001
            pass
        cpu = mem = 0.0
        for member in members:
            try:
                cpu += member.cpu_percent(interval=None)
                mem += member.memory_info().rss / 1024.0**2
            except Exception:  # noqa: BLE001 - a child that ended
                continue
        return cpu, mem
    except Exception:  # noqa: BLE001 - psutil is optional
        return None


__all__ = ["process_usage", "system_info_lines"]

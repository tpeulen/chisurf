"""The analysis report of a burst session's calibration: everything the UI does not show.

Data Selection shows the key numbers (G, V_eff, τ_D, w0, s, brightness, B, IRF width); the full
record -- which files (with their hashes), which dye and where its D comes from, the correlation
fit with its uncertainties and χ²r, G with its spread, the buffer rates, the IRF, and what was
estimated from the measurement for want of a file -- is :func:`build_report`. It is the workflow
context's ``calibration_report`` and is written into each measurement's analysis container as a
``calibration`` JSON object (:func:`write_report`, read back with :func:`read_report`), derived
from the measurement's photon streams, so it is found with the bursts it belongs to.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

__all__ = ["REPORT_NAME", "SCHEMA", "build_report", "read_report", "write_report"]

#: The name of the report object in a measurement's container.
REPORT_NAME = "burst_calibration"
#: The report's format, for a reader to check.
SCHEMA = "chisurf.burst_calibration/1"

#: What a volume fit records (and its uncertainties, ``<key>_err``).
_FIT_KEYS = (
    "detector", "D_um2_s", "N", "tau_d_ms", "s", "offset", "w0_um", "z0_um", "veff_fl",
    "concentration_nM", "count_rate_khz", "brightness_khz", "chi2r", "fit_range_ms",
)


@lru_cache(maxsize=256)
def _sha256(path: str, size: int, mtime: float) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_entry(path: str | Path) -> dict[str, Any]:
    """``{"path", "name", "size", "sha256"}`` of a file (no hash when it cannot be read)."""
    p = Path(path)
    try:
        stat = p.stat()
        return {"path": str(p), "name": p.name, "size": int(stat.st_size),
                "sha256": _sha256(str(p), int(stat.st_size), float(stat.st_mtime))}
    except OSError:
        return {"path": str(p), "name": p.name, "size": None, "sha256": None}


def build_report(
    calibration: Mapping | None,
    rows: Mapping[str, str],
    setup: Mapping | None,
    *,
    estimated: Mapping[str, str] | None = None,
    applied_g: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The complete calibration record of a session.

    Parameters
    ----------
    calibration : mapping
        :func:`..samples.calibrate`'s result.
    rows : mapping
        ``{path: row}`` of every file of the session.
    setup : mapping
        The detector setup.
    estimated : mapping, optional
        What was estimated rather than measured (``BurstWorkflowContext.estimated``).
    applied_g : mapping, optional
        ``{detector: G written to the setup}``, or ``"edited by hand"`` where the user's own value
        was kept.
    """
    from chisurf.core.fluorescence.dyes import get_dye

    from .samples import dye_citation

    calibration = dict(calibration or {})
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "setup_name": str((setup or {}).get("setup_name") or ""),
        "files": [
            {**file_entry(path), "role": row}
            for path, row in sorted(rows.items(), key=lambda kv: kv[1])
        ],
        "buffer": dict(calibration.get("buffer") or {}),
        "irf": dict(calibration.get("irf") or {}),
        "colours": {},
        "estimated": dict(estimated or {}),
        "errors": list(calibration.get("errors") or []),
    }
    for colour, entry in (calibration.get("colours") or {}).items():
        dye = dict(entry.get("dye") or {})
        dye.pop("_for", None)
        db = get_dye(dye.get("dye", "")) if dye.get("dye") else None
        volume = dict(entry.get("volume") or {})
        fit = {k: volume[k] for k in _FIT_KEYS if k in volume}
        fit.update({f"{k}_err": volume[f"{k}_err"] for k in _FIT_KEYS if f"{k}_err" in volume})
        g = {
            det: {k: v for k, v in value.items() if k in ("g", "std", "sem", "region",
                                                          "background_region", "from", "counts")}
            for det, value in (entry.get("g_factor") or {}).items()
        }
        report["colours"][colour] = {
            "files": list(entry.get("files") or []),
            "dye": dye,
            "D_um2_s": entry.get("D_um2_s"),
            "D_source": entry.get("D_source", ""),
            "D_citation": dye_citation(db),
            "D25_um2_s": (db or {}).get("d25_um2_s"),
            "g_factor": g,
            "g_applied": {d: (applied_g or {}).get(d) for d in g},
            "volume_fit": fit,
        }
    return json.loads(json.dumps(report, default=float))


def write_report(source: str | Path, report: Mapping, out_dir: str | Path | None = None) -> str:
    """Write *report* into the container of the measurement *source* (replacing the one written
    before), derived from its photon streams; returns the container's path."""
    from chisurf.core.fio.fluorescence.burst_container import open_measurement

    payload = json.dumps(report, indent=1, sort_keys=True).encode("utf-8")
    with open_measurement(source, out_dir, raw_data="sidecar") as m:
        for obj in list(m._f.objects()):
            if getattr(obj, "name", "") == REPORT_NAME:
                m._f.remove(obj.uid)
        m.put_blob(
            REPORT_NAME,
            payload,
            artifact_kind="calibration_data",
            data_format="json",
            operation_type="calibration",
            parameters={"schema": SCHEMA},
            derived_from=m.instrument_uids or m.instrument_uid,
            mime_type="application/json",
        )
        return str(m.path)


def read_report(container: str | Path) -> dict[str, Any]:
    """The calibration report of a measurement's container (``{}``: none written)."""
    from chisurf.core.fio.pto import Measurement

    with Measurement.open(container) as m:
        for obj in m._f.objects():
            if getattr(obj, "name", "") == REPORT_NAME:
                return json.loads(m.get_blob(obj.uid).decode("utf-8"))
    return {}

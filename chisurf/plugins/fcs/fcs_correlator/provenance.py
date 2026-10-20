"""The correlator's settings record, and reproducing a correlation from it and the raw photons.

The workflow describes the photons it hands the correlator (:func:`photon_record`: the files, each file's time
regions, how the files were read, the photon filter); Correlate adds the correlator's own settings
(:func:`settings_of`); the merger adds which pieces it averaged and writes the record beside the ``.cor``
(:func:`chisurf.core.fluorescence.fcs.merge.save_mean_correlation`). :func:`reproduce` runs the same workflow again,
headless, from that file::

    python -m chisurf.plugins.fcs.fcs_correlator.provenance merged.cor.json -o again.cor
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

import numpy as np

from chisurf.core.fluorescence.fcs.provenance import complete_inputs, new_record, read_settings, sha256

#: Settings attributes are the models' public scalar attributes; these are views, not inputs.
_NOT_SETTINGS = {"range_lo", "range_hi", "mcs_bin_width"}


def settings_of(model) -> dict[str, Any]:
    """The public scalar attributes of a settings model (what its form edits)."""
    return {
        k: v
        for k, v in vars(model).items()
        if not k.startswith("_")
        and k not in _NOT_SETTINGS
        and isinstance(v, (bool, int, float, str))
    }


def apply_settings(model, settings: dict) -> None:
    """Set the attributes of *settings* that *model* has (an unknown key is a newer record's, and is skipped)."""
    for key, value in (settings or {}).items():
        if hasattr(model, key) and not key.startswith("_"):
            setattr(model, key, value)


def photon_record(workflow, files: list[str], filter_model=None) -> dict[str, Any]:
    """What the correlator was given: *files* (as read), their regions, the reading setup and the filter.

    *filter_model* is the photon filter that selected the photons, ``None`` when the raw photons were correlated.
    Checksums are added when the record is written (:func:`chisurf.core.fluorescence.fcs.provenance.complete_inputs`), off the drawing thread.
    """
    context = workflow.context
    return new_record(
        "photons",
        inputs=[{"path": str(f), "regions": [list(r) for r in workflow.regions.get(f)]} for f in files],
        reading={
            "file_type": workflow.file_type,
            "detector_settings": context.detector_settings,
            "channel_defs": context.channel_defs,
        },
        photon_filter=settings_of(filter_model) if filter_model is not None else None,
    )


def correlator_record(model) -> dict[str, Any]:
    """The correlator settings of *model* at Correlate, with the lifetime filters it used."""
    lifetime = None
    if model._lifetime_filters is not None:
        path = getattr(model, "_filter_path", "") or ""
        lifetime = {
            "path": str(path),
            "sha256": sha256(path) if path and pathlib.Path(path).is_file() else "",
            "species_a": int(model._species_a),
            "species_b": int(model._species_b),
        }
    return {**settings_of(model), "lifetime_filters": lifetime}


def _chosen(curves: list[dict], chunks) -> list[dict]:
    if chunks is None:
        return list(curves)
    wanted = list(chunks)
    return [c for i, c in enumerate(curves) if c.get("chunk", i) in wanted]


def reproduce(settings, verify: bool = True) -> tuple[dict, list[dict]]:
    """``(merged, curves)`` computed again from a settings record (a dict, a ``.cor.json`` or its ``.cor``).

    With *verify*, a raw file whose checksum differs from the record's is refused: it is not the measurement
    the result was computed from.
    """
    from chisurf.core.fluorescence.fcs.merge import compute_average_correlations

    from .correlator_model import CorrelatorSettingsModel
    from .filter_model import FilterSettingsModel
    from .workflow import FcsWorkflow

    record = settings if isinstance(settings, dict) else read_settings(settings)
    if record.get("source") != "photons":
        raise ValueError(
            f"This result was computed from {record.get('source')!r}, not from photons: there is nothing to "
            "correlate again."
        )
    inputs = record.get("inputs", [])
    files = [entry["path"] for entry in inputs]
    for entry in inputs:
        if not pathlib.Path(entry["path"]).is_file():
            raise FileNotFoundError(f"Raw photon file not found: {entry['path']}")
        if verify and entry.get("sha256") and sha256(entry["path"]) != entry["sha256"]:
            raise ValueError(f"{entry['path']} is not the file the result was computed from (checksum differs).")
    workflow = FcsWorkflow()
    reading = record.get("reading", {})
    workflow.context.detector_settings = dict(reading.get("detector_settings") or {})
    workflow.context.channel_defs = dict(reading.get("channel_defs") or {})
    photon_filter = record.get("photon_filter")
    workflow.set_files(files, use_filter=photon_filter is not None, use_merger=True)
    for entry in inputs:
        workflow.regions.set(entry["path"], [tuple(r) for r in entry.get("regions", [])])
    filter_model = FilterSettingsModel()
    if photon_filter is not None:
        apply_settings(filter_model, photon_filter)
        workflow.load_files_into_filter(filter_model)
    correlator = CorrelatorSettingsModel()
    workflow.apply_to_correlator(correlator, filter_model)
    settings_ = dict(record.get("correlator") or {})
    lifetime = settings_.pop("lifetime_filters", None)
    apply_settings(correlator, settings_)
    if lifetime:
        if verify and lifetime.get("sha256") and sha256(lifetime["path"]) != lifetime["sha256"]:
            raise ValueError(f"{lifetime['path']} is not the filter file the result used (checksum differs).")
        correlator.load_lifetime_filter_file(lifetime["path"])
        correlator._species_a, correlator._species_b = lifetime["species_a"], lifetime["species_b"]
    message = correlator.correlate_data()
    curves = list(correlator._correlations)
    if not curves:
        raise ValueError(f"The correlation came out empty: {message}")
    chosen = _chosen(curves, (record.get("merge") or {}).get("chunks"))
    return compute_average_correlations(chosen or curves), curves


def main(argv=None) -> int:
    """Reproduce a ``.cor`` from its settings file; optionally write it, and compare with the recorded one."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("settings", help="The settings file (<name>.cor.json) or the .cor beside it.")
    parser.add_argument("-o", "--output", help="Write the reproduced correlation here (with its own settings file).")
    parser.add_argument("--no-verify", action="store_true", help="Do not refuse raw files whose checksum differs.")
    args = parser.parse_args(argv)
    from chisurf.core.fluorescence.fcs.merge import save_mean_correlation
    from chisurf.core.fluorescence.fcs.provenance import settings_path

    path = pathlib.Path(args.settings)
    record = read_settings(path)
    merged, curves = reproduce(record, verify=not args.no_verify)
    print(f"{len(curves)} piece(s) correlated, {len(_chosen(curves, record.get('merge', {}).get('chunks')))} merged.")
    original = path if path.suffix.lower() == ".cor" else path.with_name(record.get("output", {}).get("file", ""))
    if original.is_file() and original != settings_path(original):
        y_old = np.loadtxt(str(original), delimiter="\t")[:, 1]
        y_new = np.array([float(f"{v:.5g}") for v in merged["y"]])  # as the .cor writes it
        n = min(len(y_old), len(y_new))
        print(f"max |ΔG| against {original.name}: {np.max(np.abs(y_old[:n] - y_new[:n])):.3g}")
    if args.output:
        save_mean_correlation(merged, pathlib.Path(args.output), complete_inputs(record))
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

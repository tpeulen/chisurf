"""CLI entry point of the burst-fusion step.

``csc fusion curve`` reports the same-molecule probability of a burst folder and
what a threshold would fuse, without writing anything; ``csc fusion fuse``
writes the fused burst folder. The two share every option, so a threshold can be
scanned first and applied second.
"""

from __future__ import annotations

import json
import pathlib

import click

from chisurf.plugins.burst.burst_fusion.api.models import FusionSettings


def _settings(
    threshold, tau_min, tau_max, bins, min_pairs, max_gap, max_group, per_file, file_type
):
    """Build :class:`FusionSettings` from the shared CLI options."""
    return FusionSettings(
        threshold=threshold,
        tau_min_s=tau_min,
        tau_max_s=tau_max,
        n_bins=bins,
        min_pairs=min_pairs,
        max_gap_ms=max_gap,
        max_group=max_group,
        pool_measurements=not per_file,
        file_type=file_type,
    )


def _channel_definition(detectors_file: str | None, setup_name: str | None):
    """Resolve the detector/window definition the fused table is rebuilt from.

    A burst folder written by the current burst selection records this in its own
    reading manifest and nothing has to be given here. Older folders do not, and
    then the definition has to come from somewhere: a JSON file, or one of the
    saved detector setups by name — the same setups the GUI offers.

    Returns
    -------
    detectors, windows : dict or None
        ``None`` means "use whatever the folder recorded".
    """
    if detectors_file:
        payload = json.loads(pathlib.Path(detectors_file).read_text(encoding="utf-8"))
        return payload.get("detectors") or payload, payload.get("windows") or {}
    if setup_name:
        from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import (
            load_detector_setups,
        )

        setup = (load_detector_setups().get("setups") or {}).get(setup_name)
        if not setup:
            raise click.ClickException(f"no saved detector setup named {setup_name!r}")
        return setup.get("detectors") or {}, setup.get("windows") or {}
    return None, None


def _shared_options(function):
    """Attach the options both sub-commands take."""
    function = click.option(
        "--threshold",
        default=0.5,
        show_default=True,
        type=float,
        help="Same-molecule probability required to fuse two bursts.",
    )(function)
    function = click.option(
        "--tau-min",
        default=1e-4,
        show_default=True,
        type=float,
        help="Shortest lag of the P_same estimate (s).",
    )(function)
    function = click.option(
        "--tau-max",
        default=1.0,
        show_default=True,
        type=float,
        help="Longest lag of the P_same estimate (s); also caps the fusion window.",
    )(function)
    function = click.option(
        "--bins",
        default=60,
        show_default=True,
        type=int,
        help="Logarithmic lag bins.",
    )(function)
    function = click.option(
        "--min-pairs",
        default=3,
        show_default=True,
        type=int,
        help="Burst pairs a lag bin needs before it may end the fusion window.",
    )(function)
    function = click.option(
        "--max-gap",
        default=10.0,
        show_default=True,
        type=float,
        help="Hard ceiling on the gap fusion may bridge, in ms (0 = none). Caps "
        "the probability window so a fused burst does not swallow background.",
    )(function)
    function = click.option(
        "--max-group",
        default=0,
        show_default=True,
        type=int,
        help="Largest number of bursts one fused burst may contain (0 = no limit).",
    )(function)
    function = click.option(
        "--per-file",
        is_flag=True,
        help="Estimate P_same per measurement instead of pooling the folder.",
    )(function)
    function = click.option(
        "--file-type",
        default="auto",
        show_default=True,
        help="TTTR container type of the raw data (the folder's manifest wins).",
    )(function)
    return function


@click.group(name="fusion")
def cli():
    """Fuse bursts that the same molecule produced."""


@cli.command()
@click.argument("analysis_folder", type=click.Path(exists=True, file_okay=False))
@_shared_options
@click.option("--json", "as_json", is_flag=True, help="Print the full result as JSON.")
def curve(
    analysis_folder,
    threshold,
    tau_min,
    tau_max,
    bins,
    min_pairs,
    max_gap,
    max_group,
    per_file,
    file_type,
    as_json,
):
    """Report P_same and what THRESHOLD would fuse in ANALYSIS_FOLDER."""
    from chisurf.plugins.burst.burst_fusion.core.fusion import analyze

    settings = _settings(
        threshold, tau_min, tau_max, bins, min_pairs, max_gap, max_group, per_file, file_type
    )
    result = analyze(pathlib.Path(analysis_folder), settings)
    if as_json:
        click.echo(json.dumps(result.statistics, indent=2, default=str))
        return

    stats = result.statistics
    window = result.window
    click.echo(
        f"Bursts:            {stats['n_bursts_before']} in {stats['n_measurements']} measurement(s)"
    )
    click.echo(
        f"P_same >= {threshold:.2f}:   tau <= {window.tau_max_s * 1e3:.3f} ms"
        + ("" if window.resolved else "  (unresolved: the curve never crossed the threshold)")
    )
    click.echo(
        f"Gaps fused:        <= {result.tau_used_s * 1e3:.3f} ms"
        + ("  (capped by --max-gap)" if stats["gap_capped"] else "")
    )
    click.echo(
        f"After fusion:      {stats['n_bursts_after']} bursts "
        f"({stats['n_fused_groups']} fused, largest {stats['largest_group']})"
    )
    ratio = stats.get("proximity_ratio", {})
    if ratio.get("before", {}).get("n"):
        click.echo(
            "Proximity ratio:   "
            f"{ratio['before']['mean']:.4f} +/- {ratio['before']['std']:.4f}"
            f"  ->  {ratio['after']['mean']:.4f} +/- {ratio['after']['std']:.4f}"
        )
    click.echo(
        "Photons/burst:     "
        f"{stats['photons']['before']['mean']:.1f}  ->  {stats['photons']['after']['mean']:.1f}"
    )
    click.echo(
        "Duration (ms):     "
        f"{stats['duration_ms']['before']['mean']:.3f}  ->  {stats['duration_ms']['after']['mean']:.3f}"
    )


@cli.command()
@click.argument("analysis_folder", type=click.Path(exists=True, file_okay=False))
@_shared_options
@click.option("--output", "-o", type=click.Path(), help="Target folder for the fused bursts.")
@click.option(
    "--data-folder",
    type=click.Path(exists=True, file_okay=False),
    help="Where the raw measurements live (default: the analysis folder's parent).",
)
@click.option(
    "--detectors",
    "detectors_file",
    type=click.Path(exists=True, dir_okay=False),
    help="JSON detector/window definition, for a folder written before "
    "burst analyses recorded their own reading manifest.",
)
@click.option(
    "--setup", "setup_name", help="Name of a saved detector setup to use instead of --detectors."
)
def fuse(
    analysis_folder,
    threshold,
    tau_min,
    tau_max,
    bins,
    min_pairs,
    max_gap,
    max_group,
    per_file,
    file_type,
    output,
    data_folder,
    detectors_file,
    setup_name,
):
    """Write the fused bursts of ANALYSIS_FOLDER as a new burst folder."""
    from chisurf.plugins.burst.burst_fusion.core.fusion import fuse_folder

    settings = _settings(
        threshold, tau_min, tau_max, bins, min_pairs, max_gap, max_group, per_file, file_type
    )
    detectors, windows = _channel_definition(detectors_file, setup_name)
    result = fuse_folder(
        pathlib.Path(analysis_folder),
        settings,
        output_folder=output,
        detectors=detectors,
        windows=windows,
        data_folder=data_folder,
    )
    stats = result["statistics"]
    click.echo(
        f"Fused {stats['n_bursts_before']} -> {stats['n_bursts_after']} bursts "
        f"(gaps <= {result['tau_used_s'] * 1e3:.3f} ms)"
    )
    for stem, counts in result["per_measurement"].items():
        click.echo(f"  {stem}: {counts['bursts_before']} -> {counts['bursts_after']}")
    click.echo(f"Written to {result['output_folder']}")


if __name__ == "__main__":  # pragma: no cover
    cli()

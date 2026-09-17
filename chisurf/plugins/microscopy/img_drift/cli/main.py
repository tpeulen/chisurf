"""Headless CLI for inter-frame drift correction."""

from __future__ import annotations

import json

import click
import numpy as np

from .. import core as _core


def _channel(value: str):
    """Return *value* as an int channel index when numeric, else as a channel name."""
    try:
        return int(value)
    except ValueError:
        return value


@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option(
    "--channel", "-c", default="0", help="Channel to measure the drift on (index or name)."
)
@click.option(
    "--reference",
    type=click.Choice(["first", "previous", "mean"]),
    default="first",
    show_default=True,
    help="Frame each frame is compared with. 'first' suits slow monotonic drift; "
    "'previous' tracks wander but accumulates error.",
)
@click.option(
    "--mode",
    type=click.Choice(["wrap", "constant"]),
    default="wrap",
    show_default=True,
    help="'wrap' conserves every photon; 'constant' drops what leaves the frame.",
)
@click.option(
    "--smooth",
    type=float,
    default=2.0,
    show_default=True,
    help="Gaussian smoothing of the correlation before the peak search (px).",
)
@click.option("--subpixel", is_flag=True, help="Refine each peak by parabolic interpolation.")
@click.option(
    "--roi",
    type=click.Path(exists=True),
    default=None,
    help="JSON file holding a serialised ROI to restrict the estimate to.",
)
@click.option(
    "--channel-axis", default=None, help="Images: force the channel axis (index or label)."
)
@click.option(
    "--out-stack",
    type=click.Path(),
    default=None,
    help="Write the corrected stack as a multi-page TIFF.",
)
@click.option(
    "--out-shifts",
    type=click.Path(),
    default=None,
    help="Write the per-frame displacements as CSV.",
)
@click.option("--json", "as_json", is_flag=True, help="Print the summary as JSON.")
def cli(
    filename,
    channel,
    reference,
    mode,
    smooth,
    subpixel,
    roi,
    channel_axis,
    out_stack,
    out_shifts,
    as_json,
):
    """Measure and remove inter-frame drift in an image stack or photon stream.

    Reports the largest displacement found, which is the number worth acting on:
    a fraction of a pixel means the correction changes nothing, while a drift
    beyond the beam waist means any frame-lag analysis of the raw data was
    compromised.
    """
    roi_spec = None
    if roi:
        with open(roi) as fh:
            roi_spec = json.load(fh)

    result = _core.measure_drift(
        filename,
        _channel(channel),
        reference=reference,
        roi=roi_spec,
        smooth=smooth,
        subpixel=subpixel,
        mode=mode,
        channel_axis=channel_axis,
    )

    written = {}
    if out_shifts:
        written["shifts"] = _core.write_shifts_csv(result.shifts, out_shifts)
    if out_stack:
        data, _ = _core.corrected_stack(
            filename,
            _channel(channel),
            shifts=result.shifts,
            mode=mode,
            channel_axis=channel_axis,
        )
        written["stack"] = _core.write_stack_tiff(data, out_stack)

    summary = result.to_dict()
    summary["written"] = written

    if as_json:
        click.echo(json.dumps(summary, indent=2))
        return

    sh = np.asarray(result.shifts)
    click.echo(f"source        : {result.source} ({result.kind})")
    click.echo(f"frames        : {result.n_frames}")
    click.echo(f"channels      : {', '.join(result.channel_names)}")
    click.echo(f"max drift     : {result.total_drift:.2f} px")
    click.echo(f"final offset  : dy={sh[-1, 0]:+.2f} dx={sh[-1, 1]:+.2f} px")
    for label, path in written.items():
        click.echo(f"wrote {label:<8}: {path}")


if __name__ == "__main__":
    cli()

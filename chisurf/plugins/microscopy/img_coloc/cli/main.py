"""Headless CLI for two-channel image colocalization."""

from __future__ import annotations

import json

import click

from .. import core as _core


def _channel(value: str):
    """Return *value* as an int channel index when numeric, else as a channel name."""
    try:
        return int(value)
    except ValueError:
        return value


@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option("--channel-a", "-a", default="0", help="First channel (index or name).")
@click.option("--channel-b", "-b", default="1", help="Second channel (index or name).")
@click.option("--frame", type=int, default=None, help="Single frame; default sums all frames.")
@click.option(
    "--channel-axis", default=None, help="Images: force the channel axis (index or label)."
)
@click.option("--auto-background", is_flag=True, help="Estimate background as the 5% quantile.")
@click.option("--background-a", type=float, default=0.0, help="Background of channel A.")
@click.option("--background-b", type=float, default=0.0, help="Background of channel B.")
@click.option("--threshold-a", type=float, default=0.0, help="Intensity threshold of channel A.")
@click.option("--threshold-b", type=float, default=0.0, help="Intensity threshold of channel B.")
@click.option("--costes-threshold", is_flag=True, help="Use Costes automatic thresholds.")
@click.option("--costes-test", is_flag=True, help="Run the Costes randomization significance test.")
@click.option("--randomizations", type=int, default=200, help="Costes randomization count.")
@click.option("--block", type=int, default=4, help="Costes scramble block size (PSF width, px).")
@click.option("--seed", type=int, default=0, help="Random seed of the Costes test.")
@click.option("--ccf-shift", type=int, default=0, help="van Steensel max shift (0 disables).")
@click.option("--json", "as_json", is_flag=True, help="Print the metrics as JSON.")
@click.option(
    "--output", "-o", type=click.Path(), default=None, help="Write the metrics to a JSON file."
)
def cli(
    filename,
    channel_a,
    channel_b,
    frame,
    channel_axis,
    auto_background,
    background_a,
    background_b,
    threshold_a,
    threshold_b,
    costes_threshold,
    costes_test,
    randomizations,
    block,
    seed,
    ccf_shift,
    as_json,
    output,
):
    """Compute colocalization coefficients for two channels of an image FILENAME.

    FILENAME is a TIFF stack (or any imageio-readable image) or a photon-stream
    file (PTU/HT3/…), which is reconstructed into a confocal-scan image.
    """
    result = _core.compute_colocalization(
        filename,
        channel_a=_channel(channel_a),
        channel_b=_channel(channel_b),
        frame=frame,
        channel_axis=channel_axis,
        auto_background=auto_background,
        background_a=background_a,
        background_b=background_b,
        threshold_a=threshold_a,
        threshold_b=threshold_b,
        auto_threshold=costes_threshold,
        costes_test=costes_test,
        costes_block=block,
        costes_randomizations=randomizations,
        costes_seed=seed,
        ccf_max_shift=ccf_shift,
    )
    metrics = {k: (list(v) if isinstance(v, tuple) else v) for k, v in result["metrics"].items()}
    if as_json:
        click.echo(json.dumps(metrics, indent=2, default=float))
    else:
        ny, nx = result["shape"]
        click.echo(f"{filename}: {nx}x{ny} px | channels {result['channel_names']}")
        for row in _core.metric_rows(metrics):
            click.echo(f"  {row['name']:<32} {row['value']}")
        if metrics.get("warning"):
            click.echo(f"  warning: {metrics['warning']}")
    if output:
        with open(output, "w") as fp:
            json.dump(metrics, fp, indent=2, default=float)
        click.echo(f"wrote {output}")


if __name__ == "__main__":
    cli()

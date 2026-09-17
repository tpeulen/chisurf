"""Headless CLI: measure image resolution by Fourier ring correlation."""

from __future__ import annotations

import json

import click

from ..client import FrcClient


@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option(
    "--split",
    type=click.Choice(["even_odd", "halves", "channels", "two_files"]),
    default="even_odd",
    show_default=True,
    help="How to cut the acquisition into two independent halves.",
)
@click.option(
    "--channel",
    "-c",
    default="0",
    show_default=True,
    help="Channel to measure, by index or by name.",
)
@click.option(
    "--channel-2", default=None, help="Second channel for --split channels (default: the next one)."
)
@click.option(
    "--second",
    "second_filename",
    type=click.Path(exists=True),
    default=None,
    help="Second acquisition for --split two_files.",
)
@click.option(
    "--pixel-size",
    "pixel_size_nm",
    type=float,
    default=None,
    help="Pixel size in nm. Without it the resolution is in pixels.",
)
@click.option(
    "--criterion",
    type=click.Choice(["fixed_1/7", "half_bit", "two_sigma"]),
    default="fixed_1/7",
    show_default=True,
    help="Threshold convention; quote it with the number.",
)
@click.option(
    "--bin-width",
    type=float,
    default=None,
    help="Ring width in cycles/pixel (default: one Fourier pixel).",
)
@click.option(
    "--smooth",
    type=int,
    default=3,
    show_default=True,
    help="Rings averaged before the threshold crossing is read.",
)
@click.option(
    "--axis-order",
    type=click.Choice(["auto", "frames", "channels"]),
    default="auto",
    show_default=True,
    help="TIFF only: read a 3-D file's leading axis as frames or as channels.",
)
@click.option(
    "--windows", type=str, default=None, help="Photon streams: JSON of named detector windows."
)
@click.option(
    "--channels",
    type=str,
    default=None,
    help="Photon streams: comma-separated routing channels to fill.",
)
@click.option(
    "--out-csv",
    "output_path",
    type=click.Path(),
    default=None,
    help="Write the curve, threshold and ring counts to a CSV file.",
)
@click.option("--json", "as_json", is_flag=True, help="Print the result as JSON.")
def cli(
    filename,
    split,
    channel,
    channel_2,
    second_filename,
    pixel_size_nm,
    criterion,
    bin_width,
    smooth,
    axis_order,
    windows,
    channels,
    output_path,
    as_json,
):
    """Measure the resolution of FILENAME (a TIFF stack or a photon stream).

    The FRC asks how far into the fine detail two independent halves of the same
    measurement still agree. Above that frequency what is in the image is noise,
    so the crossing -- inverted -- is the resolution the acquisition achieved.

    Quote the criterion with the number: the three conventions disagree by tens
    of per cent on the same data, and none of them is "the" resolution.
    """
    kwargs = {
        "split": split,
        "channel": int(channel) if str(channel).lstrip("-").isdigit() else channel,
        "channel_2": channel_2,
        "second_filename": second_filename,
        "pixel_size_nm": pixel_size_nm,
        "criterion": criterion,
        "bin_width": bin_width,
        "smooth": smooth,
        "axis_order": axis_order,
        "output_path": output_path,
    }
    if windows:
        kwargs["windows"] = json.loads(windows)
    if channels:
        kwargs["channels"] = [int(c) for c in channels.split(",") if c.strip()]

    try:
        result = FrcClient().resolution(filename, **kwargs)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        click.echo(json.dumps(result, indent=2))
        # A caller parsing the payload still needs the "no crossing" case to be
        # visible in the exit status, not only in a null field.
        if not result["crossed"]:
            click.get_current_context().exit(1)
        return

    unit = result["unit"]
    click.echo(f"{result['source']} ({result['kind']}, {result['n_frames']} frames)")
    click.echo(f"channels: {', '.join(result['channel_names'])}")
    if not result["crossed"]:
        raise click.ClickException(
            "the FRC never crosses its threshold — the halves either agree "
            "everywhere (resolution beyond this sampling) or nowhere (too few "
            "photons, or a split whose halves are not independent)"
        )
    click.echo(f"criterion: {result['criterion']}")
    click.echo(f"crossing:  {result['crossing']:.6g} 1/{unit}")
    click.echo(f"resolution: {result['resolution']:.4g} {unit}")
    if result["output_path"]:
        click.echo(f"wrote {result['output_path']}")


if __name__ == "__main__":
    cli()

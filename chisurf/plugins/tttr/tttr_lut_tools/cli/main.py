"""Command-line interface for the TTTR LUT Tools plugin.

Calls the pure ``api/`` layer directly (no Qt, no RPC)::

    chisurf lut-tools compute uniform.spc -o green.npy
    chisurf lut-tools apply data.spc --lut 0=green.npy --routine SPC-130
    chisurf lut-tools settings --lut 0=green.npy --shift 0=3 -o settings.tttr.json
"""

from __future__ import annotations

import json

import click

from ..api import compute, io, settings


def _parse_channel_map(pairs, loader=None):
    """Turn ``("0=green.npy", ...)`` into ``{0: value}`` (value via *loader*)."""
    out = {}
    for pair in pairs:
        ch, _, val = pair.partition("=")
        out[int(ch)] = loader(val) if loader else val
    return out


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """TTTR microtime LUT tools — compute / apply / build settings."""


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True, dir_okay=False), required=True)
@click.option(
    "-o", "--out", required=True, type=click.Path(), help="Output LUT (.npy/.npz/.txt/.csv)."
)
@click.option("--routine", default=None, help="tttrlib reading routine (blank = auto).")
@click.option("--n-bins", default=0, type=int, help="TAC bin count (0 = infer).")
@click.option("--linear-start", default=None, type=int, help="Linear-region start (auto if unset).")
@click.option("--linear-stop", default=None, type=int, help="Linear-region stop (auto if unset).")
@click.option("--ntac", "ntac_required", default=0, type=int, help="Target NTAC bins (0 = same).")
@click.option("--noffset", default=0, type=int, help="Offset subtracted from corrected indices.")
@click.option(
    "--channel",
    default=None,
    type=int,
    help="Routing channel to compute the LUT for (per-channel; recommended).",
)
def compute_cmd(
    files, out, routine, n_bins, linear_start, linear_stop, ntac_required, noffset, channel
):
    """Compute a linearization LUT from uniform-illumination FILES."""
    tbl = compute.compute_lut_from_files(
        list(files),
        routine=routine,
        n_bins=n_bins or None,
        linear_start=linear_start,
        linear_stop=linear_stop,
        ntac_required=ntac_required or None,
        noffset=noffset,
        channel=channel,
    )
    path = io.save_lut(out, tbl)
    ch = f"ch{channel} " if channel is not None else ""
    click.echo(f"{ch}linear region [{tbl['linear_start']}, {tbl['linear_stop']}) -> {path}")


@cli.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--lut", "luts", multiple=True, metavar="CH=PATH", help="Assign a LUT to a channel.")
@click.option(
    "--shift", "shifts", multiple=True, metavar="CH=N", help="Per-channel micro-time shift."
)
@click.option("--channel", default=0, type=int, help="Channel to histogram for the summary.")
@click.option("--routine", default=None, help="tttrlib reading routine.")
def apply_cmd(file, luts, shifts, channel, routine):
    """Apply LUTs/shifts to FILE and print the corrected histogram summary."""
    lut_map = _parse_channel_map(luts, loader=lambda p: io.load_lut_file(p))
    shift_map = _parse_channel_map(shifts, loader=int)
    counts, _axis = settings.corrected_histogram(file, channel, lut_map, shift_map, routine)
    click.echo(f"ch{channel}: {int(counts.sum())} counts, {int((counts > 0).sum())} nonzero bins")


@cli.command()
@click.option(
    "--lut", "luts", multiple=True, metavar="CH=PATH", required=True, help="Assign a LUT."
)
@click.option("--shift", "shifts", multiple=True, metavar="CH=N", help="Per-channel shift.")
@click.option("--routine", default=None, help="tttrlib reading routine.")
@click.option("-o", "--out", required=True, type=click.Path(), help="settings.tttr.json output.")
def settings_cmd(luts, shifts, routine, out):
    """Build a settings.tttr.json from assigned LUTs/shifts."""
    lut_map = {ch: io.load_lut_file(p) for ch, p in _parse_channel_map(luts).items()}
    shift_map = _parse_channel_map(shifts, loader=int)
    d = settings.build_settings_dict(
        lut_map, shift_map, reading_routine=routine, used_channels=sorted(lut_map)
    )
    path = settings.save_settings(out, d)
    click.echo(f"wrote {path} ({len(lut_map)} channel(s))")


# click renames underscores to hyphens for the command names
cli.add_command(compute_cmd, name="compute")
cli.add_command(apply_cmd, name="apply")
cli.add_command(settings_cmd, name="settings")


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps({"cli": "lut-tools"}))

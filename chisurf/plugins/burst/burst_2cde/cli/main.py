"""CLI entrypoint for 2CDE analysis."""

from __future__ import annotations

import json
import pathlib

import click

from chisurf.plugins.burst.burst_2cde.api.models import TwoCdeSettings
from chisurf.plugins.burst.burst_2cde.core.computation import (
    column_for_variant,
    compute_2cde,
    read_burst_analysis,
    write_2cde_analysis,
)


@click.group(name="2cde")
def cli():
    """FRET-2CDE / ALEX-2CDE burst dynamics feature."""


@cli.command()
@click.argument("analysis_folder", type=click.Path(exists=True, file_okay=False))
@click.option("--variant", type=click.Choice(["fret", "alex"]), default="fret")
@click.option("--kernel", type=click.Choice(["laplace", "gaussian"]), default="laplace")
@click.option("--tau", default=100e-6, type=float, help="Kernel time constant (s)")
@click.option("--file-type", default="SPC-130", help="tttrlib container name")
@click.option("--pattern", default="bi4_bur", help="Glob pattern for burst data dirs")
@click.option("--donor-channels", default="0,8", help="Comma-separated donor channels")
@click.option("--acceptor-channels", default="1,9", help="Comma-separated acceptor channels")
@click.option("--donor-mtr-start", default=0, type=int)
@click.option("--donor-mtr-end", default=32768, type=int)
@click.option("--acceptor-mtr-start", default=0, type=int)
@click.option("--acceptor-mtr-end", default=32768, type=int)
@click.option("--output", "-o", type=click.Path(), help="Output directory root")
@click.option("--save-settings", is_flag=True, help="Save settings JSON alongside output")
def compute(
    analysis_folder, variant, kernel, tau, file_type, pattern,
    donor_channels, acceptor_channels,
    donor_mtr_start, donor_mtr_end, acceptor_mtr_start, acceptor_mtr_end,
    output, save_settings,
):
    """Compute the 2CDE feature for burst data in ANALYSIS_FOLDER."""
    try:
        donor_chs = [int(x.strip()) for x in donor_channels.split(",")]
        acceptor_chs = [int(x.strip()) for x in acceptor_channels.split(",")]
    except ValueError as e:
        click.echo(f"Error parsing channels: {e}", err=True)
        raise click.Abort()

    af = pathlib.Path(analysis_folder)
    settings = TwoCdeSettings(
        donor_channels=donor_chs,
        donor_micro_time_ranges=[(donor_mtr_start, donor_mtr_end)],
        acceptor_channels=acceptor_chs,
        acceptor_micro_time_ranges=[(acceptor_mtr_start, acceptor_mtr_end)],
        tau=tau, kernel=kernel, variant=variant, file_type=file_type,
    )

    click.echo(f"Reading burst data from {af} ...")
    df, tttrs = read_burst_analysis(af, file_type, pattern=pattern)
    click.echo(f"Found {len(df)} bursts across {len(tttrs)} TTTR file(s)")

    click.echo(f"Computing {variant.upper()}-2CDE ({kernel}) ...")
    df_v = compute_2cde(
        df, tttrs,
        donor_channels=settings.donor_channels,
        donor_micro_time_ranges=settings.donor_micro_time_ranges,
        acceptor_channels=settings.acceptor_channels,
        acceptor_micro_time_ranges=settings.acceptor_micro_time_ranges,
        tau=settings.tau, kernel=settings.kernel, variant=settings.variant,
    )
    column = column_for_variant(variant)
    import numpy as np
    valid = int(np.isfinite(df_v[column]).sum())
    click.echo(f"Valid bursts: {valid} / {len(df_v)} total")

    out_root = pathlib.Path(output) if output else af
    write_2cde_analysis(df_v, str(out_root), variant=variant)
    click.echo(f"Wrote {column} sidecars to {out_root / '2cde'}")

    if save_settings:
        from chisurf.plugins.burst.burst_2cde.api.serialization import to_jsonable
        out = out_root / "2cde"
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "2cde_settings.json", "w") as f:
            json.dump(to_jsonable(settings), f, indent=4)
        click.echo(f"Settings saved to {out / '2cde_settings.json'}")

    click.echo("Done")

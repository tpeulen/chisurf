"""CLI entrypoint for 2CDE analysis."""

from __future__ import annotations

import json
import pathlib

import click
import numpy as np

from chisurf.core.datastore import numeric_column, row_count
from chisurf.plugins.burst.burst_2cde.api.models import TwoCdeSettings
from chisurf.plugins.burst.burst_2cde.core.computation import (
    column_for_variant,
    compute_2cde,
    read_burst_analysis,
    write_2cde_container,
)


@click.group(name="2cde")
def cli():
    """FRET-2CDE / ALEX-2CDE burst dynamics feature."""


@cli.command()
@click.argument("analysis_folder", type=click.Path())
@click.option("--variant", type=click.Choice(["fret", "alex"]), default="fret")
@click.option("--kernel", type=click.Choice(["laplace", "gaussian"]), default="laplace")
@click.option("--tau", default=100e-6, type=float, help="Kernel time constant (s)")
@click.option("--file-type", default="SPC-130", help="tttrlib container name")
@click.option("--pattern", default="bi4_bur", help="Glob pattern for burst data dirs")
@click.option("--donor-channels", default="0,8", help="Routing channels of G|G (donor emission), comma separated")
@click.option("--acceptor-channels", default="1,9", help="Routing channels of R|G (FRET acceptor), comma separated")
@click.option("--donor-mtr-start", default=0, type=int)
@click.option("--donor-mtr-end", default=32768, type=int)
@click.option("--acceptor-mtr-start", default=0, type=int)
@click.option("--acceptor-mtr-end", default=32768, type=int)
@click.option("--acceptor-excitation-mtr-start", type=int, default=None)
@click.option("--acceptor-excitation-mtr-end", type=int, default=None)
@click.option("--micro-time-resolution-ps", type=float, default=None)
@click.option("--alternation-period-ticks", type=float, default=0)
@click.option("--alternation-offset-ticks", type=float, default=0)
@click.option("--donor-phase", type=(float, float), multiple=True, help="Donor-excitation phase [start, end) in macro ticks.")
@click.option("--acceptor-phase", type=(float, float), multiple=True, help="Acceptor-excitation phase [start, end) in macro ticks.")
@click.option("--output", "-o", type=click.Path(), help="Output directory root")
@click.option("--save-settings", is_flag=True, help="Save settings JSON alongside output")
def compute(
    analysis_folder,
    variant,
    kernel,
    tau,
    file_type,
    pattern,
    donor_channels,
    acceptor_channels,
    donor_mtr_start,
    donor_mtr_end,
    acceptor_mtr_start,
    acceptor_mtr_end,
    acceptor_excitation_mtr_start,
    acceptor_excitation_mtr_end,
    micro_time_resolution_ps,
    alternation_period_ticks,
    alternation_offset_ticks,
    donor_phase,
    acceptor_phase,
    output,
    save_settings,
):
    """Compute the 2CDE feature for burst data in ANALYSIS_FOLDER."""
    try:
        donor_chs = [int(x.strip()) for x in donor_channels.split(",")]
        acceptor_chs = [int(x.strip()) for x in acceptor_channels.split(",")]
    except ValueError as e:
        click.echo(f"Error parsing channels: {e}", err=True)
        raise click.Abort()

    from click.core import ParameterSource

    from chisurf.plugins.burst.burst_2cde.backend.services import (
        settings_from_setup,
        setup_from_run,
    )

    af = pathlib.Path(analysis_folder)
    ctx = click.get_current_context()
    def explicit(name):
        return ctx.get_parameter_source(name) != ParameterSource.DEFAULT
    try:
        values = settings_from_setup(setup_from_run(af))
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    if explicit("donor_channels"):
        values["donor_channels"] = donor_chs
    if explicit("acceptor_channels"):
        values["acceptor_channels"] = acceptor_chs
        values["acceptor_excitation_channels"] = acceptor_chs
    for role, start, end in (("donor", donor_mtr_start, donor_mtr_end),
                             ("acceptor", acceptor_mtr_start, acceptor_mtr_end)):
        if explicit(f"{role}_mtr_start") or explicit(f"{role}_mtr_end"):
            values[f"{role}_micro_time_ranges"] = [(start, end)]
    if (acceptor_excitation_mtr_start is None) != (acceptor_excitation_mtr_end is None):
        raise click.ClickException("Both acceptor-excitation window endpoints are required")
    if acceptor_excitation_mtr_start is not None:
        values["acceptor_excitation_micro_time_ranges"] = [(acceptor_excitation_mtr_start, acceptor_excitation_mtr_end)]
    if micro_time_resolution_ps is not None:
        values["micro_time_resolution_ps"] = micro_time_resolution_ps
    if explicit("file_type"):
        values["file_type"] = file_type
    if explicit("donor_phase"):
        values.update(donor_macro_phase_ranges=list(donor_phase),
                      acceptor_macro_phase_ranges=list(donor_phase))
    if explicit("acceptor_phase"):
        values["acceptor_excitation_macro_phase_ranges"] = list(acceptor_phase)
    if explicit("alternation_period_ticks"):
        values["alternation_period_ticks"] = alternation_period_ticks
    if explicit("alternation_offset_ticks"):
        values["alternation_offset_ticks"] = alternation_offset_ticks
    values.update(tau=tau, kernel=kernel, variant=variant)
    settings = TwoCdeSettings(**values)

    click.echo(f"Reading burst data from {af} ...")
    df, tttrs = read_burst_analysis(af, settings.file_type, pattern=pattern)
    click.echo(f"Found {row_count(df)} bursts across {len(tttrs)} TTTR file(s)")

    click.echo(f"Computing {variant.upper()}-2CDE ({kernel}) ...")
    df_v = compute_2cde(
        df,
        tttrs,
        donor_channels=settings.donor_channels,
        donor_micro_time_ranges=settings.donor_micro_time_ranges,
        acceptor_channels=settings.acceptor_channels,
        acceptor_micro_time_ranges=settings.acceptor_micro_time_ranges,
        acceptor_excitation_channels=settings.acceptor_excitation_channels,
        acceptor_excitation_micro_time_ranges=settings.acceptor_excitation_micro_time_ranges,
        micro_time_resolution_ps=settings.micro_time_resolution_ps,
        alex_donor_channel_ranges=settings.alex_donor_channel_ranges,
        alex_acceptor_channel_ranges=settings.alex_acceptor_channel_ranges,
        donor_macro_phase_ranges=settings.donor_macro_phase_ranges,
        acceptor_macro_phase_ranges=settings.acceptor_macro_phase_ranges,
        acceptor_excitation_macro_phase_ranges=settings.acceptor_excitation_macro_phase_ranges,
        alternation_period_ticks=settings.alternation_period_ticks,
        alternation_offset_ticks=settings.alternation_offset_ticks,
        tau=settings.tau,
        kernel=settings.kernel,
        variant=settings.variant,
    )
    from chisurf.core.fluorescence.burst.streams import (
        gates_record,
        stream_detectors,
        window_warnings,
    )
    from chisurf.plugins.burst.burst_2cde.core.computation import applied_streams

    streams = applied_streams(
        variant,
        settings.donor_channels,
        settings.donor_micro_time_ranges,
        settings.acceptor_channels,
        settings.acceptor_micro_time_ranges,
        settings.acceptor_excitation_channels,
        settings.acceptor_excitation_micro_time_ranges,
    )
    detectors = stream_detectors(streams)
    for line in window_warnings(tttrs, gates_record(detectors, settings.micro_time_resolution_ps), detectors):
        click.echo(f"warning: {line}", err=True)

    column = column_for_variant(variant)
    valid = int(np.isfinite(numeric_column(df_v, column)).sum())
    click.echo(f"Valid bursts: {valid} / {row_count(df_v)} total")

    out_root = pathlib.Path(output) if output else af
    written = write_2cde_container(df_v, variant, parameters=__import__("dataclasses").asdict(settings), analysis_folder=out_root)
    click.echo(f"Wrote {column} into {len(written)} measurement container(s)")

    if save_settings:
        from chisurf.plugins.burst.burst_2cde.api.serialization import to_jsonable

        out = out_root / "2cde"
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "2cde_settings.json", "w") as f:
            json.dump(to_jsonable(settings), f, indent=4)
        click.echo(f"Settings saved to {out / '2cde_settings.json'}")

    click.echo("Done")

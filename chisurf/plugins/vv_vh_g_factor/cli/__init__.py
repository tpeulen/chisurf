"""Command Line Interface for VV/VH G-Factor Calculator."""

from __future__ import annotations

import json
import sys

import click
import numpy as np

from ..core.calculations import calculate_g_factor_core


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """VV/VH G-Factor CLI.

    Run tail matching G-factor calculations headlessly.
    """
    pass


@cli.command("calculate")
@click.argument("vv_vh_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--region-min", type=float, required=True, help="Tail match region min channel.")
@click.option("--region-max", type=float, required=True, help="Tail match region max channel.")
@click.option(
    "--shift", type=float, default=0.0, show_default=True, help="Perpendicular decay shift."
)
@click.option("--use-bg", is_flag=True, help="Enable background subtraction.")
@click.option("--bg-min", type=float, default=None, help="Background region min channel.")
@click.option("--bg-max", type=float, default=None, help="Background region max channel.")
@click.option("--flip", is_flag=True, help="Swap parallel and perpendicular decays.")
def calculate(
    vv_vh_file: str,
    region_min: float,
    region_max: float,
    shift: float,
    use_bg: bool,
    bg_min: float | None,
    bg_max: float | None,
    flip: bool,
) -> None:
    """Calculate G-factor for VV_VH_FILE using tail matching."""
    try:
        from chisurf.core.fio import read_vv_vh as _read_vv_vh
    except Exception:
        _read_vv_vh = None

    try:
        if _read_vv_vh is not None:
            vv, vh = _read_vv_vh(vv_vh_file, split=True)
        else:
            vec = np.loadtxt(vv_vh_file)
            half = len(vec) // 2
            vv, vh = vec[:half], vec[half:]
    except Exception as e:
        click.echo(f"Error loading VV/VH file: {e}", err=True)
        sys.exit(1)

    bg_bounds = None
    if use_bg:
        if bg_min is None or bg_max is None:
            click.echo(
                "Error: --bg-min and --bg-max must be provided if --use-bg is set.", err=True
            )
            sys.exit(1)
        bg_bounds = [bg_min, bg_max]

    res = calculate_g_factor_core(
        parallel_data=vv,
        perpendicular_data=vh,
        region_bounds=[region_min, region_max],
        decay_shift=shift,
        use_bg=use_bg,
        bg_region_bounds=bg_bounds,
        flip=flip,
    )
    click.echo(json.dumps(res, indent=2))

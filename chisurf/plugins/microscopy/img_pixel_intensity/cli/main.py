"""Headless CLI for the per-pixel intensity imaging tool."""

from __future__ import annotations

import click

from .. import core as _core


@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option("--channel", "-c", multiple=True, type=int, default=(0,), help="Detector channel(s).")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output imaging HDF5 path.")
@click.option(
    "--container", is_flag=True, help="Also write the map into <filename>.pto, beside the photons"
)
def cli(filename, channel, output, container):
    """Compute the per-pixel intensity map and create a standard imaging HDF5."""
    import numpy as np

    from chisurf.core.fluorescence.imaging import maps_to_table, write_imaging_hdf5

    result = _core.compute_intensity(filename, channels=tuple(channel))
    maps = result["maps"]
    ny, nx = result["shape"]
    click.echo(f"{nx}x{ny} px | total intensity={np.nansum(maps['intensity']):.0f}")
    if output:
        write_imaging_hdf5(maps_to_table(maps), output, source=filename)
        click.echo(f"wrote {output}")
    if container:
        from chisurf.core.fio.fluorescence.imaging_container import (
            write_imaging_table,
        )

        path = write_imaging_table(
            filename,
            maps_to_table(maps),
            name="intensity",
            artifact_kind="pixel_map",
            operation_type="image_analysis",
            row_grain="pixel",
            parameters={"channels": list(channel)},
            units={
                "X pixel": "pixels",
                "Y pixel": "pixels",
                "Pixel Number": "dimensionless",
                "intensity": "counts",
            },
        )
        click.echo(f"wrote {path}")


if __name__ == "__main__":
    cli()

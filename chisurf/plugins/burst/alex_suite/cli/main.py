"""Headless ALEX Suite: alternation conversion, histograms, titration, export.

Everything the window does that is not already another tool's command. The burst
search itself is ``csc burst-selection`` and the corrections are
``csc accurate-fret`` — those are not repeated here, because the pipeline is the
ordinary one.
"""

from __future__ import annotations

import json
import pathlib

import click
import numpy as np


def _channels(text: str) -> list[int] | None:
    """Parse a ``"0,8"`` channel list; ``"auto"`` means "work it out"."""
    stripped = str(text).strip().lower()
    if not stripped or stripped == "auto":
        return None
    return [int(part) for part in stripped.replace(";", ",").split(",") if part.strip()]


@click.group("alex-suite")
def cli() -> None:
    """Run the ALEX Suite headlessly."""


@cli.command("alternation")
@click.argument("files", nargs=-1, type=click.Path(exists=True), required=True)
@click.option("--donor", default="auto",
              help="Donor routing channels, comma separated, or 'auto'.")
@click.option("--acceptor", default="auto",
              help="Acceptor routing channels, comma separated, or 'auto'.")
@click.option("--out-dir", type=click.Path(), default=None,
              help="Where the converted .pto containers go (default: beside the source).")
@click.option("--detect-only", is_flag=True,
              help="Report the period and the laser gates without converting.")
@click.option("--as-json", is_flag=True, help="Print the result as JSON.")
def alternation(files, donor, acceptor, out_dir, detect_only, as_json) -> None:
    """Find the µs-ALEX alternation and fold it into the micro-time.

    After this the measurement is ordinary PIE data and the normal burst
    pipeline applies to it unchanged.
    """
    from chisurf.plugins.burst.alex_suite.api.convert import detect_and_convert

    donor_channels = _channels(donor)
    acceptor_channels = _channels(acceptor)

    if detect_only:
        # Same code path as the conversion, minus the writing, so what is
        # reported is what a real run would use.
        outcome = detect_and_convert(
            files[:1], donor_channels=donor_channels,
            acceptor_channels=acceptor_channels, dry_run=True,
        )
        payload = {
            "period": outcome["period"],
            "confidence": outcome["confidence"],
            "donor": outcome["donor_channels"],
            "acceptor": outcome["acceptor_channels"],
            "green": [float(v) for v in outcome["windows"]["green"]],
            "red": [float(v) for v in outcome["windows"]["red"]],
        }
    else:
        outcome = detect_and_convert(
            files, donor_channels=donor_channels,
            acceptor_channels=acceptor_channels, out_dir=out_dir,
            progress=lambda i, n, name: click.echo(f"  [{i + 1}/{n}] {name}", err=True),
        )
        payload = {
            "period": outcome["period"],
            "confidence": outcome["confidence"],
            "donor": outcome["donor_channels"],
            "acceptor": outcome["acceptor_channels"],
            "green": [float(v) for v in outcome["windows"]["green"]],
            "red": [float(v) for v in outcome["windows"]["red"]],
            "converted": [str(p) for p in outcome["converted"]],
            "failed": [str(p) for p, _ in outcome["failed"]],
        }

    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return
    click.echo(f"period      {payload['period']} macro-time units")
    click.echo(f"confidence  {payload['confidence']:.0f}x")
    click.echo(f"donor       channel(s) {payload['donor']}")
    click.echo(f"acceptor    channel(s) {payload['acceptor']}")
    click.echo(f"green gate  {payload['green'][0]:.0f} - {payload['green'][1]:.0f}")
    click.echo(f"red gate    {payload['red'][0]:.0f} - {payload['red'][1]:.0f}")
    for path in payload.get("converted", []):
        click.echo(f"wrote       {path}")


@cli.command("histogram")
@click.argument("burst_table", type=click.Path(exists=True))
@click.option("--gamma", type=float, default=1.0, help="Detection/quantum-yield ratio.")
@click.option("--beta", type=float, default=1.0, help="Excitation-flux ratio.")
@click.option("--alpha", type=float, default=0.0, help="Donor leakage.")
@click.option("--delta", type=float, default=0.0, help="Direct acceptor excitation.")
@click.option("--min-photons", type=float, default=0.0, help="Minimum photons per burst.")
@click.option("--bins", type=int, default=101, help="Bins on both axes.")
@click.option("--export", "export_stem", type=click.Path(), default=None,
              help="Write the ALEX-Suite CSV export with this stem.")
def histogram(burst_table, gamma, beta, alpha, delta, min_photons, bins,
              export_stem) -> None:
    """Report the E-S histogram of a burst table, optionally exporting it."""
    from chisurf.plugins.burst.alex_suite.api.histograms import (
        Corrections,
        Thresholds,
        es_histograms,
    )

    corrections = Corrections(gamma=gamma, beta=beta, alpha=alpha, delta=delta)
    result = es_histograms(
        burst_table, corrections=corrections,
        thresholds=Thresholds(total_min=min_photons), bins=(bins, bins),
    )
    click.echo(f"bursts      {result.e.size} of {result.n_bursts_total}")
    click.echo(f"columns     {result.columns}")
    if result.e.size:
        click.echo(f"E peak      {result.e_centres[int(np.argmax(result.e_hist))]:.3f}")
        finite = np.isfinite(result.s)
        if finite.any():
            click.echo(
                f"S peak      {result.s_centres[int(np.argmax(result.s_hist))]:.3f}")
    if export_stem:
        from chisurf.plugins.burst.alex_suite.api.legacy_export import (
            write_legacy_export,
        )

        for path in write_legacy_export(
            export_stem, result, corrections=corrections,
            thresholds=Thresholds(total_min=min_photons),
        ):
            click.echo(f"wrote       {path}")


@cli.command("titration")
@click.argument("series", type=click.Path(exists=True))
@click.option("--populations", type=int, default=2,
              help="Populations shared across the whole series.")
@click.option("--model", type=click.Choice(["hill", "one_site"]), default="hill")
@click.option("--unit", default="nM", help="Concentration unit, for the report only.")
@click.option("--min-photons", type=float, default=50.0, help="Minimum photons per burst.")
@click.option("--bins", type=int, default=81, help="Bins of the efficiency histogram.")
@click.option("--as-json", is_flag=True, help="Print the result as JSON.")
def titration(series, populations, model, unit, min_photons, bins, as_json) -> None:
    """Fit a titration series.

    SERIES is a CSV of ``concentration,burst_file`` rows (no header needed;
    a header line whose first field does not parse as a number is skipped).
    Paths are resolved relative to the series file.
    """
    import csv

    from chisurf.plugins.burst.alex_suite.api.histograms import Thresholds
    from chisurf.plugins.burst.alex_suite.api.titration import (
        Condition,
        run_titration,
    )

    root = pathlib.Path(series).parent
    conditions = []
    with open(series, newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            try:
                concentration = float(row[0])
            except ValueError:
                continue  # header line
            path = pathlib.Path(row[1].strip())
            conditions.append(Condition(
                concentration=concentration,
                source=str(path if path.is_absolute() else root / path),
                label=f"{concentration:g} {unit}",
            ))
    if len(conditions) < 2:
        raise click.ClickException(
            f"{series} holds {len(conditions)} usable rows; a titration needs at least 2"
        )

    result = run_titration(
        conditions, n_components=populations, binding_model=model,
        thresholds=Thresholds(total_min=min_photons), bins=bins,
    )
    payload = {
        "concentrations": result.stack.concentrations.tolist(),
        "centres": result.fit.centres.tolist(),
        "widths": result.fit.widths.tolist(),
        "fractions": result.fit.fractions.tolist(),
        "component": result.component,
        "chi2r": result.fit.chi2r,
    }
    if result.binding is not None:
        payload["binding"] = {
            "model": result.binding.model,
            "kd": result.binding.kd,
            "unit": unit,
            "hill": result.binding.hill,
            "f_min": result.binding.f_min,
            "f_max": result.binding.f_max,
            "chi2r": result.binding.chi2r,
        }
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return
    click.echo(f"conditions  {len(result.stack)}")
    for k, (centre, width) in enumerate(zip(result.fit.centres, result.fit.widths)):
        mark = " <-" if k == result.component else ""
        click.echo(f"population  {k}  E={centre:.3f}  sigma={width:.3f}{mark}")
    if result.binding is not None:
        click.echo(
            f"Kd          {result.binding.kd:.4g} {unit} "
            f"(hill {result.binding.hill:.2f}, chi2r {result.binding.chi2r:.3g})"
        )
    else:
        click.echo("Kd          not fitted (needs at least three concentrations)")


if __name__ == "__main__":
    cli()

"""Headless CLI for simulating FCS saturation curves."""

from __future__ import annotations

import json

import click
import numpy as np

from chisurf.plugins.calculator.fcs_saturation_calc.api import (
    calculate_fcs_curves,
    isomerisation_scheme,
    triplet_scheme,
    two_state_scheme,
    volume_expansion,
)

SCHEMES = {
    "two-state": two_state_scheme,
    "triplet": triplet_scheme,
    "isomerisation": isomerisation_scheme,
}


@click.command()
@click.option(
    "--scheme",
    type=click.Choice(sorted(SCHEMES)),
    default="triplet",
    show_default=True,
    help="Built-in photochemical scheme. Use --scheme-file for your own.",
)
@click.option(
    "--scheme-file",
    type=click.Path(exists=True),
    default=None,
    help="JSON scheme with dark_matrix, exc_matrix and brightness (overrides --scheme).",
)
@click.option(
    "--power", "-p", type=float, default=2.0, show_default=True, help="Excitation power in mW."
)
@click.option(
    "--extinction",
    "-e",
    type=float,
    default=100000.0,
    show_default=True,
    help="Molar extinction coefficient at the excitation wavelength (1/M cm).",
)
@click.option(
    "--dye",
    default=None,
    help="MMFDB dye name; reads epsilon at --wavelength from its spectrum, overriding -e.",
)
@click.option(
    "--wavelength", type=float, default=488.0, show_default=True, help="Excitation wavelength in nm."
)
@click.option("--w-r", type=float, default=250.0, show_default=True, help="Lateral waist in nm.")
@click.option("--w-z", type=float, default=1000.0, show_default=True, help="Axial waist in nm.")
@click.option(
    "--diffusion",
    "-d",
    type=float,
    default=10.0,
    show_default=True,
    help="Diffusion coefficient in um^2/s.",
)
@click.option(
    "--n-molecules", "-n", type=float, default=1.0, show_default=True, help="Number of molecules."
)
@click.option("--no-bunching", is_flag=True, help="Drop the photokinetic bunching term.")
@click.option(
    "--out-csv", type=click.Path(), default=None, help="Write the calculated curves to a CSV file."
)
@click.option("--json", "as_json", is_flag=True, help="Print the summary as JSON.")
def cli(
    scheme,
    scheme_file,
    power,
    extinction,
    dye,
    wavelength,
    w_r,
    w_z,
    diffusion,
    n_molecules,
    no_bunching,
    out_csv,
    as_json,
):
    """Simulate FCS saturation curves for an arbitrary photochemical scheme.

    Compares the unperturbed Gaussian FCS curve against the numerically
    integrated saturated curve, and reports the effective-volume expansion.
    """
    if scheme_file:
        with open(scheme_file, encoding="utf-8") as handle:
            data = json.load(handle)
        dark_matrix = np.asarray(data["dark_matrix"], dtype=float)
        exc_matrix = np.asarray(data["exc_matrix"], dtype=float)
        brightness = np.asarray(data["brightness"], dtype=float)
        scheme_name = data.get("name", scheme_file)
    else:
        dark_matrix, exc_matrix, brightness = SCHEMES[scheme]()
        scheme_name = scheme

    epsilon_source = "given"
    if dye:
        from chisurf.core.fluorescence.fret.dyes import extinction_at

        resolved = extinction_at(dye, wavelength)
        if resolved is None:
            raise click.ClickException(
                f"MMFDB has no absorption spectrum for {dye!r}; pass --extinction instead."
            )
        extinction = float(resolved)
        epsilon_source = f"mmfdb:{dye}"

    tau_ms, g_unpert, g_sat = calculate_fcs_curves(
        power_mW=power,
        extinction=extinction,
        dark_matrix=dark_matrix,
        exc_matrix=exc_matrix,
        brightness=brightness,
        w_r_nm=w_r,
        w_z_nm=w_z,
        D_um2s=diffusion,
        N=n_molecules,
        include_bunching=not no_bunching,
        wavelength_nm=wavelength,
    )
    v_rel = volume_expansion(
        power_mW=power,
        extinction=extinction,
        dark_matrix=dark_matrix,
        exc_matrix=exc_matrix,
        brightness=brightness,
        w_r_nm=w_r,
        w_z_nm=w_z,
        wavelength_nm=wavelength,
    )

    if out_csv:
        lines = ["tau_ms,g_unperturbed,g_saturated"]
        lines += [f"{t:.6g},{gu:.6g},{gs:.6g}" for t, gu, gs in zip(tau_ms, g_unpert, g_sat)]
        with open(out_csv, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        click.echo(f"Wrote {out_csv}")

    result = {
        "scheme": scheme_name,
        "n_states": int(dark_matrix.shape[0]),
        "power_mW": power,
        "wavelength_nm": wavelength,
        "extinction": extinction,
        "extinction_source": epsilon_source,
        "g_unperturbed_0": float(g_unpert[0]),
        "g_saturated_0": float(g_sat[0]),
        "amplitude_ratio": float(g_sat[0] / g_unpert[0]) if g_unpert[0] > 0 else 0.0,
        "v_eff_over_v0": v_rel,
    }

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"FCS saturation — {scheme_name} ({result['n_states']} states)")
        click.echo(
            f"Power {power} mW at {wavelength:g} nm | "
            f"eps = {extinction:g} M-1cm-1 ({epsilon_source})"
        )
        click.echo(f"Unperturbed G(0): {g_unpert[0]:.4f}")
        click.echo(f"Saturated G(0):   {g_sat[0]:.4f}")
        click.echo(f"V_eff / V_0:      {v_rel:.4f}")


if __name__ == "__main__":
    cli()

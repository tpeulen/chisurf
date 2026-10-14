"""
Command-line interface for lltf.

This module provides a command-line interface for fitting lifetime spectra to
fluorescence decay data.
"""

import os
import sys

import click
import yaml

from chisurf.core.cli.support import DidYouMeanGroup

from .fitter import fit_lifetime


@click.group(cls=DidYouMeanGroup)
def cli():
    """Lifetime fitter command-line interface."""
    pass


@cli.command()
@click.argument("decay_file", type=click.Path(exists=True))
@click.argument("irf_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output JSON file")
@click.option("--plot", "-p", type=click.Path(), help="Output plot file")
@click.option(
    "--save-path",
    "-sp",
    type=click.Path(),
    help='Path to save all output files (creates a subfolder named "lltf_output" in data location if not specified)',
)
@click.option("--config", "-c", type=click.Path(exists=True), help="Configuration YAML file")
@click.option(
    "--n-lifetimes",
    "-n",
    type=int,
    default=None,
    help="Number of lifetimes to fit; given without --find-optimal it also switches off a "
    "configuration's find_optimal (default 1)",
)
@click.option(
    "--find-optimal", "-f", is_flag=True, help="Find optimal number of lifetimes automatically"
)
@click.option(
    "--max-lifetimes",
    "-m",
    type=int,
    default=None,
    help="Maximum number of lifetimes to try when finding optimal (default: the configuration's, 6)",
)
@click.option(
    "--prob-threshold",
    "-pt",
    type=float,
    default=None,
    help="Probability threshold for selecting the best number of lifetimes "
    "(default: the configuration's, 0.68)",
)
@click.option(
    "--selection-mode",
    "-sm",
    type=click.Choice(["lower", "upper"]),
    default=None,
    help="Mode for selecting the best number of lifetimes (lower: fewer components, upper: "
    "more components; default: the configuration's, lower)",
)
@click.option(
    "--noise-model",
    "-nm",
    type=click.Choice(["neyman", "poisson"]),
    default=None,
    help="Objective: poisson (deviance 2I*, unbiased, the default; the decay must be raw photon "
    "counts) or neyman (data-weighted chi-square; any curve). Overrides the configuration.",
)
@click.option("--skiprows", "-s", type=int, default=0, help="Number of rows to skip in data files")
@click.option("--delimiter", "-d", type=str, default=None, help="Delimiter used in data files")
@click.option("--time-column", "-t", type=int, default=0, help="Column index for time data")
@click.option("--counts-column", "-y", type=int, default=1, help="Column index for counts data")
@click.option("--verbose", "-v", is_flag=True, help="Print verbose output")
@click.option(
    "--save-intermediate",
    "-si",
    is_flag=True,
    default=False,
    help="Save intermediate results when finding optimal number of lifetimes (default: disabled)",
)
@click.option(
    "--intermediate-base",
    "-ib",
    type=click.Path(),
    help="Base filename for intermediate results (defaults to output filename without extension)",
)
def fit(
    decay_file,
    irf_file,
    output,
    plot,
    save_path,
    config,
    n_lifetimes,
    find_optimal,
    max_lifetimes,
    prob_threshold,
    selection_mode,
    noise_model,
    skiprows,
    delimiter,
    time_column,
    counts_column,
    verbose,
    save_intermediate,
    intermediate_base,
):
    """Fit a lifetime to decay data.

    DECAY_FILE is the path to the decay data file.
    IRF_FILE is the path to the IRF data file.
    """
    # Load configuration
    config_dict = {}
    if config:
        try:
            with open(config) as f:
                config_dict = yaml.safe_load(f)
        except Exception as e:
            click.echo(f"Error loading configuration file: {e}", err=True)
            sys.exit(1)

    # Handle save path and create output directory if needed
    output_dir = None

    if save_path is not None:
        # Use user-provided save path
        output_dir = save_path
        # Create the directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        click.echo(f"Using save path: {output_dir}")
    else:
        # Create a subfolder in the data file location
        data_dir = os.path.dirname(os.path.abspath(decay_file))
        output_dir = os.path.join(data_dir, "lltf_output")
        # Create the directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        click.echo(f"Created output directory: {output_dir}")

    # Get the base filename without path and extension
    base_filename = os.path.splitext(os.path.basename(decay_file))[0]

    # Set default output file if not specified
    if output is None:
        output = os.path.join(output_dir, f"{base_filename}_fit.json")
    elif not os.path.isabs(output):
        # If output is a relative path, make it relative to the output directory
        output = os.path.join(output_dir, output)

    # Set default plot file if not specified
    if plot is None:
        plot = os.path.join(output_dir, f"{base_filename}_fit.png")
    elif not os.path.isabs(plot):
        # If plot is a relative path, make it relative to the output directory
        plot = os.path.join(output_dir, plot)

    # Fit lifetime
    # The command line decides over the configuration: -f searches, an explicit -n fixes the
    # count. -n used to be ignored whenever the configuration had find_optimal: true (the
    # shipped example does), so a GUI asking for 2 lifetimes got a search and 3.
    if find_optimal or n_lifetimes is not None:
        config_dict.setdefault("lifetime_fit_parameter", {})["find_optimal"] = bool(find_optimal)
    n_lifetimes = 1 if n_lifetimes is None else n_lifetimes
    if noise_model is not None:
        config_dict.setdefault("lifetime_fit_parameter", {})["noise_model"] = noise_model
    # Only options actually given override the configuration; an unset one used to
    # overwrite the file with the CLI's own default (selection_mode "lower" always won).
    for key, value in (
        ("maximum_number_of_lifetimes", max_lifetimes),
        ("prob_threshold", prob_threshold),
        ("selection_mode", selection_mode),
    ):
        if value is not None:
            config_dict.setdefault("lifetime_fit_parameter", {})[key] = value

    # Set default intermediate_base if not specified but save_intermediate is enabled
    if save_intermediate and not intermediate_base:
        # Use the same directory as the output file, but with a base name derived from the decay file
        intermediate_base = os.path.join(output_dir, f"{base_filename}_intermediate")
        click.echo(f"No intermediate base filename specified, using: {intermediate_base}")
    elif intermediate_base and not os.path.isabs(intermediate_base):
        # If intermediate_base is a relative path, make it relative to the output directory
        intermediate_base = os.path.join(output_dir, intermediate_base)

    # Determine whether to save intermediate results
    # Only save intermediates if find_optimal is True AND save_intermediate is True
    should_save_intermediates = find_optimal and save_intermediate

    # Handle save_intermediate based on find_optimal flag
    if save_intermediate and not find_optimal:
        # User explicitly enabled save_intermediate but didn't use find_optimal
        click.echo("Note: --save-intermediate is only effective with --find-optimal")
        # We don't automatically enable find_optimal anymore
        # Instead, we'll pass save_intermediate=True to fit_lifetime, but it will only
        # have an effect if find_optimal is enabled in the config

    # Inform user about saving intermediate results
    if should_save_intermediates:
        click.echo(f"Intermediate results will be saved with base filename: {intermediate_base}")
    elif save_intermediate and not find_optimal:
        click.echo(
            "Note: Intermediate results will not be saved because --find-optimal is not enabled"
        )

    # Always disable plotting to screen: the fit is written to the plot file instead. The
    # optimal-number search's probability and residual figures are switched by their own keys;
    # left on, their plt.show() blocks a run started from a GUI or without a display.
    if "plot_resulting_fit" in config_dict:
        config_dict["plot_resulting_fit"] = False
    fit_parameters = config_dict.get("lifetime_fit_parameter")
    if isinstance(fit_parameters, dict):
        fit_parameters["plot_probabilities"] = False
        fit_parameters["plot_weighted_residuals"] = False

    result = fit_lifetime(
        decay_file=decay_file,
        irf_file=irf_file,
        n_lifetimes=n_lifetimes,
        skiprows=skiprows,
        delimiter=delimiter,
        time_column=time_column,
        counts_column=counts_column,
        output_file=output,
        plot_file=plot,
        verbose=verbose,
        config=config_dict,
        save_intermediate_results=should_save_intermediates,
        intermediate_results_base_filename=intermediate_base,
    )

    if result.get("converged", False):
        click.echo("Fit completed successfully.")
    else:
        click.echo("Fit completed with optimizer warning.")
        click.echo(result.get("optimizer_message", "Optimizer convergence was not reported."))
    click.echo(f"Results saved to {output}")
    click.echo(f"Plot saved to {plot}")

    # Print summary of results
    click.echo("\nFit results summary:")
    for i in range(result["n_lifetimes"]):
        lifetime = result["lifetime_spectrum"][2 * i + 1]
        amplitude = result["lifetime_spectrum"][2 * i]
        click.echo(f"Lifetime {i + 1}: {lifetime:.3f} ns, Amplitude: {amplitude:.3f}")

    click.echo(f"IRF shift: {result['irf_shift']:.3f} ns")
    click.echo(f"Decay background: {result['decay_background']:.2f}")
    click.echo(f"Reduced chi-square: {result['reduced_chi_square']:.2f}")


@cli.command("fit-vvvh")
@click.argument("decay_file", type=click.Path(exists=True))
@click.argument("irf_file", type=click.Path(exists=True))
@click.option(
    "--vh",
    "vh_file",
    type=click.Path(exists=True),
    help="VH channel as a two-column file (time, counts); DECAY_FILE is then VV",
)
@click.option(
    "--irf-vh",
    type=click.Path(exists=True),
    help="VH IRF as a two-column file; without it IRF_FILE serves both channels",
)
@click.option("--output", "-o", type=click.Path(), help="Output JSON file")
@click.option("--plot", "-p", type=click.Path(), help="Output plot file (VV, VH, residuals, r(t))")
@click.option(
    "--save-path",
    "-sp",
    type=click.Path(),
    help="Output directory (default: lltf_output beside the data)",
)
@click.option("--config", "-c", type=click.Path(exists=True), help="Configuration YAML file")
@click.option("--n-lifetimes", "-n", type=int, default=None, help="Number of lifetimes (default 1)")
@click.option(
    "--find-optimal", "-f", is_flag=True, help="Choose the number of lifetimes by the F test"
)
@click.option(
    "--max-lifetimes", "-m", type=int, default=None, help="Largest number of lifetimes tried"
)
@click.option("--prob-threshold", "-pt", type=float, default=None, help="F-test acceptance level")
@click.option("--selection-mode", "-sm", type=click.Choice(["lower", "upper"]), default=None)
@click.option(
    "--n-rotations", "-nr", type=int, default=None, help="Number of rotational correlation times"
)
@click.option("--r-inf/--no-r-inf", default=None, help="Fit a residual anisotropy r_inf")
@click.option(
    "--g-factor",
    "-g",
    type=float,
    default=None,
    help="G = S_par/S_perp (divides VH); default: the data's, else the configuration's",
)
@click.option("--l1", type=float, default=None, help="Schaffer mixing factor of VV")
@click.option("--l2", type=float, default=None, help="Schaffer mixing factor of VH")
@click.option(
    "--channel-width", "-dt", type=float, default=None, help="ns per channel of a stacked file"
)
@click.option("--noise-model", "-nm", type=click.Choice(["neyman", "poisson"]), default=None)
@click.option("--verbose", "-v", is_flag=True, help="Print verbose output")
def fit_vvvh(
    decay_file,
    irf_file,
    vh_file,
    irf_vh,
    output,
    plot,
    save_path,
    config,
    n_lifetimes,
    find_optimal,
    max_lifetimes,
    prob_threshold,
    selection_mode,
    n_rotations,
    r_inf,
    g_factor,
    l1,
    l2,
    channel_width,
    noise_model,
    verbose,
):
    """Fit a VV/VH pair jointly: lifetimes, rotational correlation times and r0.

    DECAY_FILE is a stacked VV/VH file (one column, the vv_vh format), a
    three-column file (time, VV, VH), or the VV channel with --vh. IRF_FILE is
    one IRF for both channels (time, counts), or a pair in the same forms.
    """
    from .polarized import fit_polarized

    config_dict = {}
    if config:
        with open(config) as f:
            config_dict = yaml.safe_load(f) or {}
    fit_parameters = config_dict.setdefault("lifetime_fit_parameter", {})
    pol = config_dict.setdefault("polarization_parameter", {})
    # Only options actually given override the configuration.
    for target, key, value in (
        (fit_parameters, "number_of_lifetimes", n_lifetimes),
        (fit_parameters, "maximum_number_of_lifetimes", max_lifetimes),
        (fit_parameters, "prob_threshold", prob_threshold),
        (fit_parameters, "selection_mode", selection_mode),
        (fit_parameters, "noise_model", noise_model),
        (pol, "number_of_rotations", n_rotations),
        (pol, "fit_r_infinity", r_inf),
        (pol, "channel_width", channel_width),
    ):
        if value is not None:
            target[key] = value
    if find_optimal or n_lifetimes is not None:
        fit_parameters["find_optimal"] = bool(find_optimal)

    output_dir = save_path or os.path.join(
        os.path.dirname(os.path.abspath(decay_file)), "lltf_output"
    )
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(decay_file))[0]
    output = output or os.path.join(output_dir, f"{base}_vvvh_fit.json")
    plot = plot or os.path.join(output_dir, f"{base}_vvvh_fit.png")

    result = fit_polarized(
        decay_file,
        irf_file,
        vh_decay=vh_file,
        irf_vh=irf_vh,
        config=config_dict,
        g_factor=g_factor,
        l1=l1,
        l2=l2,
        output_file=output,
        plot_file=plot,
        verbose=verbose,
    )
    if result.get("converged", False):
        click.echo("Fit completed successfully.")
    else:
        click.echo("Fit completed with optimizer warning.")
        click.echo(result.get("optimizer_message", ""))
    click.echo(f"Results saved to {output}")
    click.echo(f"Plot saved to {plot}")
    click.echo("\nFit results summary:")
    for i, row in enumerate(result["lifetimes"], 1):
        click.echo(f"Lifetime {i}: {row['lifetime']:.3f} ns, Amplitude: {row['amplitude']:.3f}")
    for i, row in enumerate(result["rotations"], 1):
        click.echo(f"Rotation {i}: {row['rho']:.3f} ns, b: {row['b']:.3f}")
    click.echo(f"r0: {result['r0']:.3f}")
    if result["fit_r_infinity"]:
        click.echo(f"r_inf: {result['r_infinity']:.3f}")
    source = result["calibration_source"]
    click.echo(
        f"g: {result['g_factor']:.4g} ({source['g_factor']}), "
        f"l1: {result['l1']:.4g} ({source['l1']}), l2: {result['l2']:.4g} ({source['l2']})"
    )
    click.echo(
        f"Reduced chi-square: {result['reduced_chi_square']:.2f} "
        f"(VV {result['reduced_chi_square_vv']:.2f}, VH {result['reduced_chi_square_vh']:.2f})"
    )


@cli.command("demo-vvvh")
@click.argument("folder", type=click.Path())
def demo_vvvh(folder):
    """Write the simulated VV/VH demo pair (known tau, rho, r0, g) and print its paths."""
    from .polarized import DEMO, write_demo

    decay_file, irf_file = write_demo(folder)
    click.echo(f"decay: {decay_file}")
    click.echo(f"irf: {irf_file}")
    click.echo(
        f"truth: lifetimes {DEMO['lifetimes']} ns, fractions {DEMO['amplitudes']}, "
        f"rho {DEMO['rho']} ns, r0 {DEMO['r0']}, g {DEMO['g_factor']}"
    )


def main():
    """Entry point for the command-line interface."""
    cli()


if __name__ == "__main__":
    main()

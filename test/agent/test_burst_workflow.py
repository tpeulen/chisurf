"""The composed analysis: bursts -> selection -> sub-ensemble decay -> distance.

This is the workflow the `fret-from-bursts` skill describes, run end to end on
a real Becker & Hickl single-molecule DNA measurement. The skill is prose and
cannot be tested; what can be tested is that every primitive it tells the
assistant to use behaves as it claims — because a skill built on a wrong
assumption produces confident nonsense rather than an error.

The scientific payoff is the last test: the FRET efficiency from the donor
lifetime must agree with the proximity ratio of the selected bursts. Those are
independent observables, so agreement is evidence that the whole chain — burst
indices, channel roles, decay construction, IRF, fitting — is right.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

DATA = (
    pathlib.Path(__file__).resolve().parents[2]
    / "chisurf"
    / "plugins"
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
)
BUR_DIR = DATA / "burstwise_All 0.1000#15" / "bi4_bur"
FILE_TYPE = "SPC-130"
GREEN, RED = [0, 8], [1, 9]
#: The whole measurement. A subset is not a cheaper version of this test: with
#: three of the ten files the FRET population keeps only ~2600 donor photons,
#: the two-component fit stops being determined (reduced chi-square 0.43) and
#: the efficiency comes out at 0.14 instead of 0.53. Too few photons is a real
#: failure mode of this analysis, not a testing inconvenience.
FILES = tuple(f"m{index:03d}.spc" for index in range(10))
N_BINS = 4096


@pytest.fixture(scope="module")
def bursts():
    """Return the burst table of the sample measurement, with proximity ratios."""
    pd = pytest.importorskip("pandas")
    if not BUR_DIR.is_dir():
        pytest.skip(f"no burst analysis at {BUR_DIR}")

    frames = []
    for path in sorted(BUR_DIR.glob("*.bur")):
        if path.stem + ".spc" not in FILES:
            continue
        table = pd.read_csv(path, sep="\t")
        table = table[table["Number of Photons"] > 0].copy()
        table["file"] = path.stem + ".spc"
        frames.append(table)
    if not frames:
        pytest.skip("no .bur tables for the selected files")

    table = pd.concat(frames, ignore_index=True)
    green = table["Number of Photons (green)"].to_numpy(float)
    red = table["Number of Photons (red)"].to_numpy(float)
    table["PR"] = red / (green + red)
    return table


def _stream(name):
    """Return (routing channels, micro times) of one photon file."""
    tttrlib = pytest.importorskip("tttrlib")
    data = tttrlib.TTTR(str(DATA / name), FILE_TYPE)
    return np.asarray(data.routing_channels), np.asarray(data.micro_times)


def test_the_burst_photon_indices_have_an_exclusive_end(bursts):
    """The skill tells the assistant to slice ``photons[first:last]``.

    Off by one here silently changes every burst, so it is checked against the
    per-colour counts the analysis itself recorded.
    """
    counted = {"green": 0, "red": 0}
    for name in FILES:
        routing, _ = _stream(name)
        part = bursts[bursts["file"] == name]
        for first, last in zip(part["First Photon"].astype(int), part["Last Photon"].astype(int)):
            window = routing[first:last]
            counted["green"] += int(np.isin(window, GREEN).sum())
            counted["red"] += int(np.isin(window, RED).sum())

    assert counted["green"] == int(bursts["Number of Photons (green)"].sum())
    assert counted["red"] == int(bursts["Number of Photons (red)"].sum())


def test_the_measurement_has_a_donor_only_and_a_fret_population(bursts):
    """The reference the workflow depends on has to actually be there."""
    donor_only = bursts[bursts.PR < 0.2]
    fret = bursts[(bursts.PR >= 0.5) & (bursts.PR <= 0.7)]

    assert len(donor_only) > 50, "no donor-only population to use as a reference"
    assert len(fret) > 50, "no bursts in the requested FRET window"


@pytest.fixture(scope="module")
def analysis(bursts, tmp_path_factory):
    """Run the whole chain once: decays, IRF, fits, efficiency."""
    from chisurf.core.fluorescence.burst.irf_bg import extract_irf_background

    tttrlib = pytest.importorskip("tttrlib")
    workspace = tmp_path_factory.mktemp("setcspc")

    populations = {
        "donor_only": bursts.PR < 0.2,
        "fret": (bursts.PR >= 0.5) & (bursts.PR <= 0.7),
    }
    decays = {name: np.zeros(N_BINS, np.int64) for name in populations}
    irf = np.zeros(N_BINS, float)
    axis = None

    for name in FILES:
        data = tttrlib.TTTR(str(DATA / name), FILE_TYPE)
        routing = np.asarray(data.routing_channels)
        micro = np.asarray(data.micro_times)
        for label, mask in populations.items():
            part = bursts[mask & (bursts["file"] == name)]
            for first, last in zip(
                part["First Photon"].astype(int), part["Last Photon"].astype(int)
            ):
                photons = micro[first:last][np.isin(routing[first:last], GREEN)]
                decays[label] += np.bincount(photons, minlength=N_BINS)[:N_BINS]
        estimate = extract_irf_background(
            data, {"green": {"chs": GREEN, "micro_time_ranges": []}}
        )["green"]
        irf += estimate.irf
        axis = estimate.time_ns

    for label, counts in decays.items():
        np.savetxt(workspace / f"{label}.dat", np.column_stack([axis, counts]), fmt="%.6f\t%d")
    np.savetxt(
        workspace / "irf.dat",
        np.column_stack([axis, np.round(irf / irf.sum() * 1e6)]),
        fmt="%.6f\t%d",
    )

    from chisurf.core.agent import AgentContext
    from chisurf.core.agent.tools import data as data_tools
    from chisurf.core.agent.tools import decay as decay_tools
    from chisurf.core.agent.tools import fitting as fit_tools

    context = AgentContext(working_directory=str(workspace))
    data_tools.load_data(context, directory=".", pattern="*.dat", experiment="TCSPC")
    names = [str(getattr(d, "name", "")) for d in context.datasets]
    irf_index = next(i for i, n in enumerate(names) if "irf" in n.lower())
    samples = [i for i, n in enumerate(names) if i != irf_index]
    fit_tools.create_fit(context, datasets=samples, model_name="Lifetime")

    results = {}
    for position, dataset in enumerate(samples):
        label = "donor_only" if "donor_only" in names[dataset] else "fret"
        decay_tools.set_irf(context, fit=position, irf=irf_index)
        decay_tools.set_components(context, fit=position, n=2)
        outcome = fit_tools.run_fit(context, fit=position)["results"][0]
        values = {p["name"]: p["value"] for p in fit_tools.get_fit(context, fit=position)["parameters"]}
        x1, x2 = values.get("xL1", 0.0), values.get("xL2", 0.0)
        t1, t2 = values.get("tL1", 0.0), values.get("tL2", 0.0)
        results[label] = {
            "chi2r": outcome["chi2r"],
            "tau_x": (x1 * t1 + x2 * t2) / ((x1 + x2) or 1.0),
            "photons": int(decays[label].sum()),
        }
    return results


def test_every_population_yields_a_decay_worth_fitting(analysis):
    assert analysis["donor_only"]["photons"] > 5000
    assert analysis["fret"]["photons"] > 1000


def test_both_sub_ensemble_fits_describe_their_decay(analysis):
    for label, outcome in analysis.items():
        assert 0.5 < outcome["chi2r"] < 2.0, f"{label}: chi2r {outcome['chi2r']}"


def test_fret_shortens_the_donor_lifetime(analysis):
    """The direction is the whole physics: an acceptor quenches the donor."""
    assert analysis["fret"]["tau_x"] < analysis["donor_only"]["tau_x"]


def test_the_lifetime_efficiency_agrees_with_the_proximity_ratio(analysis):
    """Independent observables, so this is evidence rather than a tautology.

    The selection window is PR 0.5-0.7. An efficiency from the donor decay that
    lands in the same region means the burst indices, the channel roles, the
    decay construction and the shared IRF are all right; a mistake in any of
    them moves it out.
    """
    efficiency = 1.0 - analysis["fret"]["tau_x"] / analysis["donor_only"]["tau_x"]
    assert 0.35 < efficiency < 0.8, f"lifetime efficiency {efficiency:.3f} is far from the PR window"

    r0 = 52.0
    distance = r0 * (1.0 / efficiency - 1.0) ** (1.0 / 6.0)
    assert 35.0 < distance < 70.0, f"implausible distance {distance:.1f} A"


def test_the_workflow_prompt_loads_the_skill():
    """Deterministic routing: the request must reach this procedure."""
    from chisurf.core.agent.skills import SkillLibrary

    library = SkillLibrary.discover()
    matched = [
        skill.name
        for skill in library.match(
            "process the smfret burst data, select bursts with proximity ratio "
            "0.5-0.7 and determine the distance by tcspc"
        )
    ]
    assert "fret-from-bursts" in matched

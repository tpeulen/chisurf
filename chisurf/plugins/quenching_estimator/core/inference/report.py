"""Plain-language text of a quenching analysis, written from its numbers.

Every sentence here is computed from a result (:mod:`.graph_fit`, :mod:`.stages`): nothing is
a canned conclusion. The GUI shows these texts; the API returns them in
``AnalysisResult.to_dict()``. The wording follows the MalE prototype's ``explain`` (notebook
cells 31 and 58), with one change: the quench-scale interval is reported by method (Laplace
samples and, where computed, the profile likelihood), and the text says when two stages give
the same interval instead of claiming that one narrows the other.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "explain",
    "dye_line",
    "summary_text",
    "transfer_text",
    "water_access_text",
    "profile_text",
    "compare_profiles",
]


def _g(x):
    """Two significant digits.

    Parameters
    ----------
    x : float

    Returns
    -------
    str
    """
    return f"{x:.2g}"


def _determined(view, label):
    """Whether a parameter is fitted and determined.

    Parameters
    ----------
    view : graph_fit.BlockResult
    label : str

    Returns
    -------
    bool
    """
    try:
        e = view.estimate(label)
    except KeyError:
        return False
    return not e["note"].startswith("not determined")


def explain(view, groups):
    """What one data set's fit says, in plain words.

    Parameters
    ----------
    view : graph_fit.BlockResult
    groups : sequence of str
        Residue groups of the stickiness.

    Returns
    -------
    str
        Markdown bullet list.
    """
    t = view.table
    d = t["tau_pred"] - t["tau_x"]
    def rng(label):
        e = view.estimate(label)
        return f"{_g(e['low'])}–{_g(e['high'])}"

    text = [f"**What the analysis says about {view.label}:**", ""]
    text.append(
        f"* The **best fit** reproduces the {len(t)} measured lifetimes with a typical deviation "
        f"of **{np.median(np.abs(d)):.2f} ns** (rms {np.sqrt((d ** 2).mean()):.2f} ns); the "
        f"model's own error is {view.model_error:.2f} ns. The typical prediction error (from the "
        f"error bars of all parameters, including the titrations) is "
        f"{np.median(t['pred_sd']):.2f} ns.")
    if _determined(view, "scale"):
        e = view.estimate("scale")
        text.append(
            f"* **Quench strength:** contact quenching on the protein is **{_g(e['value'])}×** "
            f"the value measured with free amino acids (68 %: {rng('scale')}).")
        if "other regions" in e["note"] and "ln_scale" in view.block.free:
            i = view.block.free.index("ln_scale")
            best = view.searches[0][1]
            others = [np.exp(x[i]) for x, lp in view.searches[1:] if lp > best - 2.0]
            text.append("  *Careful:* other searches found almost equally good fits with a "
                        "quench scale of " + ", ".join(f"{_g(v)}×" for v in sorted(others)) + ".")
    else:
        text.append(f"* **Quench strength:** *not determined*: anything between "
                    f"{rng('scale')}× the titration value fits.")
    found = [(g, view.estimate(f"s_{g}")["value"]) for g in groups if _determined(view, f"s_{g}")]
    if found:
        ranked = sorted(found, key=lambda x: x[1])
        text.append("* **Stickiness** (smaller = stickier): "
                    + ", ".join(f"{g} {_g(v)}" for g, v in ranked)
                    + f". The dye sticks most to **{ranked[0][0]}** residues.")
    missing = [g for g in groups if not _determined(view, f"s_{g}")]
    if missing:
        text.append(f"* Not determined by these data: stickiness of {', '.join(missing)}.")
    if _determined(view, "delta"):
        delta = view.estimate("delta")["value"]
        text.append(
            f"* **Contact distance:** shifted by **{delta:+.1f} Å** ({rng('delta')} Å): "
            + ("the dye must come *closer* than the textbook distance to be quenched."
               if delta < 0 else "quenching reaches a bit *further* than the textbook distance."))
    if _determined(view, "decay_length"):
        e = view.estimate("decay_length")
        text.append(
            f"* **Quenching range:** beyond the contact distance the rate falls e-fold every "
            f"**{e['value']:.2f} Å** ({rng('decay_length')} Å).")
    dark = float(np.mean(t["dark_fraction"]))
    if dark > 0.02:
        text.append(f"* **Invisible dye:** on average {100 * dark:.0f} % of the dye is dark "
                    "(quenched faster than the shortest measurable lifetime, or in a static "
                    "complex).")
    if "dtau_shield" in view.block.free:
        e = view.estimate("dtau_shield")
        text.append(f"* **Brighter when shielded:** a dye position fully covered by protein lives "
                    f"**{e['value']:.2f} ns** longer ({rng('dtau_shield')} ns).")
    bad = view.stats["outliers"]
    text.append("* **Outliers** (a left-out site predicted more than 3 error bars off): "
                + (", ".join(map(str, bad)) if bad else "none") + ".")
    return "\n".join(text)


def dye_line(view, groups):
    """The summary numbers of one dye's final data set.

    Parameters
    ----------
    view : graph_fit.BlockResult
    groups : sequence of str

    Returns
    -------
    dict
        ``dye``, ``block``, ``scale``, ``scale_low``, ``scale_high``, ``scale_note``,
        ``stickiest_group``, ``outliers``.
    """
    e = view.estimate("scale")
    found = [(g, view.estimate(f"s_{g}")["value"]) for g in groups if _determined(view, f"s_{g}")]
    sticky = min(found, key=lambda x: x[1])[0] if found else "no group (not determined)"
    return dict(dye=view.dye, block=view.label, scale=e["value"], scale_low=e["low"],
                scale_high=e["high"], scale_note=e["note"], stickiest_group=sticky,
                outliers=list(view.stats["outliers"]))


def summary_text(lines):
    """The story in numbers, one bullet per dye.

    Parameters
    ----------
    lines : sequence of dict
        From :func:`dye_line`.

    Returns
    -------
    str
    """
    out = ["**The story in numbers (from this run):**", ""]
    for line in lines:
        if line["scale_note"].startswith("not determined"):
            scale = "quench scale not determined"
        else:
            scale = (f"quench scale {_g(line['scale'])} "
                     f"({_g(line['scale_low'])}–{_g(line['scale_high'])})")
        bad = ", ".join(map(str, line["outliers"])) or "none"
        out.append(f"* **{line['dye']}:** {scale}; stickiest near **{line['stickiest_group']}** "
                   f"residues; outlier sites: {bad}.")
    return "\n".join(out)


def transfer_text(numbers, dye, solvent):
    """The transfer test's result (expected to fail).

    Parameters
    ----------
    numbers : dict
        ``median_abs_dev``, ``sites_above_free_tau0``, ``n``, ``tau0``, ``source``.
    dye, solvent : str

    Returns
    -------
    str
    """
    return (f"{dye} in {solvent} predicted from {numbers['source']} with the free dye's "
            f"lifetime {numbers['tau0']:.2f} ns and no water term: typical distance "
            f"**{numbers['median_abs_dev']:.2f} ns**; {numbers['sites_above_free_tau0']} of "
            f"{numbers['n']} sites live longer than the free dye in {solvent}. On the protein the "
            f"dye is shielded from water, so the free dye's water quenching overestimates it; the "
            f"joint fit of both solvents (water = kq_w,free × exposure) is the test that counts.")


def water_access_text(numbers):
    """Measured against model water access.

    Parameters
    ----------
    numbers : dict
        ``r_all``, ``r_without``, ``without``.

    Returns
    -------
    str
    """
    without = ", ".join(map(str, numbers["without"])) or "none"
    return (f"**Water access per site** (1 = like the free dye): the model's values agree with "
            f"the measured ones with r = {numbers['r_all']:.2f} (without {without}: "
            f"{numbers['r_without']:.2f}).")


def profile_text(label, numbers):
    """The quench-scale interval by method.

    Parameters
    ----------
    label : str
    numbers : dict
        A stage's ``numbers["blocks"][label]`` (``scale_laplace``, ``scale_profile``).

    Returns
    -------
    str
    """
    lap = numbers["scale_laplace"]
    text = (f"{label}: quench scale {_g(lap['median'])}× (Laplace: 68 % between "
            f"{_g(lap['low'])}× and {_g(lap['high'])}×, a factor {lap['factor']:.1f} wide)")
    prof = numbers.get("scale_profile")
    if prof:
        text += (f"; profile likelihood {_g(prof['best'])}× ({_g(prof['low'])}–"
                 f"{_g(prof['high'])}×, a factor {prof['high'] / prof['low']:.1f} wide)")
    return text + "."


def compare_profiles(first, second, labels):
    """Whether a second fit narrows the quench scale of a first one.

    Parameters
    ----------
    first, second : dict
        ``{"low", "high"}`` (natural units) of each fit's interval.
    labels : tuple of str

    Returns
    -------
    str
        States plainly when the widths agree within 10 %.
    """
    w1 = np.log(first["high"] / first["low"])
    w2 = np.log(second["high"] / second["low"])
    if abs(w2 - w1) <= 0.1 * w1:
        return (f"{labels[1]} gives the quench scale the same width as {labels[0]} "
                f"(factor {np.exp(w2):.1f} vs {np.exp(w1):.1f}): adding the second solvent does "
                f"not narrow it.")
    verb = "narrows" if w2 < w1 else "widens"
    return (f"{labels[1]} {verb} the quench scale from a factor {np.exp(w1):.1f} to "
            f"{np.exp(w2):.1f}.")

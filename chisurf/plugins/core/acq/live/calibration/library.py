"""The shipped calibration workflows: FRET (PIE), polarisation (MFD) and the
per-laser power-diode calibration, plus the editable optics catalog.

Every stage is honest about what it needs and what it records: instructions say
what the operator physically does (the backend never drives hardware), inputs
carry the measured or read values, metrics compute transparent values, and the
accept/reject limits start EMPTY -- the user owns every threshold. The only
shipped numbers are the owner's policies: the available laser wavelengths and
the 3-calendar-month staleness of a power-diode calibration (in
:mod:`.lasers`).

Literature the stages build on:

* Müller, Zaychikov, Bräuchle, Lamb, *Pulsed interleaved excitation*,
  Biophys. J. 89, 3508 (2005), DOI 10.1529/biophysj.105.064766 -- gamma from a
  single doubly-labelled sample.
* Hellenkamp et al., *Precision and accuracy of single-molecule FRET
  measurements*, Nat. Methods 15, 669 (2018), DOI 10.1038/s41592-018-0085-0 --
  the correction-factor nomenclature (alpha, delta, beta, gamma) and the
  calibration workflow these stages follow.
"""

from __future__ import annotations

import datetime

from . import measurements, workflow
from .. import power_calibration
from .lasers import AVAILABLE_LASERS_NM

__all__ = ["build_workflow", "optics_catalog", "step_spec", "STEP_SPECS"]


# -- small builders ------------------------------------------------------------------------------

def _num(key, name, unit="", describe="", required=True, default=None):
    return workflow.InputSpec(key=key, name=name, kind="number", describe=describe,
                              unit=unit, required=required, default=default)


def _txt(key, name, describe="", required=True, default=None):
    return workflow.InputSpec(key=key, name=name, kind="text", describe=describe,
                              required=required, default=default)


def _file(key, name, describe="", required=True):
    return workflow.InputSpec(key=key, name=name, kind="file", describe=describe,
                              required=required)


def _flag(key, name, describe=""):
    return workflow.InputSpec(key=key, name=name, kind="boolean", describe=describe)


def _choice(key, name, choices, describe="", required=True):
    return workflow.InputSpec(key=key, name=name, kind="choice", describe=describe,
                              choices=tuple(choices), required=required)


def _metric(key, name, unit, describe, compute, needs_workflow=False):
    return workflow.MetricSpec(
        key=key, name=name, unit=unit, describe=describe, compute=compute,
        needs_workflow=needs_workflow,
    )


def _result(wf, step, *, quantity, value, unit, source, values, extra=None, note=""):
    return workflow.MeasuredResult(
        quantity=quantity, value=value, unit=unit, step_id=step.id, step_name=step.name,
        source=source, measured_at=workflow._now_iso(),
        sample=str(values.get("sample", "") or ""),
        file=str(values.get("file", "") or ""), note=note, extra=dict(extra or {}),
    )


def _record_metric(quantity, unit):
    """Record one metric's computed value on confirmation."""
    def build(wf, step):
        for m in wf.metrics(step.id):
            if m["key"] == quantity and m["value"] is not None:
                return [_result(wf, step, quantity=quantity, value=float(m["value"]),
                                unit=unit, source="computed", values=wf.state[step.id].values,
                                note=m["detail"])]
        return []
    return build


def _record_preferred(quantity, unit, entered_key, computed_key):
    """Record the user's own fitted value when given, else the computed one."""
    def build(wf, step):
        values = wf.state[step.id].values
        if values.get(entered_key) is not None:
            return [_result(wf, step, quantity=quantity, value=float(values[entered_key]),
                            unit=unit, source="entered", values=values,
                            note="entered by the operator (own fit)")]
        for m in wf.metrics(step.id):
            if m["key"] == computed_key and m["value"] is not None:
                return [_result(wf, step, quantity=quantity, value=float(m["value"]),
                                unit=unit, source="computed", values=values, note=m["detail"])]
        return []
    return build


def _guard_metric_computable(metric_key, message):
    def guard(wf, step):
        for m in wf.metrics(step.id):
            if m["key"] == metric_key:
                if m["value"] is None:
                    return message + f" ({m['detail']})"
                return None
        return message
    return guard


# -- shared stages -------------------------------------------------------------------------------

def _instrument_setup(polarization: bool = False) -> workflow.StepSpec:
    if polarization:
        goal = "The shared Instrument setup (channels, beam splitters, filters) with the polarisation channels identified"
        extra = (
            "Identify the parallel and perpendicular detection channels and the "
            "excitation polarisation. "
        )
    else:
        goal = "The shared Instrument setup (channels, beam splitters, filters) this calibration applies to"
        extra = "Identify the donor and acceptor detection channels and the excitation windows. "
    return workflow.StepSpec(
        id="instrument_setup", spec_id="instrument_setup",
        name="Instrument setup",
        goal=goal,
        instructions=(
            "Record the Instrument setup the whole calibration applies to: lasers, beam "
            "splitters, emission filters and detectors, and how the routing channels map "
            "to them. The editable optics catalog (see the GUI) lists the dyes "
            "(Alexa488, Cy3, Cy5, Rh110, Alexa647, Atto655) and beam splitters -- fill in "
            "the wavelengths and bands from YOUR instrument's data sheets; the catalog "
            "ships empty on purpose. " + extra +
            "Nothing is switched or aligned from here; alignment is the operator's work."
        ),
        inputs=[
            _txt("setup_name", "Setup name", "the Instrument setup this calibration applies to"),
            _txt("setup_notes", "Setup notes", "beam splitters, filters, detectors", required=False),
        ],
        metrics=[],
    )


def _water_irf() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="water_irf", spec_id="water_irf",
        name="Water IRF (instrument response)",
        goal="The instrument's timing response, measured on a scattering solution of water",
        instructions=(
            "Measure the instrument response with a cuvette of water (scatterer): no dye, "
            "laser attenuated as for a routine IRF run. Save the recording and attach the "
            "microtime histogram (or enter the file and let the tool fold it). The IRF is "
            "needed for reconvolution fits; its width is a measured property, not a pass/"
            "fail."
        ),
        inputs=[
            _file("file", "Recording / histogram", "the water-scatter measurement"),
            _num("micro_time_resolution_ns", "Micro time resolution", unit="ns",
                 describe="the TCSPC bin width of the recording"),
        ],
        metrics=[
            _metric(
                "irf_fwhm_ns", "IRF full width at half maximum", "ns",
                "linear interpolation of the half-maximum crossings around the histogram peak",
                lambda v: measurements.irf_fwhm_ns(
                    measurements.load_histogram(v.get("file", "")) if v.get("file") else None,
                    v.get("micro_time_resolution_ns"),
                ),
            ),
        ],
        requires=("instrument_setup",),
        skippable=True,
        result_builders=(_record_metric("irf_fwhm_ns", "ns"),),
    )


def _buffer_background() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="buffer_background", spec_id="buffer_background",
        name="Buffer background",
        goal="The background count rate the sample corrections subtract",
        instructions=(
            "Measure the buffer ALONE (no dye) under exactly the conditions of the "
            "calibration samples: same volume, same cuvette/channel settings, same "
            "acquisition time discipline. Enter the photons collected and the acquisition "
            "time, or attach the recording. The rate is recorded per calibration so later "
            "stages can compare like with like."
        ),
        inputs=[
            _num("photons", "Photons in the buffer run",
                 describe="photons collected over the run"),
            _num("acquisition_time_s", "Acquisition time", unit="s"),
            _txt("sample", "Buffer", "composition and conditions", required=False),
        ],
        metrics=[
            _metric(
                "background_rate_khz", "Background count rate", "kHz",
                "photons divided by the acquisition time",
                lambda v: measurements.background_rate_khz(
                    photons=v.get("photons"), acquisition_time_s=v.get("acquisition_time_s")
                ),
            ),
        ],
        requires=("water_irf",),
        skippable=True,
        result_builders=(_record_metric("background_rate_khz", "kHz"),),
    )


def _reference_dye(step_id, name, dye_hint, quantity) -> workflow.StepSpec:
    return workflow.StepSpec(
        id=step_id, spec_id=step_id,
        name=name,
        goal=f"The reference lifetime of the {dye_hint} in the detection channel it calibrates",
        instructions=(
            f"Measure {dye_hint} dilute in buffer (no FRET partner) and attach the "
            "microtime histogram. Set the tail window yourself -- the fit starts where "
            "YOU judge the IRF and the prompt to be over. The tail fit here is a "
            "first-order estimator: if you fitted the decay with a reconvolution model, "
            "enter YOUR fitted lifetime and it is the value that gets recorded."
        ),
        inputs=[
            _file("file", "Recording / histogram"),
            _num("micro_time_resolution_ns", "Micro time resolution", unit="ns"),
            _num("tail_start_ns", "Tail window start", unit="ns",
                 describe="where the tail fit starts (after the IRF; your call)"),
            _num("tail_stop_ns", "Tail window stop", unit="ns"),
            _num("lifetime_fit_ns", "Your fitted lifetime", unit="ns", required=False,
                 describe="a reconvolution-fit lifetime of yours; it overrides the tail estimate"),
            _txt("sample", "Sample", "dye, buffer, concentration"),
        ],
        metrics=[
            _metric(
                "tail_lifetime_ns", "Tail-fit lifetime", "ns",
                "counts-weighted log-linear single-exponential fit over the tail window "
                "(first-order; a reconvolution fit is the proper analysis)",
                lambda v: measurements.tail_lifetime_ns(
                    measurements.load_histogram(v.get("file", "")) if v.get("file") else None,
                    v.get("micro_time_resolution_ns"),
                    start_ns=v.get("tail_start_ns"), stop_ns=v.get("tail_stop_ns"),
                ),
            ),
        ],
        requires=("buffer_background",),
        skippable=True,
        guards=(
            _guard_metric_computable(
                "tail_lifetime_ns",
                "no lifetime measured: provide the histogram and tail window, "
                "or enter your fitted lifetime in 'lifetime_fit_ns'",
            ),
        ),
        result_builders=(_record_preferred(quantity, "ns", "lifetime_fit_ns", "tail_lifetime_ns"),),
    )


def _donor_only_crosstalk() -> workflow.StepSpec:
    def compute(values):
        i_dd, i_ad = values.get("i_dd"), values.get("i_ad_raw")
        if i_dd is None or i_ad is None:
            return None, "set 'i_dd' and 'i_ad_raw' first"
        if float(i_dd) <= 0:
            return None, "i_dd must be positive"
        return float(i_ad) / float(i_dd), "alpha = I_Aem|Dex / I_Dem|Dex of the donor-only sample"

    return workflow.StepSpec(
        id="donor_only_crosstalk", spec_id="donor_only_crosstalk",
        name="Donor-only crosstalk (alpha)",
        goal="The donor leakage into the acceptor channel, from a donor-only sample",
        instructions=(
            "Measure a DONOR-ONLY sample (e.g. the Alexa488 DNA strand alone, or free "
            "donor dye) under the PIE/ALEX conditions of the calibration. Enter the "
            "background-corrected mean counts: donor channel under donor excitation "
            "(i_dd) and acceptor channel under donor excitation (i_ad_raw). Per "
            "Hellenkamp et al. 2018 (eq. 12), alpha is their ratio."
        ),
        inputs=[
            _num("i_dd", "Donor channel under donor excitation", "counts",
                 describe="background-corrected mean of the donor-only sample"),
            _num("i_ad_raw", "Acceptor channel under donor excitation", "counts"),
            _txt("sample", "Sample", "what was measured"),
        ],
        metrics=[
            _metric("alpha", "Donor leakage alpha", "1",
                    "I_Aem|Dex / I_Dem|Dex of the donor-only population", compute),
        ],
        requires=("buffer_background",),
        result_builders=(_record_metric("alpha", "1"),),
    )


def _acceptor_only_direct() -> workflow.StepSpec:
    def compute(values):
        i_aa, i_ad = values.get("i_aa"), values.get("i_ad_raw")
        if i_aa is None or i_ad is None:
            return None, "set 'i_aa' and 'i_ad_raw' first"
        if float(i_aa) <= 0:
            return None, "i_aa must be positive"
        return float(i_ad) / float(i_aa), "delta = I_Aem|Dex / I_Aem|Aex of the acceptor-only sample"

    return workflow.StepSpec(
        id="acceptor_only_direct", spec_id="acceptor_only_direct",
        name="Acceptor-only direct excitation (delta)",
        goal="Direct acceptor excitation by the donor laser, from an acceptor-only sample",
        instructions=(
            "Measure an ACCEPTOR-ONLY sample (e.g. the Cy5/Alexa647 strand alone) under "
            "the same conditions. Enter the background-corrected mean counts: acceptor "
            "channel under acceptor excitation (i_aa) and acceptor channel under donor "
            "excitation (i_ad_raw). Per Hellenkamp et al. 2018 (eq. 13), delta is their "
            "ratio."
        ),
        inputs=[
            _num("i_aa", "Acceptor channel under acceptor excitation", "counts"),
            _num("i_ad_raw", "Acceptor channel under donor excitation", "counts"),
            _txt("sample", "Sample", "what was measured"),
        ],
        metrics=[
            _metric("delta", "Direct excitation delta", "1",
                    "I_Aem|Dex / I_Aem|Aex of the acceptor-only population", compute),
        ],
        requires=("buffer_background",),
        result_builders=(_record_metric("delta", "1"),),
    )


def _pie_metric(field_name: str):
    def compute(values):
        out, detail = measurements.pie_gamma(
            i_dd=values.get("i_dd"), i_ad_raw=values.get("i_ad_raw"), i_aa=values.get("i_aa"),
            alpha=values.get("alpha"), delta=values.get("delta"), beta=values.get("beta"),
        )
        if out is None:
            return None, detail
        return out[field_name], detail
    return compute


def _guard_stoichiometry(wf, step) -> str | None:
    if wf.state[step.id].values.get("stoichiometry_confirmed") is not True:
        return (
            "the gamma derivation assumes exactly one donor and one acceptor per "
            "molecule -- confirm the 1:1 labelling stoichiometry of the DNA sample"
        )
    return None


def _dna_pie_gamma() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="dna_pie_gamma", spec_id="dna_pie_gamma",
        name="DNA-PIE gamma",
        goal="The detection correction gamma, from one doubly-labelled DNA sample under PIE",
        instructions=(
            "Measure a doubly-labelled dsDNA with KNOWN 1:1 stoichiometry (one donor, one "
            "acceptor per molecule) under PIE. Enter the background-corrected mean counts "
            "of the doubly-labelled population: donor under donor excitation (i_dd), "
            "acceptor under donor excitation (i_ad_raw), acceptor under acceptor "
            "excitation (i_aa). Enter alpha and delta from the two crosstalk stages (the "
            "wizard offers the recorded values) and the excitation normalisation beta. "
            "The sample's stoichiometry is the load-bearing assumption -- confirm it; "
            "Müller et al. 2005 derived gamma = (F_AA - F_AD)/F_DD and E = F_AD/F_AA "
            "exactly for 1:1 labelling."
        ),
        inputs=[
            _num("i_dd", "Donor under donor excitation", "counts",
                 describe="background-corrected mean of the doubly-labelled population"),
            _num("i_ad_raw", "Acceptor under donor excitation (raw)", "counts"),
            _num("i_aa", "Acceptor under acceptor excitation (raw)", "counts"),
            _num("alpha", "Leakage alpha", "1", describe="from the donor-only stage"),
            _num("delta", "Direct excitation delta", "1", describe="from the acceptor-only stage"),
            _num("beta", "Excitation normalisation beta", "1",
                 describe="acceptor/donor excitation strength ratio under YOUR pulse scheme"),
            _flag("stoichiometry_confirmed", "1:1 stoichiometry confirmed",
                  "the sample carries exactly one donor and one acceptor per molecule"),
            _txt("sample", "Sample", "construct, sequences, labelling"),
        ],
        metrics=[
            _metric(
                "fret_efficiency_pie", "FRET efficiency (PIE ratio)", "1",
                "E = F_AD/F_AA: sensitized over directly excited acceptor emission -- "
                "the same detection channel, so detector sensitivity cancels",
                _pie_metric("fret_efficiency"),
            ),
            _metric(
                "gamma_pie", "gamma", "1",
                "gamma = (F_AA - F_AD)/F_DD per Müller et al. 2005, with alpha, delta and "
                "beta applied as in Hellenkamp et al. 2018",
                _pie_metric("gamma"),
            ),
        ],
        requires=("donor_only_crosstalk", "acceptor_only_direct"),
        reference=(
            "Müller et al., Biophys. J. 89, 3508 (2005), DOI 10.1529/biophysj.105.064766; "
            "Hellenkamp et al., Nat. Methods 15, 669 (2018), DOI 10.1038/s41592-018-0085-0"
        ),
        guards=(_guard_stoichiometry,),
        result_builders=(
            _record_metric("fret_efficiency_pie", "1"),
            _record_metric("gamma_pie", "1"),
        ),
    )


def _fret_summary() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="fret_summary", spec_id="fret_summary",
        name="Calibration summary (sign-off)",
        goal="The recorded calibrations, accepted as the working set",
        instructions=(
            "Review the summary of recorded calibrations (IRF width, background, "
            "reference lifetimes, alpha, delta, E and gamma). Adopting them is your "
            "explicit sign-off; the values stay measured results with their provenance "
            "and can be superseded by a later calibration run."
        ),
        inputs=[_txt("note", "Note", "what you adopt and why", required=False)],
        metrics=[],
        requires=("green_reference", "red_reference", "dna_pie_gamma"),
    )


def _polarization_reference() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="polarization_reference", spec_id="polarization_reference",
        name="Polarisation factor G (Rh110)",
        goal="The detection polarisation factor G, from a fast-rotating reference dye",
        instructions=(
            "Measure Rh110 dilute in water with the polarisation-resolved detection "
            "(VV and VH channels) and enter the background-corrected "
            "steady-state counts of the two channels. A fast-rotating dye has anisotropy "
            "r = 0, which fixes G = (I_VV/I_VH)(1-r)/(1+2r); if you know your "
            "reference's true anisotropy under your conditions, enter it instead of 0 -- "
            "the assumption is yours to make and is recorded with the result."
        ),
        inputs=[
            _num("i_par", "VV channel counts", "counts",
                 describe="background-corrected steady-state"),
            _num("i_perp", "VH channel counts", "counts"),
            _num("r_assumed", "Assumed true anisotropy", "1", required=False, default=0.0,
                 describe="0 for a fast-rotating reference; verify for YOUR dye and conditions"),
            _txt("sample", "Sample", "dye, solvent, temperature"),
        ],
        metrics=[
            _metric(
                "g_factor", "Polarisation factor G", "1",
                "(I_par/I_perp)(1-r)/(1+2r) at the assumed true anisotropy r",
                lambda v: measurements.g_factor(
                    i_par=v.get("i_par"), i_perp=v.get("i_perp"), r_assumed=v.get("r_assumed", 0.0)
                ),
            ),
            _metric(
                "apparent_anisotropy_raw", "Apparent anisotropy (G = 1)", "1",
                "the raw anisotropy without G correction -- shown to make the correction's "
                "effect transparent",
                lambda v: measurements.apparent_anisotropy(i_par=v.get("i_par"), i_perp=v.get("i_perp")),
            ),
        ],
        requires=("buffer_background",),
        guards=(
            _guard_metric_computable(
                "g_factor", "no G factor measured: enter the parallel and perpendicular counts"
            ),
        ),
        result_builders=(_record_metric("g_factor", "1"),),
    )


def _polarization_summary() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="polarization_summary", spec_id="polarization_summary",
        name="Calibration summary (sign-off)",
        goal="The recorded polarisation calibrations, accepted as the working set",
        instructions=(
            "Review the recorded G factor and its assumptions (reference dye, assumed "
            "anisotropy). Adopting them is your explicit sign-off."
        ),
        inputs=[_txt("note", "Note", "what you adopt and why", required=False)],
        metrics=[],
        requires=("polarization_reference",),
    )


# -- the power-diode workflow's stages -----------------------------------------------------------
#
# These stages DELEGATE to chisurf.plugins.core.acq.live.power_calibration: that
# module owns the reference points, the dark offset, the verified configuration
# and emission states, the 3-calendar-month expiry and the bounded conversion.
# The workflow stages only walk the user through capturing what that module
# demands, and record the finished PowerCalibration as a measured result.

_POWER_JSON = "JSON list, e.g. "


def _selected(wf) -> tuple[str, float]:
    """The wizard's selection: (laser name, wavelength nm)."""
    values = wf.state["laser_selection"].values if "laser_selection" in wf.state else {}
    name = str(values.get("laser_name", "") or f"{values.get('laser_nm', '?')} nm")
    nm = values.get("laser_nm")
    return name, (float(nm) if nm is not None else float("nan"))


def _emission_state(text):
    """The verified emission states from the step's JSON input, or ``None``."""
    import json as _json

    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        doc = _json.loads(raw)
    except ValueError:
        return None
    try:
        return power_calibration.EmissionState.from_dict(doc)
    except Exception:  # noqa: BLE001 - surfaced as a guard blocker, not a crash
        return None


def _config_identity(text):
    import json as _json

    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        doc = _json.loads(raw)
    except ValueError:
        return None
    try:
        return power_calibration.ConfigIdentity.from_dict(doc)
    except Exception:  # noqa: BLE001
        return None


def _draft_calibration(wf, *, with_points: bool):
    """The PowerCalibration as the workflow's values describe it so far."""
    name, nm = _selected(wf)
    cal = power_calibration.PowerCalibration(name, nm)
    verify = wf.state.get("verify_single_laser")
    setup = wf.state.get("verify_setup")
    dark = wf.state.get("dark_offset")
    emission = _emission_state(verify.values.get("emission_states")) if verify else None
    if setup:
        config = _config_identity(setup.values.get("config_heads"))
        if config is not None:
            cal.config = config
    if emission is not None and dark is not None:
        # the dark offset carries its OWN emission states: every laser verified OFF
        dark_emission = _emission_state(dark.values.get("emission_states"))
        if dark_emission is not None:
            cal.set_dark(power_calibration.DarkOffset(
                raw=float(dark.values.get("dark_raw", float("nan"))),
                emission=dark_emission,
            ))
    if with_points:
        points = wf.state["power_points"].values.get("points") or []
        measured = wf.state["power_points"].values.get("measured_on", "")
        meter = wf.state["objective_meter_setup"].values
        for row in points:
            cal.add_point(power_calibration.ReferencePoint(
                raw=float(row["diode_raw"]), uw=float(row["meter_uw"]),
                emission=emission or power_calibration.EmissionState(),
                meter=str(meter.get("meter", "") or ""),
                meter_calibrated=str(meter.get("meter_calibrated", "") or ""),
                measured=str(measured or ""),
                intensity_pct=float(row["drive"]),
            ))
        c = wf.state["power_points"].values
        cal.conditions = power_calibration.LaserConditions(
            name, nm,
            repetition_rate_hz=c.get("rep_rate_hz"),
            mode=str(c.get("mode", "") or "pulsed"),
            pattern=str(c.get("pattern", "") or ""),
            optical_path=str(c.get("optical_path", "") or ""),
        )
    return cal


def _guard_laser_installed(wf, step) -> str | None:
    values = wf.state["laser_selection"].values if "laser_selection" in wf.state else {}
    nm = values.get("laser_nm")
    if nm is None:
        return None  # the required-input blocker covers this
    if wf.inventory is None:
        return "no laser inventory attached -- verify installations before calibrating"
    if not wf.inventory.is_verified(nm):
        return (
            f"{int(nm)} nm is no longer verified installed -- the hardware configuration "
            "changed; abort and re-verify"
        )
    return None


def _guard_laser_selection(wf, step) -> str | None:
    nm = wf.state[step.id].values.get("laser_nm")
    if nm is None:
        return None  # the required-input blocker covers this
    if wf.inventory is None:
        return "no laser inventory attached -- verify installations before selecting"
    if not wf.inventory.is_verified(nm):
        return (
            f"{int(nm)} nm is not verified installed -- verify it from the hardware "
            "configuration and the inventory before selecting; never assume an inactive "
            "head is installed"
        )
    return None


def _guard_config_identity(wf, step) -> str | None:
    doc = wf.state[step.id].values.get("config_heads")
    config = _config_identity(doc)
    if config is None:
        return (
            "the configuration readback does not parse: expected "
            '{"heads": [{"name", "wavelength_nm", "serial"}]} for every connected head'
        )
    name, nm = _selected(wf)
    if not config.includes(name, nm):
        return (
            f"the verified configuration does not include {name} at {nm:g} nm -- "
            "the head to calibrate must be among the connected, read-back heads"
        )
    return None


def _guard_single_laser_state(wf, step) -> str | None:
    name, _nm = _selected(wf)
    emission = _emission_state(wf.state[step.id].values.get("emission_states"))
    if emission is None:
        return (
            "the emission states do not parse: expected a JSON list of "
            '{"laser", "on", "verified"} for every connected laser'
        )
    ok, why = emission.confirmed_single(name)
    if not ok:
        return f"the verified emission state does not show {name} alone: {why}"
    setup = wf.state.get("verify_setup")
    if setup is not None:
        config = _config_identity(setup.values.get("config_heads"))
        if config is not None:
            missing = config.missing_from(emission)
            if missing:
                return f"no verified readback for {', '.join(missing)}"
    return None


def _guard_dark_offset(wf, step) -> str | None:
    emission = _emission_state(wf.state[step.id].values.get("emission_states"))
    if emission is None:
        return (
            "the emission states do not parse: expected a JSON list of "
            '{"laser", "on", "verified"} for every connected laser'
        )
    ok, why = emission.all_off_confirmed()
    if not ok:
        return f"the dark offset needs every laser verified OFF: {why}"
    return None


def _guard_config_unchanged(wf, step) -> str | None:
    if "verify_single_laser" not in wf.state:
        return "the single-laser verification stage is not in this workflow"
    verified = wf.state["verify_single_laser"].values.get("emission_state_readback", "")
    captured = wf.state[step.id].values.get("config_readback", "")
    if not str(verified).strip():
        return "the verification stage has no emission-state readback recorded"
    if str(captured).strip() and str(captured).strip() != str(verified).strip():
        return (
            "the configuration changed since verification (the readback differs) -- "
            "abort: re-verify the single-laser state, then recapture"
        )
    return None


def _laser_selection() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="laser_selection", spec_id="laser_selection",
        name="Laser selection",
        goal="The laser to calibrate, chosen among the heads verified installed",
        instructions=(
            "Select a laser the HARDWARE CONFIGURATION shows installed and the inventory "
            "records as verified. Available models are 488, 530, 640 and 730 nm -- "
            "available does NOT mean installed: never assume an inactive head is "
            "installed, and never let the software auto-switch. To exchange a head: shut "
            "down per the instrument manual, disconnect and reconnect the cables BY "
            "HAND, then verify the new configuration from its readback and record the "
            "verification in the inventory before selecting it here."
        ),
        inputs=[
            _choice("laser_nm", "Laser wavelength (nm)", AVAILABLE_LASERS_NM,
                    describe="only lasers verified installed may be selected"),
            _txt("laser_name", "Head name", "the head's name in the hardware configuration",
                 required=False),
        ],
        metrics=[],
        requires=(),
        guards=(_guard_laser_selection,),
    )


def _verify_setup() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="verify_setup", spec_id="verify_setup",
        name="Verified configuration",
        goal="Which laser heads are connected, as the hardware readback shows",
        instructions=(
            "Read the hardware configuration and record every connected head: name, "
            "wavelength and serial number. The power calibration is bound to this "
            "verified configuration; a head swapped later invalidates it. Paste the "
            "readback as JSON " + _POWER_JSON
            + '{"heads": [{"name": "LDH-488", "wavelength_nm": 488.0, "serial": "1234"}]}.'
        ),
        inputs=[
            _txt("config_heads", "Connected heads (readback)", "JSON list of the heads"),
        ],
        metrics=[],
        requires=("laser_selection",),
        guards=(_guard_config_identity,),
    )


def _verify_single_laser() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="verify_single_laser", spec_id="verify_single_laser",
        name="Verified single-laser state",
        goal="Evidence that ONLY the selected laser emits while the diode is read",
        instructions=(
            "The power diode integrates ALL laser light, so the calibration is only "
            "valid with every OTHER laser OFF. Switch all other lasers off, record every "
            "laser's emission state as verified by readback (JSON "
            + _POWER_JSON + '[{"laser": "LDH-488", "on": true, "verified": true}, ...] -- '
            "an unverified or unknown state blocks the claim), paste the readback text, "
            "and confirm the switch-off. Isolation is NEVER inferred from the requested "
            "or intended state -- only the verified readback counts. The same readback "
            "must be pasted again at the measurement stage; if it changes there, the "
            "calibration aborts."
        ),
        inputs=[
            _flag("all_other_lasers_off_confirmed", "All other lasers switched OFF and verified",
                  "confirmed by the operator from the instrument readback"),
            _txt("emission_states", "Emission states (verified readback)",
                 "JSON list of every laser's on/off state"),
            _txt("emission_state_readback", "Emission-state readback",
                 "the captured readback of every laser's emission state"),
        ],
        metrics=[],
        requires=("verify_setup",),
        guards=(_guard_single_laser_state,),
    )


def _dark_offset() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="dark_offset", spec_id="dark_offset",
        name="Dark offset",
        goal="The diode's raw reading with the emission blocked -- the µW zero",
        instructions=(
            "Block the selected laser's emission and read the diode: this raw reading is "
            "the zero every reference is measured against. Record the emission states as "
            "verified by readback (JSON " + _POWER_JSON
            + '[{"laser": "LDH-488", "on": false, "verified": true}, ...]) -- every '
            "laser must read verified OFF, or the zero is not a zero."
        ),
        inputs=[
            _num("dark_raw", "Dark raw reading", unit="counts",
                 describe="the diode's raw reading with the emission blocked"),
            _txt("emission_states", "Emission states (verified readback)",
                 "JSON list of every laser's on/off state"),
        ],
        metrics=[],
        requires=("verify_single_laser",),
        guards=(_guard_dark_offset,),
    )


def _objective_meter_setup() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="objective_meter_setup", spec_id="objective_meter_setup",
        name="Objective power meter setup",
        goal="The external power meter in place, reading at the objective",
        instructions=(
            "Set up the EXTERNAL calibrated power meter so it reads at the objective "
            "(the plane the sample sees). Note the meter model, its position and its own "
            "calibration date. The wizard records the meter's measured values only -- it "
            "never estimates or extrapolates a power."
        ),
        inputs=[
            _flag("meter_setup_confirmed", "Meter set up at the objective"),
            _txt("meter", "Meter", "model and where it reads"),
            _txt("meter_calibrated", "Meter calibration date", "YYYY-MM-DD", required=False),
        ],
        metrics=[],
        requires=("laser_selection",),
    )


def _power_points() -> workflow.StepSpec:
    def fit_metric(field):
        def compute(values, wf):
            cal = _draft_calibration_for_metrics(wf, values)
            fit = cal.linear_fit() if cal is not None else None
            if fit is None:
                return None, (
                    "the linearity report needs the dark offset and reference points at "
                    "three or more raw readings"
                )
            detail = (
                f"through-origin line over the dark-corrected anchors: "
                f"{fit.n_points} anchors, max residual {fit.max_residual_uw:.4g} µW -- "
                "a linearity report, never the converter"
            )
            return float(getattr(fit, field)), detail
        return compute

    return workflow.StepSpec(
        id="power_points", spec_id="power_points",
        name="Power points (diode vs. meter)",
        goal="The multi-point diode-to-µW scale of the selected laser, entered from the meter",
        instructions=(
            "Vary the selected laser's drive with the drive slider over several points "
            "from low to high. AT EACH POINT: read the external power meter at the "
            "objective (µW) and the diode's raw reading at the same moment, and enter the "
            "triple (drive, meter_uw, diode_raw). All other lasers stay OFF and verified "
            "-- paste the emission-state readback again here; if it differs from the "
            "verification readback the calibration aborts. Capture measured values only: "
            "the wizard never sets a drive, never guesses a reading."
        ),
        inputs=[
            workflow.InputSpec(
                key="points", name="Measured points", kind="table",
                fields=("drive", "meter_uw", "diode_raw"),
                describe="rows of drive setting, meter µW at the objective, diode raw reading",
            ),
            _txt("measured_on", "Measured on", "YYYY-MM-DD of the captures"),
            _txt("config_readback", "Emission-state readback (at capture)",
                 "the same readback, pasted again at capture; a difference aborts"),
            _num("rep_rate_hz", "Repetition rate", unit="Hz",
                 describe="the laser rep rate the calibration is keyed to"),
            _choice("mode", "Pulse mode", ("cw", "pulsed")),
            _txt("pattern", "Pulse timing",
                 "e.g. the PIE pattern or pulse picker ratio"),
            _txt("optical_path", "Optical path",
                 "beam splitters and filters in the beam"),
        ],
        metrics=[
            _metric("n_anchors", "Measured anchors", "1",
                    "the measured anchors of the response curve: the dark zero and the "
                    "reference points",
                    fit_metric("n_points"), needs_workflow=True),
            _metric("slope_uw_per_raw", "Linearity slope", "µW/count",
                    "µW per raw count above dark -- how the response measures, reported "
                    "only (the conversion interpolates between measured points)",
                    fit_metric("slope"), needs_workflow=True),
            _metric("rms_residual_uw", "Residual RMS", "µW",
                    "RMS residual of the linearity report -- how straight the response measured",
                    fit_metric("rms_residual_uw"), needs_workflow=True),
            _metric("max_residual_uw", "Residual max", "µW",
                    "worst residual of the linearity report",
                    fit_metric("max_residual_uw"), needs_workflow=True),
        ],
        requires=("dark_offset", "objective_meter_setup"),
        guards=(_guard_config_unchanged, _guard_laser_installed),
    )


def _draft_calibration_for_metrics(wf, values):
    """A PowerCalibration from the metrics' point of view (the points being entered)."""
    name, nm = _selected(wf)
    if nm != nm:  # NaN: nothing selected yet
        return None
    cal = power_calibration.PowerCalibration(name, nm)
    dark_step = wf.state.get("dark_offset")
    if dark_step is not None:
        emission = _emission_state(dark_step.values.get("emission_states"))
        if emission is not None:
            cal.set_dark(power_calibration.DarkOffset(
                raw=float(dark_step.values.get("dark_raw", float("nan"))), emission=emission))
    for row in values.get("points") or []:
        cal.add_point(power_calibration.ReferencePoint(
            raw=float(row["diode_raw"]), uw=float(row["meter_uw"])))
    return cal


def _guard_calibration_complete(wf, step) -> str | None:
    cal = _draft_calibration(wf, with_points=True)
    if cal is None:
        return "no calibration to adopt"
    cal.calibrated = datetime.date.today().isoformat()  # what confirming would record
    problems = cal.validate()
    if problems:
        return "the calibration is not complete: " + "; ".join(problems)
    return None


def _power_calibration_builder(wf, step) -> list:
    cal = _draft_calibration(wf, with_points=True)
    if cal is None:
        return []
    cal.calibrated = datetime.date.today().isoformat()
    if cal.validate():
        return []  # the guard already names the problems; nothing is recorded
    fit = cal.linear_fit()
    doc = cal.to_dict()  # the companion module's own schema -- never mutated
    note = str(wf.state[step.id].values.get("note", "") or "")
    expires = cal.expires_on()
    return [
        _result(
            wf, step, quantity="power_calibration",
            value=float(fit.slope) if fit is not None else None,
            unit="µW/count", source="fitted",
            values={**wf.state["power_points"].values,
                    "sample": f"{cal.key.laser} at {cal.key.wavelength_nm:g} nm"},
            extra={
                "power_calibration": doc,  # round-trips through PowerCalibration.from_dict
                "operator_note": note,
                "expires_on": expires.isoformat() if expires is not None else "",
                "validations": cal.validate(),
                "warnings": cal.warnings(),
                "slope_uw_per_raw": float(fit.slope) if fit is not None else None,
                "residual_rms_uw": float(fit.rms_residual_uw) if fit is not None else None,
            },
        )
    ]


def _power_summary() -> workflow.StepSpec:
    return workflow.StepSpec(
        id="power_summary", spec_id="power_summary",
        name="Power calibration (sign-off)",
        goal="The keyed per-laser power scale, adopted as a measured calibration",
        instructions=(
            "Review the reference points, the linearity report and the validation of the "
            "calibration it will be bound to: the laser, the repetition rate, the pulse "
            "mode and timing, the optical path, the verified configuration and the "
            "verified single-laser emission states. Confirming adopts it as a MEASURED "
            "result in the companion power-calibration store: it expires 3 calendar "
            "months after today (policy) and converts only inside the measured range, "
            "under matching conditions and verified states. Device health (diffusion "
            "time, counts per molecule at this calibrated power) is tracked against "
            "YOUR reference bounds in the instrument reference history -- an "
            "out-of-bounds value there is a recommendation, never by itself hardware "
            "proof."
        ),
        inputs=[_txt("note", "Note", "what you adopt and why", required=False)],
        metrics=[],
        requires=("power_points",),
        guards=(_guard_calibration_complete, _guard_laser_installed),
        result_builders=(_power_calibration_builder,),
    )


# -- the catalog and the workflows ---------------------------------------------------------------

def optics_catalog() -> dict:
    """The editable dye / beam splitter catalog: named placeholders, NO numbers.

    The GUI lets the user fill excitation/emission wavelengths and splitter
    bands from their instrument's data sheets; shipping them prefilled would
    put someone else's numbers into someone else's calibration.
    """
    def dye(name, role):
        return {"name": name, "role": role, "excitation_nm": None,
                "emission_nm": None, "filter": "", "notes": ""}

    return {
        "lasers_nm": list(AVAILABLE_LASERS_NM),
        "dyes": [
            dye("Alexa488", "green label / FRET donor"),
            dye("Cy3", "yellow-orange label / FRET donor or middle channel"),
            dye("Cy5", "red label / FRET acceptor"),
            dye("Rh110", "green reference dye (lifetime / polarisation reference)"),
            dye("Alexa647", "red label / FRET acceptor / red reference dye"),
            dye("Atto655", "red reference dye (alternative)"),
        ],
        "beam_splitters": [
            {"name": "main dichroic (name yours)", "cutoff_nm": None, "bands": None, "notes": ""},
            {"name": "PIE / ALEX splitter (name yours)", "cutoff_nm": None, "bands": None, "notes": ""},
            {"name": "polarisation beamsplitter (name yours)", "cutoff_nm": None, "bands": None, "notes": ""},
        ],
    }


STEP_SPECS = {
    "instrument_setup": _instrument_setup,
    "water_irf": _water_irf,
    "buffer_background": _buffer_background,
    "green_reference": lambda: _reference_dye(
        "green_reference", "Green reference (Rh110)", "Rh110", "lifetime_green_ns"
    ),
    "red_reference": lambda: _reference_dye(
        "red_reference", "Red reference (Alexa647 / Atto655)", "Alexa647 or Atto655", "lifetime_red_ns"
    ),
    "donor_only_crosstalk": _donor_only_crosstalk,
    "acceptor_only_direct": _acceptor_only_direct,
    "dna_pie_gamma": _dna_pie_gamma,
    "fret_summary": _fret_summary,
    "polarization_reference": _polarization_reference,
    "polarization_summary": _polarization_summary,
    "laser_selection": _laser_selection,
    "verify_setup": _verify_setup,
    "verify_single_laser": _verify_single_laser,
    "dark_offset": _dark_offset,
    "objective_meter_setup": _objective_meter_setup,
    "power_points": _power_points,
    "power_summary": _power_summary,
}


def step_spec(spec_id: str) -> workflow.StepSpec:
    """A fresh, independent stage spec (the library never shares instances)."""
    try:
        factory = STEP_SPECS[spec_id]
    except KeyError:
        raise KeyError(f"no step spec {spec_id!r} in the calibration library") from None
    return factory()


WORKFLOW_LAYOUTS = {
    "fret": (
        "FRET calibration (PIE)",
        ["instrument_setup", "water_irf", "buffer_background", "green_reference",
         "red_reference", "donor_only_crosstalk", "acceptor_only_direct",
         "dna_pie_gamma", "fret_summary"],
    ),
    "polarization": (
        "Polarization calibration (MFD)",
        ["instrument_setup", "water_irf", "buffer_background", "polarization_reference",
         "polarization_summary"],
    ),
    "power_diode": (
        "Laser power (diode) calibration",
        ["laser_selection", "verify_setup", "verify_single_laser", "dark_offset",
         "objective_meter_setup", "power_points", "power_summary"],
    ),
}


def build_workflow(kind: str, inventory=None, name: str = "") -> workflow.CalibrationWorkflow:
    """One of the shipped workflows, as editable live objects."""
    try:
        default_name, step_ids = WORKFLOW_LAYOUTS[kind]
    except KeyError:
        raise ValueError(
            f"unknown workflow kind {kind!r}: one of {sorted(WORKFLOW_LAYOUTS)}"
        ) from None
    instrument_setup = _instrument_setup(polarization=(kind == "polarization"))
    steps = []
    for step_id in step_ids:
        spec = instrument_setup if step_id == "instrument_setup" else step_spec(step_id)
        steps.append(spec)
    return workflow.CalibrationWorkflow(kind, name or default_name, steps, inventory=inventory)

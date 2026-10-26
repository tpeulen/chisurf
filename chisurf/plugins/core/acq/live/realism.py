"""How real the simulated smFRET measurement looks: sample and instrument imperfections.

:class:`Realism` collects every imperfection the simulator adds to a measurement; :data:`REALISTIC`
is what a confocal smFRET measurement typically shows and the Record tool's default, :data:`IDEAL`
switches everything off (the clean stream the exact tests and teaching use).

Where each lives:

* **in tttrlib's SimEngine** (the molecule): donor-only and acceptor-only populations, aggregates,
  photobleaching of donor and acceptor and acceptor blinking (molecular states with
  excitation-driven ``k_rad`` and spontaneous ``k_nrad`` transitions), the detection efficiency
  ratio gamma, donor leakage alpha and direct acceptor excitation delta (the per-laser brightness
  rows), diffusion and the Gaussian focus, uncorrelated background;
* **at record level** (this plugin's simulator, because SimEngine has no such feature): the
  instrument response and timing jitter, per-state and per-channel lifetimes (a species carries one
  decay in SimEngine; here the donor, the FRET-quenched donor, the sensitised acceptor and the
  directly excited acceptor each have theirs), prompt-window scatter, detector afterpulsing and dead
  time, brightness heterogeneity between molecules, and slow intensity drift.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

__all__ = ["IDEAL", "PRESETS", "REALISTIC", "Realism"]


@dataclass(frozen=True)
class Realism:
    """Imperfections of a simulated measurement (units in the attribute comments).

    ``ideal`` keeps the simulator's clean path exactly (every other field is then ignored).
    """

    name: str = "realistic"
    ideal: bool = False
    # -- sample ---------------------------------------------------------------------------------
    donor_only_fraction: float = 0.2  # of all molecules: no (or no active) acceptor -> S ~ 1
    acceptor_only_fraction: float = 0.1  # of all molecules: no donor -> S ~ 0
    aggregate_fraction: float = 0.004  # of all molecules: bright, slow particles (spikes)
    aggregate_brightness: float = 8.0  # x a molecule's brightness
    brightness_cv: float = 0.25  # molecule-to-molecule brightness spread (coefficient of variation)
    diffusion_um2_per_s: float = 80.0  # a ~30 kDa protein
    focus_w0_um: float = 0.3  # lateral 1/e^2 radius of the Gaussian focus
    focus_z0_um: float = 1.5  # axial radius (V_eff ~ 0.75 fl)
    # -- photophysics (per ms at the focus centre) -----------------------------------------------
    acceptor_bleach_per_ms: float = 0.4
    donor_bleach_per_ms: float = 0.15
    acceptor_blink_per_ms: float = 1.0  # into a dark (triplet / cis) state
    acceptor_recover_per_ms: float = 5.0  # back from it (0.2 ms dark)
    # -- lifetimes (ns) --------------------------------------------------------------------------
    tau_donor_ns: float = 4.0  # donor without FRET; with FRET tau_D (1 - E)
    tau_acceptor_ns: float = 2.5
    # -- detection -------------------------------------------------------------------------------
    gamma: float = 0.8  # acceptor / donor detection efficiency x quantum yield
    beta: float = 1.0  # acceptor / donor excitation normalisation
    alpha: float = 0.07  # donor leakage into the acceptor channel
    delta: float = 0.05  # direct excitation of the acceptor by the donor laser (of F_AA)
    irf_fwhm_ns: float = 0.25
    irf_tail_fraction: float = 0.1  # of photons delayed by an exponential tail
    irf_tail_ns: float = 0.4
    jitter_donor_ns: float = 0.03
    jitter_acceptor_ns: float = 0.04
    background_donor_khz: float = 0.6  # uncorrelated (ambient, dark counts), flat in micro time
    background_acceptor_khz: float = 0.8
    scatter_donor_khz: float = 0.3  # scattered / Raman light of the donor laser, prompt window
    scatter_acceptor_khz: float = 0.1
    afterpulse_probability: float = 0.005  # per detected photon
    afterpulse_delay_us: float = 1.0  # mean delay of an afterpulse
    dead_time_ns: float = 50.0  # per detector channel
    # -- the measurement over time -----------------------------------------------------------------
    drift_per_minute: float = -0.03  # relative intensity change (focus, laser power, evaporation)

    def as_dict(self) -> dict:
        return asdict(self)

    def factors(self) -> dict:
        """The correction factors this instrument has (what a calibration would find)."""
        return {"gamma": self.gamma, "beta": self.beta, "alpha": self.alpha, "delta": self.delta}


REALISTIC = Realism()

#: Everything off: the simulator's clean stream.
IDEAL = replace(
    Realism(),
    name="ideal",
    ideal=True,
    donor_only_fraction=0.0,
    acceptor_only_fraction=0.0,
    aggregate_fraction=0.0,
    brightness_cv=0.0,
    acceptor_bleach_per_ms=0.0,
    donor_bleach_per_ms=0.0,
    acceptor_blink_per_ms=0.0,
    gamma=1.0,
    alpha=0.0,
    delta=0.0,
    irf_fwhm_ns=0.0,
    irf_tail_fraction=0.0,
    jitter_donor_ns=0.0,
    jitter_acceptor_ns=0.0,
    scatter_donor_khz=0.0,
    scatter_acceptor_khz=0.0,
    afterpulse_probability=0.0,
    dead_time_ns=0.0,
    drift_per_minute=0.0,
)

PRESETS = {"realistic": REALISTIC, "ideal": IDEAL}

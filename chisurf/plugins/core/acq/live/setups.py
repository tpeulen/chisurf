"""The experiment a live run analyses: the shared channel definition, its preset, the burst rule.

A measurement type is not a class here: it is the **Instrument setup** (the shared ChiSurf/CMC
channel definition: ``detectors``, ``windows``, ``tttr_reading``) read with one of the analyzer's
presets -- ``single_color``, ``two_color``, ``pie``, ``alex``, ``mfd``, ``three_color_pie``
(:data:`chisurf.plugins.core.acq.live.analyzer.PRESETS`). :func:`infer_preset` proposes the preset a
setup describes; the user may pick another.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .analyzer import PRESETS, make_analyzer

__all__ = [
    "BurstParameters",
    "Experiment",
    "PRESET_LABELS",
    "default_setup",
    "infer_preset",
    "unwrap",
]

#: What the Record tool calls each preset.
PRESET_LABELS = {
    "single_color": "Single colour",
    "two_color": "Two colour (no alternation)",
    "pie": "PIE (pulsed interleaved excitation)",
    "alex": "µs-ALEX (alternating excitation)",
    "mfd": "MFD (polarisation-resolved)",
    "three_color_pie": "Three-colour PIE",
}


@dataclass(frozen=True)
class BurstParameters:
    """The sliding-window burst rule: ``window_photons`` within ``window_time_s``, at least
    ``min_photons`` -- the three numbers burst selection's search takes."""

    min_photons: int = 30
    window_photons: int = 10
    window_time_s: float = 1e-3


def unwrap(setup: dict) -> dict:
    """The definition itself (a setup file may hold it under ``data``)."""
    return dict(setup.get("data", setup)) if isinstance(setup, dict) else {}


def infer_preset(setup: dict) -> str:
    """The preset a setup describes: polarisation pairs -> MFD, three colours with their own
    windows -> three-colour PIE, a prompt/delay pair -> PIE, two detectors -> two colour, else
    single colour. (µs-ALEX needs an alternation period, so it is never inferred.)"""
    s = unwrap(setup)
    det = list((s.get("detectors") or {}).keys())
    win = set((s.get("windows") or {}).keys())
    if any(d.endswith("_par") for d in det) and any(d.endswith("_perp") for d in det):
        return "mfd"
    if {"blue", "green", "red"} <= set(det) and {"blue", "green", "red"} <= win:
        return "three_color_pie"
    if {"prompt", "delayed"} <= win and len(det) >= 2:
        return "pie"
    if len(det) >= 2:
        return "two_color"
    return "single_color"


def default_setup(preset: str, n_micro: int) -> dict:
    """The simulator's (and a first measurement's) setup: routing channel 0 the donor (green)
    detector, 1 the acceptor (red); PIE splits the laser period into prompt and delay halves."""
    det = {"green": {"chs": [0]}, "red": {"chs": [1]}}
    if preset == "single_color":
        return {"detectors": {"green": {"chs": [0]}}}
    if preset == "pie":
        half = int(n_micro) // 2
        return {"detectors": det, "windows": {"prompt": [0, half], "delayed": [half, int(n_micro)]}}
    if preset in ("two_color", "alex"):
        return {"detectors": det}
    raise ValueError(f"no default setup for preset {preset!r}: pick an Instrument setup")


@dataclass
class Experiment:
    """A setup read with a preset, and the burst rule.

    Attributes
    ----------
    setup : dict
        The shared channel definition (``detectors``, ``windows``, ...).
    preset : str
        One of the analyzer presets.
    burst : BurstParameters
    name : str
        Where the setup came from, for display.
    alex_period_s : float or None
        The alternation period of a µs-ALEX measurement.
    """

    setup: dict
    preset: str
    burst: BurstParameters = field(default_factory=BurstParameters)
    name: str = ""
    alex_period_s: float | None = None
    donor: str = "green"
    acceptor: str = "red"
    prompt: str = "prompt"
    delay: str = "delayed"

    def __post_init__(self) -> None:
        self.setup = unwrap(self.setup)
        if self.preset not in PRESETS:
            raise ValueError(f"unknown preset {self.preset!r}; one of {PRESETS}")

    @property
    def alternating(self) -> bool:
        """The acceptor is excited directly (stoichiometry exists)."""
        return self.preset in ("pie", "alex", "three_color_pie")

    def factors(self) -> dict | None:
        """gamma, beta, alpha, delta when the setup carries all four, else ``None`` (raw E/S)."""
        corr = self.setup.get("corrections") or self.setup.get("fret") or self.setup
        keys = {"gamma": ("gamma",), "beta": ("beta",), "alpha": ("alpha", "crosstalk", "leakage"),
                "delta": ("delta", "direct", "direct_excitation")}  # fmt: skip
        out = {}
        for k, names in keys.items():
            for n in names:
                if isinstance(corr, dict) and corr.get(n) is not None:
                    out[k] = float(corr[n])
                    break
        return out if len(out) == 4 else None

    def channels(self, role: str) -> list[int]:
        det = (self.setup.get("detectors") or {}).get(
            self.donor if role == "donor" else self.acceptor
        ) or {}
        return [int(c) for c in det.get("chs", [])]

    def analyzer(self, macro_clock_s: float, micro_res_s: float, n_micro: int):
        """The live analyzer for this experiment (tttrlib's class, or the stand-in)."""
        b = self.burst
        return make_analyzer(
            self.setup,
            self.preset,
            min_photons=b.min_photons,
            window_photons=b.window_photons,
            window_time=b.window_time_s,
            macro_time_resolution=macro_clock_s,
            micro_time_resolution=micro_res_s,
            donor=self.donor,
            acceptor=self.acceptor,
            prompt=self.prompt,
            delay=self.delay,
            factors=self.factors() if self.preset in ("pie", "alex") else None,
            alex_period=self.alex_period_s,
            trace=(0.1, 600),
            decays=(min(int(n_micro), 1024), int(n_micro), False),
        )

    def describe(self) -> str:
        det = self.setup.get("detectors") or {}
        win = self.setup.get("windows") or {}
        parts = [", ".join(f"{n} {list(d.get('chs', []))}" for n, d in det.items())]
        if win:
            parts.append("; ".join(f"{n} {list(r)}" for n, r in win.items()))
        f = self.factors()
        if self.preset in ("pie", "alex"):
            parts.append(
                "corrected E/S (gamma {gamma}, beta {beta}, alpha {alpha}, delta {delta})".format(
                    **f
                )
                if f
                else "raw proximity ratio and stoichiometry"
            )
        return " — ".join(p for p in parts if p)

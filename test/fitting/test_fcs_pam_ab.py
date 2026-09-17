"""A/B verification of the PAM-derived FCS models ported into models.yaml.

The reference side ("A") transcribes each PAM model's MATLAB ``fit`` lambda from
PAM's ``Models/fcs/*.m`` (https://gitlab.com/PAM-PIE/PAM at 7319d15d) verbatim (keeping the explicit ``1e-12``/``1e-6`` SI
conversions and ``x`` in seconds). The ported side ("B") is the corresponding
``models.yaml`` equation evaluated through ChiSurf's real ``ParseModel`` scanner.
For each model we draw random in-range parameter sets and assert the two agree,
which validates the port (including the algebraic simplification of the
cancelling unit conversions) against PAM as the ground truth.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
import yaml

MODELS_YAML = (
    pathlib.Path(__file__).resolve().parents[2]
    / "chisurf"
    / "core"
    / "models"
    / "fcs"
    / "models.yaml"
)

_G = 1.0 / np.sqrt(8.0)  # gamma factor for a 3D-Gaussian volume


# --- Reference "A": verbatim transcriptions of PAM's MATLAB fit lambdas -------
def _fcs_d(x, N, D, w_r, w_z, tau_T, Trip, y_0):
    return (_G * (1 / N) * (1 + (Trip / (1 - Trip) * np.exp(-x / tau_T / 1e-6)))
            * (1 / (1 + 4 * (D * 1e-12) * x / (w_r * 1e-6) ** 2))
            * (1 / np.sqrt(1 + 4 * (D * 1e-12) * x / (w_z * 1e-6) ** 2)) + y_0)


def _fcs_d_2c(x, N_1, D_1, N_2, D_2, w_r, w_z, tau_T, Trip, y_0):
    return (y_0 + _G * 1 / (N_1 + N_2) ** 2 * (1 + (Trip / (1 - Trip) * np.exp(-x / tau_T / 1e-6)))
            * ((N_1 * (1 / (1 + 4 * (D_1 * 1e-12) * x / (w_r * 1e-6) ** 2))
                * (1 / np.sqrt(1 + 4 * (D_1 * 1e-12) * x / (w_z * 1e-6) ** 2)))
               + (N_2 * (1 / (1 + 4 * (D_2 * 1e-12) * x / (w_r * 1e-6) ** 2))
                  * (1 / np.sqrt(1 + 4 * (D_2 * 1e-12) * x / (w_z * 1e-6) ** 2)))))


def _fcs_d_2exp(x, N, D, w_r, w_z, tau_T, Trip, tau_T2, Trip_2, y_0):
    return (_G * (1 / N) * (1 + (Trip / (1 - Trip) * np.exp(-x / tau_T / 1e-6)))
            * (1 + (Trip_2 / (1 - Trip_2) * np.exp(-x / tau_T2 / 1e-6)))
            * (1 / (1 + 4 * (D * 1e-12) * x / (w_r * 1e-6) ** 2))
            * (1 / np.sqrt(1 + 4 * (D * 1e-12) * x / (w_z * 1e-6) ** 2)) + y_0)


def _fcs_taud(x, N, tau_D, p, tau_T, Trip, y_0):
    return (_G * 1 / N * (1 + (Trip / (1 - Trip)) * np.exp(-x / tau_T / 1e-6))
            * (1 / (1 + x / (tau_D * 1e-6)))
            * (1 / np.sqrt(1 + (1 / p ** 2) * x / (tau_D * 1e-6))) + y_0)


def _fcs_taud_anom(x, N, tau_D, p, alpha, tau_T, Trip, y_0):
    return (_G * 1 / N * (1 + (Trip / (1 - Trip)) * np.exp(-x / tau_T / 1e-6))
            * (1 / (1 + (x / (tau_D * 1e-6)) ** alpha))
            * (1 / np.sqrt(1 + (1 / p ** 2) * (x / (tau_D * 1e-6)) ** alpha)) + y_0)


def _fcs_flow(x, N, D, w_r, w_z, tau_T, Trip, y_0, v_flow):
    return (_G * (1 / N) * (1 + (Trip / (1 - Trip) * np.exp(-x / tau_T / 1e-6)))
            * (1 / (1 + 4 * (D * 1e-12) * x / (w_r * 1e-6) ** 2))
            * (1 / np.sqrt(1 + 4 * (D * 1e-12) * x / (w_z * 1e-6) ** 2))
            * np.exp(-((x * v_flow / w_r) ** 2) / (1 + 4 * (D * 1e-12) * x / (w_r * 1e-6) ** 2)) + y_0)


def _fcs_bg(x, Counts, BG, N, D, w_r, w_z, tau_T, Trip, y_0):
    return (_G * (1 / N) * (1 - BG / Counts) ** 2
            * (1 + (Trip / (1 - Trip) * np.exp(-x / tau_T / 1e-6)))
            * (1 / (1 + 4 * (D * 1e-12) * x / (w_r * 1e-6) ** 2))
            * (1 / np.sqrt(1 + 4 * (D * 1e-12) * x / (w_z * 1e-6) ** 2)) + y_0)


def _fcs_ap(x, N, D, w_r, w_z, tau_T, Trip, A_ap, tau_ap, stretch, y_0):
    return (_G * (1 / N) * (1 + (Trip / (1 - Trip) * np.exp(-x / tau_T / 1e-6)))
            * (1 / (1 + 4 * (D * 1e-12) * x / (w_r * 1e-6) ** 2))
            * (1 / np.sqrt(1 + 4 * (D * 1e-12) * x / (w_z * 1e-6) ** 2))
            + A_ap * np.exp(-(x / tau_ap / 1e-6) ** stretch) + y_0)


def _fcs_bleach(x, N, tau_D, p, tau_B, AB, y_0):
    return (_G * 1 / N * (1 - AB + AB * np.exp(-x / tau_B / 1e-6))
            * (1 / (1 + x / (tau_D * 1e-6)))
            * (1 / np.sqrt(1 + (1 / p ** 2) * x / (tau_D * 1e-6))) + y_0)


def _fcs_2focus(x, N, D, w_r, w_z, tau_T, Trip, diam, y_0):
    return (_G * 1 / N * (1 + (Trip / (1 - Trip) * np.exp(-x / tau_T / 1e-6)))
            * (1 / (1 + 4 * (D * 1e-12) * x / (w_r * 1e-6) ** 2))
            * (1 / np.sqrt(1 + 4 * (D * 1e-12) * x / (w_z * 1e-6) ** 2))
            * np.exp(-diam ** 2 / (w_r ** 2 + 4 * D * x)) + y_0)


def _fret_fccs(x, N_1, N_2, N_3, a, k_12, k_21, E_1, E_2, D, w_r, w_z, b, c, y_0):
    diff = ((1 / (1 + 4 * (D * 1e-12) * x / (w_r * 1e-6) ** 2))
            * (1 / np.sqrt(1 + 4 * (D * 1e-12) * x / (w_z * 1e-6) ** 2)))
    ex = np.exp(-(k_12 + k_21) * x)
    t1 = a * (_G * (1 / N_1)
              * (1 + (k_12 * k_21 * (E_1 - E_2) ** 2 / (k_21 * (1 - E_1) + k_12 * (1 - E_2)) ** 2) * ex) * diff)
    t2 = b * (_G * (1 / N_2)
              * (1 + (k_12 * k_21 * (E_1 - E_2) ** 2 / (k_21 * E_1 + k_12 * E_2) ** 2) * ex) * diff)
    t3 = c * (_G * (1 / N_3)
              * (1 - (k_12 * k_21 * (E_1 - E_2) ** 2
                      / ((k_21 * (1 - E_1) + k_12 * (1 - E_2)) * (k_21 * E_1 + k_12 * E_2))) * ex) * diff)
    return t1 + t2 + t3 + y_0


def _nsfcs(x, N, t_0, A_ab, t_ab, A_cd, t_cd, A_T, t_T, offset):
    return (offset + (1 / N) * (1 - A_ab * np.exp(-np.abs(x - t_0) / t_ab))
            * (1 + A_cd * np.exp(-np.abs(x - t_0) / t_cd))
            * (1 + A_T * np.exp(-np.abs(x - t_0) / t_T)))


def _fcs_scan(x, N, D, w_r, w_z, tau_T, Trip, diam, freq, y_0):
    return (_G * 1 / N * (1 + (Trip / (1 - Trip) * np.exp(-x / tau_T / 1e-6)))
            * (1 / (1 + 4 * (D * 1e-12) * x / (w_r * 1e-6) ** 2))
            * (1 / np.sqrt(1 + 4 * (D * 1e-12) * x / (w_z * 1e-6) ** 2))
            * np.exp(-diam ** 2 * np.sin(np.pi * freq * 10 ** 3 * x) ** 2 / (w_r ** 2 + 4 * D * x)) + y_0)


def _fcs_taud_bg(x, Counts, BG, N, tau_D, p, tau_T, Trip, y_0):
    return (_G * 1 / N * (1 - BG / Counts) ** 2
            * (1 + (Trip / (1 - Trip)) * np.exp(-x / tau_T / 1e-6))
            * (1 / (1 + x / (tau_D * 1e-6)))
            * (1 / np.sqrt(1 + (1 / p ** 2) * x / (tau_D * 1e-6))) + y_0)


def _sccf1(x, N, tau_D, p, alpha, tau_T, A, y_0, isCCF):
    return (_G * 1 / N * (1 + (1 - 2 * isCCF) * A * np.exp(-x / tau_T / 1e-6))
            * (1 / (1 + (x / (tau_D * 1e-6)) ** alpha))
            * (1 / np.sqrt(1 + (1 / p ** 2) * (x / (tau_D * 1e-6)) ** alpha)) + y_0)


def _sccf2(x, N, tau_D, p, alpha, tau_1, A_1, tau_2, A_2, y_0, isCCF):
    return (_G * 1 / N * (1 + (1 - 2 * isCCF) * A_1 * np.exp(-x / tau_1 / 1e-6)
                          + (1 - 2 * isCCF) * A_2 * np.exp(-x / tau_2 / 1e-6))
            * (1 / (1 + (x / (tau_D * 1e-6)) ** alpha))
            * (1 / np.sqrt(1 + (1 / p ** 2) * (x / (tau_D * 1e-6)) ** alpha)) + y_0)


def _sccf3(x, N, tau_D, p, alpha, tau_1, A_1, tau_2, A_2, tau_3, A_3, y_0, isCCF):
    return (_G * 1 / N * (1 + (1 - 2 * isCCF) * A_1 * np.exp(-x / tau_1 / 1e-6)
                          + (1 - 2 * isCCF) * A_2 * np.exp(-x / tau_2 / 1e-6)
                          + (1 - 2 * isCCF) * A_3 * np.exp(-x / tau_3 / 1e-6))
            * (1 / (1 + (x / (tau_D * 1e-6)) ** alpha))
            * (1 / np.sqrt(1 + (1 / p ** 2) * (x / (tau_D * 1e-6)) ** alpha)) + y_0)


def _full_sum(x, N, tau_D, p, tau_AB, A_ab, tau_1, A_1, tau_2, A_2, tau_T, T, y_0):
    return (_G * 1 / N * (1 - A_ab * np.exp(-x / tau_AB / 1e-9))
            * (1 + A_1 * np.exp(-x / tau_1 / 1e-9) + A_2 * np.exp(-x / tau_2 / 1e-9))
            * (1 + T * np.exp(-x / tau_T / 1e-9))
            * (1 / (1 + x / (tau_D * 1e-6)))
            * (1 / np.sqrt(1 + (1 / p ** 2) * x / (tau_D * 1e-6))) + y_0)


def _full_prod(x, N, tau_D, p, tau_AB, A_ab, tau_1, A_1, tau_2, A_2, tau_3, A_3, y_0):
    return (_G * 1 / N * (1 - A_ab * np.exp(-x / tau_AB / 1e-9))
            * (1 + A_1 * np.exp(-x / tau_1 / 1e-9))
            * (1 + A_2 * np.exp(-x / tau_2 / 1e-9))
            * (1 + A_3 * np.exp(-x / tau_3 / 1e-9))
            * (1 / (1 + x / (tau_D * 1e-6)))
            * (1 / np.sqrt(1 + (1 / p ** 2) * x / (tau_D * 1e-6))) + y_0)


# --- map: models.yaml entry name -> (reference fn, {param: (low, high)}) ------
CASES = {
    "3D diffusion (D, triplet)": (
        _fcs_d, dict(N=(0.2, 5), D=(10, 800), w_r=(0.1, 0.4), w_z=(0.5, 2),
                     tau_T=(0.5, 5), Trip=(0.01, 0.5), y_0=(-0.05, 0.05))),
    "3D diffusion, 2 components (D, triplet)": (
        _fcs_d_2c, dict(N_1=(0.2, 5), D_1=(50, 800), N_2=(0.2, 5), D_2=(1, 50),
                        w_r=(0.1, 0.4), w_z=(0.5, 2), tau_T=(0.5, 5), Trip=(0.01, 0.5), y_0=(-0.05, 0.05))),
    "3D diffusion, 2 triplet (D)": (
        _fcs_d_2exp, dict(N=(0.2, 5), D=(10, 800), w_r=(0.1, 0.4), w_z=(0.5, 2),
                          tau_T=(0.5, 5), Trip=(0.01, 0.4), tau_T2=(1, 20), Trip_2=(0.01, 0.4), y_0=(-0.05, 0.05))),
    "3D diffusion (tauD, triplet)": (
        _fcs_taud, dict(N=(0.2, 5), tau_D=(5, 200), p=(2, 10), tau_T=(0.5, 5),
                        Trip=(0.01, 0.5), y_0=(-0.05, 0.05))),
    "3D anomalous diffusion (tauD, triplet)": (
        _fcs_taud_anom, dict(N=(0.2, 5), tau_D=(5, 200), p=(2, 10), alpha=(0.6, 1.4),
                             tau_T=(0.5, 5), Trip=(0.01, 0.5), y_0=(-0.05, 0.05))),
    "3D diffusion + flow (D, triplet)": (
        _fcs_flow, dict(N=(0.2, 5), D=(10, 800), w_r=(0.1, 0.4), w_z=(0.5, 2),
                        tau_T=(0.5, 5), Trip=(0.01, 0.5), y_0=(-0.05, 0.05), v_flow=(1, 500))),
    "3D diffusion + background (D, triplet)": (
        _fcs_bg, dict(Counts=(50, 200), BG=(0, 40), N=(0.2, 5), D=(10, 800), w_r=(0.1, 0.4),
                      w_z=(0.5, 2), tau_T=(0.5, 5), Trip=(0.01, 0.5), y_0=(-0.05, 0.05))),
    "3D diffusion + afterpulsing (D, triplet)": (
        _fcs_ap, dict(N=(0.2, 5), D=(10, 800), w_r=(0.1, 0.4), w_z=(0.5, 2), tau_T=(0.5, 5),
                      Trip=(0.01, 0.5), A_ap=(0, 0.5), tau_ap=(0.05, 1), stretch=(0.6, 1.4), y_0=(-0.05, 0.05))),
    "3D diffusion + bleaching (tauD)": (
        _fcs_bleach, dict(N=(0.2, 5), tau_D=(5, 200), p=(2, 10), tau_B=(0.5, 10),
                          AB=(0.01, 0.5), y_0=(-0.05, 0.05))),
    "Two-focus 3D diffusion (D, triplet)": (
        _fcs_2focus, dict(N=(0.2, 5), D=(10, 800), w_r=(0.1, 0.4), w_z=(0.5, 2), tau_T=(0.5, 5),
                          Trip=(0.01, 0.5), diam=(0.2, 1.5), y_0=(-0.05, 0.05))),
    "FRET-FCCS, 2-state (D)": (
        _fret_fccs, dict(N_1=(0.5, 5), N_2=(0.5, 5), N_3=(0.5, 5), a=(0.2, 2), k_12=(100, 5000),
                         k_21=(100, 5000), E_1=(0.1, 0.45), E_2=(0.55, 0.9), D=(10, 200),
                         w_r=(0.1, 0.4), w_z=(0.5, 2), b=(0.2, 2), c=(0.2, 2), y_0=(-0.05, 0.05))),
    "ns-FCS antibunching + bunching + triplet": (
        _nsfcs, dict(N=(0.5, 5), t_0=(-0.05, 0.05), A_ab=(0.1, 0.9), t_ab=(0.05, 2),
                     A_cd=(0.05, 1), t_cd=(5, 200), A_T=(0, 0.5), t_T=(100, 2000), offset=(0.8, 1.2))),
    "Scanning FCS (D, triplet)": (
        _fcs_scan, dict(N=(0.2, 5), D=(10, 800), w_r=(0.1, 0.4), w_z=(0.5, 2), tau_T=(0.5, 5),
                        Trip=(0.01, 0.5), diam=(0.2, 1.5), freq=(0.5, 5), y_0=(-0.05, 0.05))),
    "3D diffusion + background (tauD, triplet)": (
        _fcs_taud_bg, dict(Counts=(50, 200), BG=(0, 40), N=(0.2, 5), tau_D=(5, 200), p=(2, 10),
                           tau_T=(0.5, 5), Trip=(0.01, 0.5), y_0=(-0.05, 0.05))),
    "SCCF anomalous diffusion, 1 relaxation": (
        _sccf1, dict(N=(0.005, 0.5), tau_D=(500, 5000), p=(2, 10), alpha=(0.6, 1.4),
                     tau_T=(0.5, 5), A=(0.05, 1.5), y_0=(-0.05, 0.05), isCCF=(0, 1))),
    "SCCF anomalous diffusion, 2 relaxation": (
        _sccf2, dict(N=(0.005, 0.5), tau_D=(500, 5000), p=(2, 10), alpha=(0.6, 1.4),
                     tau_1=(0.5, 5), A_1=(0.05, 1.5), tau_2=(5, 50), A_2=(0.05, 1.5),
                     y_0=(-0.05, 0.05), isCCF=(0, 1))),
    "SCCF anomalous diffusion, 3 relaxation": (
        _sccf3, dict(N=(0.005, 0.5), tau_D=(500, 5000), p=(2, 10), alpha=(0.6, 1.4),
                     tau_1=(0.5, 5), A_1=(0.05, 1.5), tau_2=(50, 200), A_2=(0.05, 1.5),
                     tau_3=(200, 800), A_3=(0.0, 0.5), y_0=(-0.05, 0.05), isCCF=(0, 1))),
    "Full FCS (antibunching + 2 summed bunching + triplet)": (
        _full_sum, dict(N=(0.2, 5), tau_D=(20, 200), p=(2, 10), tau_AB=(0.5, 5), A_ab=(0.1, 0.9),
                        tau_1=(20, 200), A_1=(0.01, 0.5), tau_2=(50, 400), A_2=(0.05, 1.5),
                        tau_T=(50, 500), T=(0.05, 1.5), y_0=(-0.05, 0.05))),
    "Full FCS (antibunching + 3 product bunching)": (
        _full_prod, dict(N=(0.2, 5), tau_D=(20, 200), p=(2, 10), tau_AB=(0.5, 5), A_ab=(0.1, 0.9),
                         tau_1=(20, 200), A_1=(0.01, 0.5), tau_2=(50, 400), A_2=(0.05, 1.5),
                         tau_3=(50, 400), A_3=(0.05, 1.5), y_0=(-0.05, 0.05))),
}

# PAM's own default ModelParameter values ("examples from PAM") for the batch-2
# models, used as concrete A/B assertion points in addition to random draws.
PAM_DEFAULTS = {
    "3D diffusion + background (tauD, triplet)":
        dict(Counts=100, BG=0, N=1, tau_D=30, p=5, tau_T=1, Trip=0.0, y_0=0),
    "SCCF anomalous diffusion, 1 relaxation":
        dict(N=0.01, tau_D=2500, p=5, alpha=1, tau_T=1, A=1, y_0=0, isCCF=0),
    "SCCF anomalous diffusion, 2 relaxation":
        dict(N=0.01, tau_D=2500, p=5, alpha=1, tau_1=1, A_1=1, tau_2=1, A_2=1, y_0=0, isCCF=0),
    "SCCF anomalous diffusion, 3 relaxation":
        dict(N=0.01, tau_D=2500, p=5, alpha=1, tau_1=1, A_1=1, tau_2=100, A_2=1,
             tau_3=500, A_3=0, y_0=0, isCCF=0),
    "Full FCS (antibunching + 2 summed bunching + triplet)":
        dict(N=1, tau_D=60, p=5, tau_AB=1, A_ab=1, tau_1=100, A_1=0.1, tau_2=200, A_2=1,
             tau_T=200, T=1, y_0=0),
    "Full FCS (antibunching + 3 product bunching)":
        dict(N=1, tau_D=60, p=5, tau_AB=1, A_ab=1, tau_1=100, A_1=0.1, tau_2=200, A_2=1,
             tau_3=200, A_3=1, y_0=0),
}


@pytest.fixture(scope="module")
def models():
    with open(MODELS_YAML) as handle:
        return yaml.safe_load(handle)


def _parse_and_eval(equation, values, x):
    """Evaluate a models.yaml equation via the real ParseModel scanner."""
    from numpy import abs, exp, sin, sqrt  # noqa: F401 — referenced in eval scope

    from chisurf.core.models.parse.parse import ParseModel

    m = ParseModel.__new__(ParseModel)
    m._func = equation
    m._keys = []
    m._count = 0
    m._parameters_equation = []
    m.find_parameters = lambda: None
    m.parse_code()
    a = [values[k] for k in m._keys]  # noqa: F841 — referenced by eval(code)
    return eval(m.code)


def test_all_pam_models_present(models):
    """Every ported PAM model exists in the catalogue."""
    for name in CASES:
        assert name in models, name


def test_every_catalogue_equation_parses(models):
    """Every models.yaml equation tokenises through the scanner without leftovers."""
    x = np.array([1e-6, 1e-3, 1.0])
    for name, entry in models.items():
        equation = entry["equation"]
        if isinstance(equation, str):
            equation = equation.strip()
        values = {k: float(v) for k, v in entry.get("initial", {}).items()}
        # A parse failure raises inside parse_code (unrecognised token -> rubbish).
        try:
            _parse_and_eval(equation, values, x)
        except Exception as exc:  # noqa: BLE001 — surface the offending model
            raise AssertionError(f"model {name!r} failed to parse/evaluate: {exc}") from exc


@pytest.mark.parametrize("name", list(CASES))
def test_pam_model_ab_matches_reference(models, name):
    """The models.yaml equation matches PAM's exact fit lambda over random params."""
    ref_fn, ranges = CASES[name]
    entry = models[name]
    # The equation's free parameters must exactly match the reference signature.
    assert set(entry["initial"]) == set(ranges), name

    x = np.logspace(-7, 0, 250)  # lag times in seconds
    rng = np.random.default_rng(12345)
    for _ in range(8):
        params = {k: float(rng.uniform(lo, hi)) for k, (lo, hi) in ranges.items()}
        a = ref_fn(x=x, **params)  # A: PAM reference
        b = _parse_and_eval(entry["equation"], params, x)  # B: ChiSurf port
        assert np.all(np.isfinite(a)), (name, "reference non-finite")
        assert np.all(np.isfinite(b)), (name, "port non-finite")
        assert np.allclose(a, b, rtol=1e-6, atol=1e-12), name


@pytest.mark.parametrize("name", list(PAM_DEFAULTS))
def test_pam_model_ab_at_pam_defaults(models, name):
    """The port matches PAM at PAM's own default parameters (the "examples from PAM")."""
    ref_fn, _ = CASES[name]
    entry = models[name]
    x = np.logspace(-8, 0, 250)  # lag times in seconds (ns antibunching -> s diffusion)
    base = PAM_DEFAULTS[name]
    # For SCCF models exercise both the auto (isCCF=0) and cross (isCCF=1) sign.
    variants = [base]
    if "isCCF" in base:
        variants.append(dict(base, isCCF=1))
    for params in variants:
        a = ref_fn(x=x, **params)
        b = _parse_and_eval(entry["equation"], params, x)
        assert np.all(np.isfinite(a)) and np.all(np.isfinite(b)), name
        assert np.allclose(a, b, rtol=1e-6, atol=1e-12), (name, params.get("isCCF"))

"""Shipped settings outside ``gui``: no key the application no longer reads.

The ``gui`` section has its own guard (``test_gui_settings_shipped.py``). A
user's settings file may still carry these keys (it is merged over the
defaults, never rewritten); the shipped YAML must not advertise them, nor
``docs/reference/settings.md`` document them.
"""

from __future__ import annotations

import pathlib
import re

import yaml

#: Top-level keys of ``settings_chisurf.yaml`` nothing reads (the retired Qt
#: shell's exception hook, detector-wizard warning, fit dialogs, macro echo).
RETIRED_TOP_LEVEL_KEYS = (
    "exceptions_on_gui",
    "warn_missing_detector_setups",
    "fitting_message",
    "hidden_execute",
)

#: Whole sections nothing reads.
RETIRED_SECTIONS = ("fcs", "fortune", "fps", "parameter", "photons", "tcspc_csv")

#: Keys of sections that stay, nothing reads.
RETIRED_KEYS = {
    "correlator": ("weighting",),
    "fret": (
        "bin_lifetime",
        "discriminate",
        "discriminate_amplitude",
        "lifetime_bins",
        "orientation_mode",
    ),
    "mc_settings": (
        "append_new_structures",
        "av_filename",
        "av_number_protein_mc",
        "cluster_structures",
        "do_av_steepest_descent",
        "ktAv",
        "number_of_moving_aa",
        "update_rmsd",
        "potentials",  # replaced by [] unless a run brings its own
    ),
    "optimization.leastsq": ("full_output",),
    "plugins": ("icons_enabled",),
    "tcspc": (
        "autoscale",
        "convolution_on_by_default",
        "default_convolution_mode",
        "is_vv_vh",
        "n0",
        "polarization",
        "polarization_options",
        "rebin",
        "shift_bg_with_irf",
        "ts",
    ),
}

#: Reader-entry keys of ``experiment_configs.yaml`` that named Qt widgets.
RETIRED_READER_KEYS = ("controller_class", "controller_params", "settings_key")

_SETTINGS = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "core" / "settings"
_PAGE = pathlib.Path(__file__).resolve().parents[2] / "docs" / "reference" / "settings.md"


def _shipped() -> dict:
    return yaml.safe_load((_SETTINGS / "settings_chisurf.yaml").read_text(encoding="utf-8"))


def _section(data: dict, dotted: str) -> dict:
    for part in dotted.split("."):
        data = data.get(part) or {}
    return data


def _subsections(text: str) -> dict[str, str]:
    """Map the backticked name of each ``###`` heading to the text below it."""
    parts = re.split(r"^### ", text, flags=re.M)[1:]
    out = {}
    for part in parts:
        heading, _, body = part.partition("\n")
        match = re.search(r"`([^`]+)`", heading)
        out[match.group(1) if match else heading.strip()] = body.split("\n## ")[0]
    return out


def test_shipped_settings_carry_no_retired_key():
    data = _shipped()
    assert not set(RETIRED_TOP_LEVEL_KEYS) & set(data)
    assert not set(RETIRED_SECTIONS) & set(data)
    for dotted, keys in RETIRED_KEYS.items():
        assert not set(keys) & set(_section(data, dotted)), dotted
    # What the readers still need is there.
    assert data["tcspc"]["dt"] == 1 and data["fret"]["forster_radius"] == 52


def test_shipped_experiment_configs_name_no_qt_controller():
    config = yaml.safe_load((_SETTINGS / "experiment_configs.yaml").read_text(encoding="utf-8"))
    for name, section in config.items():
        if not isinstance(section, dict):
            continue
        for reader in section.get("readers", []) or []:
            assert not set(RETIRED_READER_KEYS) & set(reader), (name, reader)
            assert reader.get("reader_class")


def test_settings_reference_documents_no_retired_key():
    if not _PAGE.is_file():
        return
    text = _PAGE.read_text(encoding="utf-8")
    sections = _subsections(text)
    for key in RETIRED_TOP_LEVEL_KEYS:
        assert f"`{key}`" not in text, key
    for name in RETIRED_SECTIONS:
        assert name not in sections, name
        assert f"`{name}." not in text, name
    for dotted, keys in RETIRED_KEYS.items():
        top = dotted.split(".")[0]
        body = sections.get(top, "")
        for key in keys:
            assert f"`{dotted}.{key}`" not in text, (dotted, key)
            assert f"**`{key}`**" not in body, (dotted, key)
    for key in RETIRED_READER_KEYS:
        assert f"**`{key}`**" not in text, key

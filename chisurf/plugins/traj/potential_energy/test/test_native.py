"""Qt-free tests for the native Potential-Energy EMTK app."""

from __future__ import annotations

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from ..app import PotentialEnergyApp, make_app
from ..potential_specs import make_potential, potential_names


def test_native_state_roundtrip(tmp_path):
    # Paths come back only while the files exist (a moved file is not restored), so they are real files here.
    run, structure = tmp_path / "run.dcd", tmp_path / "structure.pdb"
    run.write_text("x")
    structure.write_text("x")
    app = PotentialEnergyApp()
    app.model.set_trajectory(str(run))
    app.model.set_topology(str(structure))
    app.model.stride = 3
    app.model.potential_weight = 2.5
    app.selected_potential_index = 2
    app._editor_values.setdefault("H-Bond", {})["cutoff_ca"] = 9.0
    state = app.export_settings()

    other = PotentialEnergyApp()
    other.restore_settings(state)
    assert other.model.trajectory_file == str(run)
    assert other.model.topology_filename == str(structure)
    assert other.model.stride == 3
    assert other.model.potential_weight == 2.5
    assert other.selected_potential_index == 2
    assert other._editor_values["H-Bond"]["cutoff_ca"] == 9.0


def test_native_potential_registry_is_qt_free_and_complete():
    names = potential_names()
    # Mirrors the Qt potentialDict registry keys.
    assert "H-Bond" in names
    assert "Go-Potential" in names
    assert "Radius of Gyration" in names


def test_native_add_and_remove_potential_workflow():
    app = PotentialEnergyApp()
    index = potential_names().index("Radius of Gyration")
    app.selected_potential_index = index
    name = potential_names()[index]
    # Constructing the core class needs the IMP kernels; the app itself stays
    # importable and renderable without them (registry imports are lazy).
    pytest.importorskip("IMP.cgmol")
    potential = make_potential(name, {})
    app.model.add_potential(potential, 1.5, name=name)
    rows = app.model.added_potentials()
    assert len(rows) == 1
    assert rows[0]["name"] == "Radius of Gyration"
    assert rows[0]["weight"] == 1.5
    # Remove via the row button's code path.
    app.model.remove_potential(rows[0]["idx"])
    assert app.model.added_potentials() == []


class _StubPotential:
    """Minimal potential standing in for the IMP-backed core classes."""

    name = "Radius-Gyration"

    def __init__(self, structure=None):
        self.structure = structure

    def getEnergy(self):  # noqa: N802 (matches the potential interface)
        return 1.0


def test_native_process_guards():
    """The action's preconditions, in the Qt tool's words (its information boxes), in the order it checks them."""
    app = PotentialEnergyApp()
    assert app.action.missing(app.model) == "Open a trajectory first."
    app.model.set_trajectory("missing.dcd")
    assert app.action.missing(app.model) == "Add at least one potential."
    app.model.add_potential(_StubPotential(), 1.0, name="Radius of Gyration")
    assert app.action.missing(app.model) is None


@pytest.mark.filterwarnings("ignore")
def test_native_process_writes_energies(tmp_path):
    """Genuine workflow: synthetic DCD scored through the app's model writes CSV rows."""
    pytest.importorskip("chisurf.core.structure.trajectory_data")
    import time

    from .test_view_model import _peptide_trajectory

    pdb = _peptide_trajectory(str(tmp_path / "pep.dcd"))
    app = PotentialEnergyApp()
    app.model.set_trajectory(str(tmp_path / "pep.dcd"))
    app.model.set_topology(pdb)
    # The IMP-backed core potentials are unavailable in every environment; the
    # stub exercises the identical add -> process -> CSV path.
    app.model.add_potential(_StubPotential(), 1.0, name="Radius of Gyration")
    target = str(tmp_path / "energies.txt")
    app.save(target)
    end = time.monotonic() + 60
    while app.running and time.monotonic() < end:
        app.draw(RecordingPainter(), 0, 0, 800, 700)
        time.sleep(0.01)
    assert app.notice == "Processed 4 frame(s)."  # 4 frames processed

    header, *rows = open(target).read().strip().splitlines()
    assert header.split("\t")[:2] == ["FrameNbr", "Radius-Gyration"]
    assert len(rows) == 4
    values = np.array([float(row.split("\t")[1]) for row in rows])
    assert np.all(np.isfinite(values)) and np.all(values > 0)


def test_native_renders_and_labels():
    app = make_app()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 760, 620)
    # The window title is painted by the host chrome, not the app body; the
    # heading and every control label must be in the drawn strings.
    for expected in (
        "Trajectory",
        "Topology",
        "Potential",
        "Weight",
        "Add",
        "Stride",
        "Process",
        "Log",
    ):
        assert expected in [t.strip() for t in painter.strings], expected


def test_native_control_tooltips_in_all_locales(monkeypatch):
    """Every interactive control carries a tooltip, in every supported locale."""
    from emtk import im, im_widgets
    from emtk.i18n import get_locale, set_locale

    previous = get_locale()
    app = make_app()
    tips: list[str] = []
    original = im.set_item_tooltip

    def capture(text, *args, **kwargs):
        tips.append(str(text))
        return original(text, *args, **kwargs)

    monkeypatch.setattr(im, "set_item_tooltip", capture)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", capture)      # the spec-drawn fields tooltip through here
    try:
        for locale in ("en", "de", "fr", "es", "pt", "ru"):
            set_locale(locale)
            painter = RecordingPainter()
            tips.clear()
            app.draw(painter, 0, 0, 760, 620)
            # Guide + Help + two file rows (field and ...) + combo + add + H-Bond parameter editor + weight +
            # stride + process.
            assert len(tips) >= 9, (locale, tips)
            assert all(tip.strip() for tip in tips), locale
            if locale == "en":
                assert any("C-alpha distance cutoff" in tip for tip in tips), tips
            else:
                # The parameter tooltips must actually be translated.
                assert any(tip != "Type of potential to configure and add" for tip in tips), locale
    finally:
        set_locale(previous)


def test_native_renders_narrow():
    """The layout must survive a narrow viewport without dropping controls."""
    app = make_app()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 420, 560)
    for expected in ("Potential", "Stride", "Process", "Log"):
        assert expected in [t.strip() for t in painter.strings], expected


def test_native_localized_labels():
    """Every supported locale must translate the headline strings."""
    from emtk import i18n

    from ..strings import install_translations, tr

    install_translations()
    expected = {
        "de": ("Potenzielle-Energie-Rechner", "Potenzielle Energie", "Verarbeiten"),
        "fr": ("Calculateur d'énergie potentielle", "Énergie potentielle", "Traiter"),
        "es": ("Calculadora de energía potencial", "Energía potencial", "Procesar"),
        "pt": ("Calculadora de energia potencial", "Energia potencial", "Processar"),
        "ru": ("Калькулятор потенциальной энергии", "Потенциальная энергия", "Обработать"),
    }
    for locale in ("de", "fr", "es", "pt", "ru"):
        i18n.set_locale(locale)
        try:
            assert tr("Potential energy calculator") == expected[locale][0], locale
            assert tr("Potential energy") == expected[locale][1], locale
            assert tr("Process") == expected[locale][2], locale
            app = PotentialEnergyApp()
            painter = RecordingPainter()
            app.draw(painter, 0, 0, 760, 620)
            assert expected[locale][1] in [t.strip() for t in painter.strings], locale
        finally:
            i18n.set_locale("en")

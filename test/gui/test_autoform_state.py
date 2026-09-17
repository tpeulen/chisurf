"""Every AutoForm is restorable from JSON.

A form is generated from a view spec that names, per control, the model
attribute it binds to — which is already a complete description of where the
form's state lives. Reading it back and putting it back therefore needs no
per-plugin code, and belongs to the framework rather than to whichever plugin
author thought of it.

The reason it matters: a tool whose settings cannot be written down is a tool
whose results cannot be reproduced. An analysis folder can hold the numbers that
came out while having no record of what was asked for.
"""

from __future__ import annotations

import json

import pytest
from qtpy import QtWidgets

from chisurf.core import dataspec as vs
from chisurf.gui.autoform import state as af_state
from chisurf.gui.autoform.auto_form import AutoForm


@pytest.fixture(scope="module")
def qt_app():
    """A single QApplication for the module (offscreen)."""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class Settings:
    """A nested group, the way real view models hold their parameters."""

    def __init__(self):
        self.threshold = 5
        self.window = 0.5
        self.method = "sliding"
        self.use_filter = True


class Model:
    """A minimal view model: some scalars, one nested group, one action."""

    def __init__(self):
        self.name = "run A"
        self.settings = Settings()
        self.actions = []

    def view_spec(self):
        """The controls, including a nested panel and an action-bound button."""
        return vs.ModelView(
            sections=(
                vs.ValueSection(label="Name", kind="str", attr="name"),
                vs.PanelSection(
                    title="Search",
                    sections=(
                        vs.ValueSection(
                            label="Threshold", kind="int", target="settings", attr="threshold"
                        ),
                        vs.ValueSection(
                            label="Window", kind="float", target="settings", attr="window"
                        ),
                        vs.ChoiceSection(
                            label="Method",
                            target="settings",
                            attr="method",
                            options=("sliding", "cusum"),
                        ),
                        vs.ToggleSection(label="Filter", target="settings", attr="use_filter"),
                    ),
                ),
                # A command, not a setting: replaying it on load would re-run it.
                vs.ValueSection(label="Go", kind="str", set_action="run_analysis"),
            )
        )


@pytest.fixture
def form(qt_app):
    """A built form over the model above."""
    widget = AutoForm(Model())
    yield widget
    widget.close()


def test_state_captures_every_bound_control_including_nested(form):
    """Panels are not a second class of state; their fields count too."""
    state = form.state()
    assert state == {
        "name": "run A",
        "settings.threshold": 5,
        "settings.window": 0.5,
        "settings.method": "sliding",
        "settings.use_filter": True,
    }


def test_action_bound_controls_are_not_state(form):
    """A button is a command. Restoring one would re-run the analysis."""
    assert not any("run_analysis" in k for k in form.state())
    assert all(not k.endswith(".Go") for k in form.state())


def test_a_round_trip_restores_the_model(form):
    """The property the whole thing exists for."""
    original = form.state()

    form.model.name = "changed"
    form.model.settings.threshold = 99
    form.model.settings.method = "cusum"
    form.model.settings.use_filter = False

    result = form.apply_state(original)

    assert result.ok, (result.unknown, result.failed)
    assert form.model.name == "run A"
    assert form.model.settings.threshold == 5
    assert form.model.settings.method == "sliding"
    assert form.model.settings.use_filter is True


def test_a_file_round_trip(form, tmp_path):
    """Saved to JSON and restored, which is how it will actually be used."""
    form.model.settings.threshold = 42
    path = form.save_state(tmp_path / "settings.json", title="burst search")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format"] == "chisurf-autoform-state"
    assert payload["title"] == "burst search"
    assert payload["state"]["settings.threshold"] == 42

    form.model.settings.threshold = 1
    result = form.load_state(path)
    assert result.ok
    assert form.model.settings.threshold == 42


def test_a_bare_mapping_is_accepted(form, tmp_path):
    """So a state embedded in an analysis manifest can be handed straight in."""
    path = tmp_path / "bare.json"
    path.write_text(json.dumps({"settings.threshold": 7}), encoding="utf-8")

    assert form.load_state(path).applied == ["settings.threshold"]
    assert form.model.settings.threshold == 7


def test_an_older_file_restores_what_it_still_shares(form):
    """Leniency is what makes saved settings worth keeping.

    A file naming a field this version dropped must restore the rest rather than
    failing whole — and must say what it could not do.
    """
    result = form.apply_state(
        {
            "settings.threshold": 11,
            "settings.a_field_that_no_longer_exists": 3,
        }
    )

    assert form.model.settings.threshold == 11
    assert result.applied == ["settings.threshold"]
    assert result.unknown == ["settings.a_field_that_no_longer_exists"]
    assert not result.ok
    assert "1 unknown" in result.summary()


def test_a_rejected_value_does_not_abandon_the_rest(form):
    """One bad field must not cost every other setting in the file."""

    class Strict(Settings):
        @property
        def method(self):
            return self._method

        @method.setter
        def method(self, value):
            if value not in ("sliding", "cusum"):
                raise ValueError(f"unknown method {value!r}")
            self._method = value

    strict = Strict()
    strict._method = "sliding"
    form.model.settings = strict

    result = form.apply_state(
        {
            "settings.threshold": 3,
            "settings.method": "nonsense",
            "settings.window": 0.25,
        }
    )

    assert form.model.settings.threshold == 3
    assert form.model.settings.window == 0.25
    assert "settings.method" in result.failed
    assert "unknown method" in result.failed["settings.method"]


def test_unreadable_files_report_rather_than_raise(form, tmp_path):
    """A corrupt settings file must not take the tool down with it."""
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    result = form.load_state(path)
    assert not result.ok
    assert "<file>" in result.failed

    assert not form.load_state(tmp_path / "absent.json").ok


def test_numpy_values_survive_being_written(form):
    """Model values are routinely numpy; a settings file must still be writable."""
    np = pytest.importorskip("numpy")
    form.model.settings.threshold = np.int64(8)
    form.model.settings.window = np.float64(0.75)

    state = form.state()
    json.dumps(state)  # must not raise
    assert state["settings.threshold"] == 8
    assert state["settings.window"] == 0.75


def test_it_works_on_shipped_view_specs(qt_app):
    """Against the real ``.view.json`` files, not only the fixture above.

    Loads every shipped spec that declares attribute-bound controls and checks
    the collector recognises them. A spec built entirely from ``custom``
    sections legitimately has no declarative state — those are skipped rather
    than counted as failures, because their widgets own their own values.
    """
    import pathlib

    from chisurf.core.dataspec import load_view_spec

    root = pathlib.Path(af_state.__file__).parents[2]
    specs = sorted(root.rglob("*.view.json"))
    if not specs:
        pytest.skip("no view specs found")

    with_bindings = 0
    for path in specs:
        try:
            spec = load_view_spec(path)
        except Exception:
            continue
        keys = [af_state._key(s) for s in af_state.iter_bound_sections(spec.sections)]
        if keys:
            with_bindings += 1
            assert all(keys), f"{path.name} produced an empty key"
            assert len(keys) == len(set(keys)), (
                f"{path.name} binds the same attribute twice; a restore would be ambiguous"
            )

    assert with_bindings >= 5, (
        f"only {with_bindings} shipped specs had bindings — the collector is "
        "probably not recognising them"
    )

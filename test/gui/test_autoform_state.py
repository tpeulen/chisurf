"""Every AutoForm is restorable from JSON (``chisurf.core.dataspec.form_state``).

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

from chisurf.core import dataspec as vs
from chisurf.core.dataspec import form_state as af_state


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


class _Form:
    """The headless handle ``form_state`` accepts: the model is its own form (no widgets)."""

    def __init__(self, model):
        self.model = model

    def state(self):
        return af_state.collect_state(self.model)

    def apply_state(self, state):
        return af_state.apply_state(self.model, state)

    def save_state(self, path, **extra):
        return af_state.save_state(self.model, path, **extra)

    def load_state(self, path):
        return af_state.load_state(self.model, path)


@pytest.fixture
def form():
    """A headless form over the model above."""
    return _Form(Model())


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


def test_it_works_on_shipped_view_specs():
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
            # Conditional editors (e.g. masked/plain API key) may share one
            # binding. Persistence keys address the value, not the widget.

    assert with_bindings >= 5, (
        f"only {with_bindings} shipped specs had bindings — the collector is "
        "probably not recognising them"
    )


def test_native_window_round_trip_keeps_geometry_and_docks(monkeypatch, tmp_path):
    """Host coordinates and dock state are part of the same restorable snapshot."""
    from types import SimpleNamespace

    from emtk.docking import DockManager

    from chisurf.emtk import state

    monkeypatch.setattr(
        state, "_path", lambda plugin_id, kind: tmp_path / f"{plugin_id}.{kind}.json"
    )
    closed, moved, resized = [], [], []
    docks = DockManager()
    docks.set_extra("analysis", {"threshold": 7})
    app = SimpleNamespace(
        native_layouts={"main": docks},
        window_size=(640, 480),
        close=lambda: closed.append(True),
        window_moved=lambda x, y: moved.append((x, y)),
        window_resized=lambda w, h: resized.append((w, h)),
    )
    state.attach_native_state("window-test", app)
    app.window_screen_changed((0, 0, 1600, 1000))
    app.window_moved(125, 175)
    app.window_resized(900, 650)
    app.close()
    app.close()
    payload = json.loads((tmp_path / "window-test.window.json").read_text())
    assert payload["size"] == [900, 650]
    assert payload["pos"] == [125, 175]
    assert payload["docks"]["main"] == docks.state()
    assert closed == [True] and moved == [(125, 175)] and resized == [(900, 650)]

    restored = SimpleNamespace(native_layouts={"main": DockManager()})
    state.attach_native_state("window-test", restored)
    restored.window_screen_changed((0, 0, 1600, 1000))
    assert restored.window_size == (900, 650)
    assert restored.window_pos == (125, 175)
    assert restored.native_layouts["main"].extras["analysis"] == {"threshold": 7}
    restored.close()


@pytest.mark.parametrize("pos", [[99999, 2], [-1, 50], [50, float("nan")], [True, 40], "bad"])
def test_native_restore_rejects_invalid_or_offscreen_positions(monkeypatch, tmp_path, pos):
    """A stale saved monitor position must not put a reopened tool out of reach."""
    from types import SimpleNamespace

    from chisurf.emtk import state

    monkeypatch.setattr(
        state, "_path", lambda plugin_id, kind: tmp_path / f"{plugin_id}.{kind}.json"
    )
    (tmp_path / "bad-pos.window.json").write_text(json.dumps({"size": [600, 400], "pos": pos}))
    app = state.attach_native_state("bad-pos", SimpleNamespace())
    app.window_screen_changed((0, 0, 800, 600))
    assert app.window_pos is None
    assert app.window_size == (600, 400)
    app.close()
    assert json.loads((tmp_path / "bad-pos.window.json").read_text())["pos"] is None


def test_native_restore_accepts_old_size_only_window_state(monkeypatch, tmp_path):
    """Preferences written before position support still reopen normally."""
    from types import SimpleNamespace

    from chisurf.emtk import state

    monkeypatch.setattr(
        state, "_path", lambda plugin_id, kind: tmp_path / f"{plugin_id}.{kind}.json"
    )
    (tmp_path / "legacy.window.json").write_text(json.dumps({"size": [600, 400]}))
    app = state.attach_native_state("legacy", SimpleNamespace())
    assert app.window_size == (600, 400)
    assert app.window_pos is None
    app.close()


def test_conditional_editors_share_one_persisted_value():
    """Two representations of a value serialize and restore it just once."""
    from types import SimpleNamespace

    spec = vs.ModelView(
        sections=(
            vs.ValueSection(label="Masked", kind="str", attr="name"),
            vs.ValueSection(label="Plain", kind="str", attr="name"),
        )
    )
    model = Model()
    model.view_spec = lambda: spec
    form = SimpleNamespace(model=model, spec=spec)
    assert af_state.collect_state(form) == {"name": "run A"}
    result = af_state.apply_state(form, {"name": "run B"}, sync=False)
    assert result.applied == ["name"]
    assert model.name == "run B"

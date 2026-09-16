"""chimol builds its UI from ChiSurf ``view.json``, like every other tool.

The point
---------
ChiSurf tools declare their interface as data and AutoForm builds Qt widgets
from it. Chimol has no Qt -- its chrome is painted into the viewport so the
desktop app and the browser run one code path -- so the same file is read here
and drawn with the chrome's own controls.

That is an **adapter**, not a second renderer: the spec becomes
:class:`~emtk.widgets.settings_editor.Setting` rows over the editor that
already existed for the display settings. Stating it that way is what keeps the
two from drifting into two form systems.

What is pinned here
-------------------
* a spec's fields become rows **with their labels, ranges, steps and
  descriptions** -- a row that loses its range is a slider with a guessed track,
  and one that loses its description is a control nobody can identify;
* the rows **read and write the real model**, including through
  ``SettingsProxy``, which is what makes the panel do something rather than
  display something;
* sections the painted chrome cannot draw are **reported, not dropped**. A form
  quietly missing half its controls is indistinguishable from a tool that has
  none, and that is the failure mode of every "best effort" spec reader;
* a **real shipped ChiSurf spec** (not one written for the test) is read, so
  the adapter is exercised against the dialect as it is actually written.
"""
from __future__ import annotations

import pathlib

import pytest

from emtk.widgets.settings_editor import BOOL, CHOICE, FLOAT, INT, TEXT
from emtk.widgets.view_spec import (
    load_view_spec,
    model_from_view_spec,
    settings_from_view_spec,
    unsupported_sections,
)

#: chimol's own spec: the appearance settings, bound through ``SettingsProxy``.
APPEARANCE = (
    pathlib.Path(__import__("chimol").__file__).resolve().parent / "ui" / "data" / "appearance.view.json"
)

#: A spec shipped by ChiSurf itself, written with no thought for chimol. Read
#: so the adapter is tested against the dialect as it is really written rather
#: than against an example composed to suit it.
FOREIGN = (
    pathlib.Path(__file__).resolve().parents[4]
    / "chisurf" / "core" / "models" / "parameter_transform" / "parameter_transform.view.json"
)


class _Model:
    """A stand-in tool model: the attributes a spec would edit."""

    def __init__(self):
        self.model_name = "diffusion"
        self.func = "a*exp(-x/t)"
        self.function = "def f(a):\n    return a"
        self.description = "an equation"
        self.count = 3
        self.enabled = True
        self.weight = 0.5

    def catalogue_names(self):
        return ["diffusion", "triplet", "flow"]


def test_the_shipped_appearance_spec_reads():
    """The premise: chimol ships a spec, and it is a spec."""
    spec = load_view_spec(APPEARANCE)
    assert spec.get("title")
    assert spec.get("sections")


def test_every_field_becomes_a_row_with_what_it_declared():
    """Label, kind, range, step and description all survive the crossing."""
    from chimol.ui.panels.form import model_for

    spec = load_view_spec(APPEARANCE)
    rows = {row.key: row for row in settings_from_view_spec(spec, model_for(spec, None))}

    assert "cartoon_loop_radius" in rows
    radius = rows["cartoon_loop_radius"]
    assert radius.kind == FLOAT
    assert radius.label == "Loop radius"
    assert (radius.v_min, radius.v_max) == (0.05, 1.0)
    assert radius.step == pytest.approx(0.05)
    assert "tube" in radius.description.lower()
    assert radius.group == "Cartoon"

    assert rows["cartoon_flat_sheets"].kind == BOOL
    assert rows["antialias"].kind == INT
    assert rows["ambient"].group == "Lighting"


def test_a_panel_title_becomes_the_group():
    """Otherwise every control lands in one undifferentiated list."""
    from chimol.ui.panels.form import model_for

    spec = load_view_spec(APPEARANCE)
    model = model_from_view_spec(spec, model_for(spec, None))
    assert set(model.groups()) == {"Cartoon", "Surface", "Lighting"}


def test_the_rows_write_through_to_the_settings():
    """A panel that displays without editing is a picture."""
    from chimol.ui.panels.form import SettingsProxy
    from chimol.core.settings import registry as settings_api

    before = settings_api.get_setting("cartoon_loop_radius")
    try:
        seen = []
        proxy = SettingsProxy(lambda key, value: seen.append((key, value)))
        spec = load_view_spec(APPEARANCE)
        model = model_from_view_spec(spec, proxy)

        model.setter("cartoon_loop_radius", 0.42)
        assert settings_api.get_setting("cartoon_loop_radius") == pytest.approx(0.42)
        assert model.getter("cartoon_loop_radius") == pytest.approx(0.42)
        assert seen and seen[-1][0] == "cartoon_loop_radius"
    finally:
        settings_api.set_setting("cartoon_loop_radius", before)


def test_the_proxy_refuses_a_name_that_is_not_a_setting():
    """A typo in a spec must not create a setting that goes nowhere."""
    from chimol.ui.panels.form import SettingsProxy

    proxy = SettingsProxy()
    with pytest.raises(AttributeError):
        proxy.cartoon_loop_radiuss = 1.0
    with pytest.raises(AttributeError):
        _ = proxy.not_a_setting


def test_a_foreign_chisurf_spec_is_read():
    """A spec written with no thought for chimol still produces controls."""
    if not FOREIGN.exists():
        pytest.skip(f"{FOREIGN.name} is not in this tree")
    spec = load_view_spec(FOREIGN)
    model = _Model()
    rows = {row.key: row for row in settings_from_view_spec(spec, model)}

    assert "model_name" in rows, "the choice section produced no row"
    assert rows["model_name"].kind == CHOICE
    # `options_source` names a *method* on the model, which is the whole reason
    # the indirection exists -- the catalogue is not known until the model is.
    assert list(rows["model_name"].options) == ["diffusion", "triplet", "flow"]
    assert rows["function"].kind == TEXT


def test_what_cannot_be_drawn_is_reported():
    """Reported, never dropped in silence.

    The parse spec asks for an ``info`` block and a ``parameter_group_table``.
    Neither has a painted equivalent, and a form that showed the rest without
    saying so would look complete.
    """
    if not FOREIGN.exists():
        pytest.skip(f"{FOREIGN.name} is not in this tree")
    missing = unsupported_sections(load_view_spec(FOREIGN), _Model())
    assert missing, "a spec with a table and an info block reported nothing missing"
    assert any("parameter_group_table" in line for line in missing)


def test_a_spec_naming_an_attribute_the_model_lacks_is_reported():
    """Spec drift is the common failure, and it is silent."""
    spec = {"sections": [{"type": "float", "attr": "not_there", "label": "Nope"}]}
    model = _Model()
    assert settings_from_view_spec(spec, model) == []
    assert any("not_there" in line for line in unsupported_sections(spec, model))


def test_a_field_with_no_declared_kind_is_read_from_the_value():
    """`{"attr": "x"}` is common and perfectly clear once the model is in hand."""
    model = _Model()
    spec = {"sections": [
        {"attr": "enabled"}, {"attr": "count"}, {"attr": "weight"}, {"attr": "func"},
    ]}
    kinds = {row.key: row.kind for row in settings_from_view_spec(spec, model)}
    assert kinds == {
        "enabled": BOOL, "count": INT, "weight": FLOAT, "func": TEXT,
    }


def test_the_form_command_opens_a_window():
    """End to end, through the real command layer and a real frame."""
    from toolkit_free import probe

    measured = probe(f'''
        app = open_app(size=(1000, 700))
        errors = []
        app.cmd.set_error_callback(errors.append)
        messages = []
        app.cmd.set_message_callback(messages.append)

        app.cmd.do("form {APPEARANCE.as_posix()}")
        emit("errors", "; ".join(errors) or "none")
        emit("said", messages[-1] if messages else "nothing")

        gui = app.renderer._internal_gui
        window = None
        for win in gui.windows:
            if str(win.key).startswith("form:"):
                window = win
        emit("window", "yes" if window is not None else "no")
        emit("title", "" if window is None else str(window.title))
        emit("visible", "yes" if (window is not None and window.visible) else "no")

        # It has to survive a paint: a panel that raises during draw takes the
        # whole frame with it, and the window would still be listed.
        app.renderer.draw_frame()
        emit("painted", "yes")

        panel = next(v for k, v in app.viewer.gui.panels.items() if k.startswith("form:"))
        emit("rows", len(panel.model.settings))
        emit("missing", "; ".join(panel.missing) or "none")
    ''')

    assert measured["errors"] == "none"
    assert measured["window"] == "yes"
    assert measured["visible"] == "yes"
    assert measured["title"] == "Appearance"
    assert measured["painted"] == "yes"
    assert int(measured["rows"]) >= 10
    assert measured["missing"] == "none", (
        f"chimol's own spec has sections it cannot draw: {measured['missing']}"
    )


def test_a_missing_spec_is_an_error_not_an_empty_form():
    """An empty form looks like a tool with no settings."""
    with pytest.raises(FileNotFoundError):
        load_view_spec("/definitely/not/here.view.json")

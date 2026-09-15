"""Offscreen-Qt tests for the AutoModelWidget renderer.

These verify that the lifetime model -- a view on BFF's ``tcspc_lifetime`` --
renders into a real editor by composition, that picking a topology rebuilds
the parameter rows, and that custom/registered sections appear. Qt runs in
offscreen mode so the tests stay headless.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app


@pytest.fixture
def lifetime_model():
    try:
        import chisurf.core.fitting.fit as fit_mod
        from chisurf.core.data import DataCurve
        from chisurf.core.models.description import tcspc_lifetime as LifetimeModel
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"lifetime model import failed: {exc}")
    x = np.linspace(0, 25, 256)
    data = DataCurve(x=x, y=np.ones_like(x))
    fit = fit_mod.Fit(model_class=LifetimeModel, data=data)
    assert fit.model.problem is not None, fit.model.missing   # the IRF is modelled until one is loaded
    return fit.model


def _rows(widget):
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget
    return len(widget.parameter_widgets) + sum(
        t.table_model.rowCount() for t in widget.findChildren(ParameterGroupTableWidget))


def test_auto_model_widget_renders_sections(qapp, lifetime_model):
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    w = AutoModelWidget(lifetime_model)
    # one top-level widget per section in the view-spec
    spec = lifetime_model.view_spec()
    # count includes one trailing stretch item added by rebuild()
    assert w._layout.count() == len(spec.sections) + 1
    # parameter rows were created for the resolvable groups
    assert _rows(w) > 0

def test_picking_a_topology_rebuilds_the_rows(qapp, lifetime_model):
    """A component count is a structure: choosing another shows its rows."""
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    w = AutoModelWidget(lifetime_model)
    before = _rows(w)
    lifetime_model.structure = "lifetime.components.2"
    w.rebuild()
    assert _rows(w) == before + 2


def test_custom_section_registered(qapp):
    from chisurf.gui.autoform.sections.registry import get_section_factory
    assert get_section_factory("lifetime_amplitude_options") is not None


def test_plot_keys_resolve(qapp):
    from chisurf.gui.autoform.sections.registry import get_plot_class
    for key in ("line", "residual", "fit_info", "distribution"):
        assert get_plot_class(key) is not None, f"plot key {key} unresolved"


def test_build_model_editor_pure_model_makes_auto_widget(qapp, lifetime_model):
    """The live seam builds an AutoModelWidget for a pure (Qt-free) model."""
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    editor = build_model_editor(lifetime_model)
    assert isinstance(editor, AutoModelWidget)
    assert editor.model is lifetime_model


def test_model_plot_specs_resolve_from_view_spec(qapp, lifetime_model):
    """Plots for the subwindow come from the data-driven view spec."""
    from chisurf.gui.widgets.models.model_editor import model_plot_specs

    specs = model_plot_specs(lifetime_model)
    assert specs, "expected resolved plot specs from view_spec"
    # each entry is (plot_class, options_dict)
    for cls, opts in specs:
        assert isinstance(cls, type)
        assert isinstance(opts, dict)
    # distribution accessor string was resolved to a callable
    dist = [opts for _cls, opts in specs if "distribution_options" in opts]
    if dist:
        acc = dist[0]["distribution_options"]["Lifetime"]["accessor"]
        assert callable(acc)


def test_registered_auto_lifetime_model_wires_live(qapp):
    """The config-registered pure LifetimeModel resolves to an editor + plots
    produced by the data-driven path (PRD-38). The "Lifetime" menu entry now
    points at the pure compute model, not a hand-written widget."""
    import importlib

    import numpy as np
    from qtpy import QtWidgets

    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor, model_plot_specs

    # resolve exactly as main_helper._resolve_class would from the yaml entry
    path = "chisurf.core.models.description.tcspc_lifetime"
    mod, cls = path.rsplit(".", 1)
    model_class = getattr(importlib.import_module(mod), cls)
    assert model_class.name == "Lifetime"

    data = DataCurve(x=np.linspace(0, 25, 256), y=np.ones(256))
    fit = fit_mod.Fit(model_class=model_class, data=data)
    assert not isinstance(fit.model, QtWidgets.QWidget)  # pure model

    editor = build_model_editor(fit.model)
    assert isinstance(editor, AutoModelWidget)
    specs = model_plot_specs(fit.model)
    assert len(specs) == 6  # line, fit_table, fit_info, parameter_scan, distribution, residual


def test_code_view_resolves_model_view_json(qapp, lifetime_model):
    """The fit window's code toggle opens what the editor is derived from: the description."""
    import pathlib

    from chisurf.gui.devtools.source_jump import resolve_model_view_spec_path

    target = resolve_model_view_spec_path(lifetime_model)
    assert target is not None
    path, line = target
    assert pathlib.Path(path).name == "tcspc_lifetime.json"
    assert pathlib.Path(path).exists() and line == 1

    class Bare:
        pass
    assert resolve_model_view_spec_path(Bare()) is None


def _a_still_legacy_widget_model():
    """Return a registered model class that is still a hand-written Qt widget.

    Discovered from the config rather than named, because the point of the tests
    below is the MRO walk itself, not any one model: naming a model means
    repointing the test every time that model is migrated, which is how these
    two ended up asserting against classes that had become aliases. When the
    last legacy widget is gone the walk is moot and the tests skip themselves.
    """
    import importlib
    import pathlib

    import yaml
    from qtpy import QtWidgets

    import chisurf.core.settings as settings

    cfg = pathlib.Path(settings.__file__).parent / "experiment_configs.yaml"
    data = yaml.safe_load(cfg.read_text())
    for path in data.get("tcspc", {}).get("models", []):
        module_name, class_name = path.rsplit(".", 1)
        try:
            cls = getattr(importlib.import_module(module_name), class_name)
        except Exception:
            continue
        if not (isinstance(cls, type) and issubclass(cls, QtWidgets.QWidget)):
            continue
        # It must be *constructible*: ``EtModelFreeWidget`` is registered and
        # abstract (no ``update_model``), so picking it in the menu can only fail.
        # A test that instantiated it would report that pre-existing breakage as a
        # failure of the MRO walk it is actually checking.
        if getattr(cls, "__abstractmethods__", None):
            continue
        return cls
    return None


def test_code_view_legacy_widget_resolves_to_compute_model(qapp):
    """The "Code" button on a *legacy* model-widget must open the pure compute
    model source + its view.json, not the GUI widget wrapper. Verifies the MRO
    walk used by FitSubWindow.show_code_view/save.

    The widget is discovered from the config (see
    :func:`_a_still_legacy_widget_model`) rather than named.
    """
    import inspect
    import pathlib

    import numpy as np
    from qtpy import QtWidgets

    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.model import Model
    from chisurf.gui.devtools.source_jump import (
        resolve_compute_model_class,
        resolve_model_view_spec_path,
    )

    widget_cls = _a_still_legacy_widget_model()
    if widget_cls is None:
        pytest.skip("no hand-written model widgets remain — the MRO walk is moot")

    data = DataCurve(x=np.linspace(0, 25, 256), y=np.ones(256))
    fit = fit_mod.Fit(model_class=widget_cls, data=data)
    m = fit.model
    assert isinstance(m, QtWidgets.QWidget)

    # the most-derived *non-Qt* Model in the MRO is the pure compute model
    compute = resolve_compute_model_class(m)
    assert compute is not None
    assert issubclass(compute, Model)
    assert not issubclass(compute, QtWidgets.QWidget)
    src = inspect.getsourcefile(compute)
    assert "core/models" in pathlib.Path(src).as_posix()

    # the view.json path must resolve against the *declaring* class's directory,
    # not the widget's — an inherited view_spec_file used to look for the file
    # next to the widget and fail
    target = resolve_model_view_spec_path(m)
    if target is not None:
        assert pathlib.Path(target[0]).name.endswith(".view.json")
        assert pathlib.Path(target[0]).exists()


def test_parameter_group_sections_populate(qapp, lifetime_model):
    """Every parameter the active structure uses is drawn: the lifetimes and the instrument."""
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    w = AutoModelWidget(lifetime_model)
    assert _rows(w) >= len(lifetime_model.structure_parameter_ids())


@pytest.fixture
def registered_lifetime_model(lifetime_model):
    """A lifetime model whose fit is registered with the fit machinery.

    Controls that edit a fit dispatch at a *fit index* and deliberately do
    nothing when the model's fit is not registered -- dispatching at fit 0
    instead would edit whichever fit happened to be first.
    """
    import chisurf as cs

    cs.fits.append(lifetime_model.fit)
    try:
        yield lifetime_model
    finally:
        cs.fits.remove(lifetime_model.fit)


def test_curve_input_widget_renders_and_dispatches(qapp, registered_lifetime_model, monkeypatch):
    """The IRF input renders as a CurveInputWidget and a selection dispatches the
    view's dataset action with its slot and the index/name payload keys."""
    import chisurf as cs
    from chisurf.gui.autoform.sections.builtin import CurveInputWidget
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    w = AutoModelWidget(registered_lifetime_model)
    irf = next(c for c in w.findChildren(CurveInputWidget)
               if (c._section.action_fixed or {}).get("slot") == "response")

    dispatched = []
    monkeypatch.setattr(cs.core.actions, "dispatch",
                        lambda name, payload=None: dispatched.append((name, dict(payload or {}))))

    class _Sel:
        selected_curve_index = 3
        curve_name = "irf_curve.txt"
    irf._selector = _Sel()
    irf._on_change()

    name, payload = next((n, p) for n, p in dispatched if n == "model.set_dataset")
    assert payload.get("idx") == 3 and payload.get("name") == "irf_curve.txt"
    assert payload.get("slot") == "response" and "fit_index" in payload


def test_choice_and_toggle_controls_mutate_the_model(qapp, lifetime_model):
    """The topology is a choice and the switches are scalars; both write through."""
    from chisurf.gui.autoform.sections.builtin import ChoiceWidget, ToggleWidget
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    w = AutoModelWidget(lifetime_model)
    choices = {c._section.attr: c for c in w.findChildren(ChoiceWidget)}
    toggles = {t._section.attr: t for t in w.findChildren(ToggleWidget)}
    assert "structure" in choices
    assert {"scalars.convolve", "scalars.periodic_excitation", "scalars.pile_up"} <= set(toggles)

    before = bool(lifetime_model.get_scalar("convolve"))
    toggles["scalars.convolve"].checkbox.setChecked(not before)
    assert bool(lifetime_model.get_scalar("convolve")) == (not before)


def test_add_fit_display_path_wires_pure_model(qapp, lifetime_model):
    """Reproduces the live add_fit crash: core_fit did
    ``modelLayout.addWidget(fit.model)`` assuming the model is a widget. A pure
    model must be placed via its editor widget instead, cached for show/hide."""
    from qtpy import QtWidgets

    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import (
        build_model_editor,
        hide_model_editor,
        model_editor_widget,
        show_model_editor,
    )

    m = lifetime_model
    assert not isinstance(m, QtWidgets.QWidget)  # pure model

    layout = QtWidgets.QVBoxLayout()
    editor = build_model_editor(m)
    layout.addWidget(editor)  # used to raise TypeError for a pure model
    assert isinstance(editor, AutoModelWidget)

    # cached: same instance reused for lookups + show/hide
    assert build_model_editor(m) is editor
    assert model_editor_widget(m) is editor
    hide_model_editor(m)
    assert not editor.isVisible()
    show_model_editor(m)
    # show/hide on a model with no editor must be a quiet no-op
    class Bare:
        pass
    show_model_editor(Bare())
    hide_model_editor(Bare())
    assert model_editor_widget(Bare()) is None


def test_plots_come_only_from_the_view_spec(qapp):
    """A model's plots are resolved from ``view_spec().plots``, nothing else.

    ``plot_classes`` — a model naming GUI plot classes — is gone (PRD-38 task 9).
    A model with no declared plots gets *no* plot tabs, which is a visible,
    fixable state; the old fallback could hand it another model's plots instead.
    """
    import numpy as np
    from qtpy import QtWidgets

    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.description import tcspc_lifetime as LifetimeModel
    from chisurf.gui.widgets.models.model_editor import model_plot_specs

    data = DataCurve(x=np.linspace(0.05, 25, 256), y=np.ones(256))
    model = fit_mod.Fit(model_class=LifetimeModel, data=data).model
    assert not isinstance(model, QtWidgets.QWidget)

    declared = {plot.key for plot in model.view_spec().plots}
    resolved = model_plot_specs(model)
    assert resolved, "the lifetime model declares plots but none resolved"
    assert len(resolved) <= len(declared)
    assert not hasattr(model, "plot_classes")


def test_a_model_with_no_declared_plots_gets_none(qapp):
    """No plots declared means no plot tabs — not somebody else's plots."""
    from chisurf.gui.widgets.models.model_editor import model_plot_specs

    class Plotless:
        def view_spec(self):
            raise RuntimeError("no view spec")

    assert model_plot_specs(Plotless()) == []


def test_autoform_renders_a_parameter_group_without_json(qapp):
    """PRD-40 Task 4: AutoForm.from_parameter_group renders a bare param group
    (no view.json, no Model) into real parameter widgets."""
    from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
    from chisurf.gui.autoform import AutoForm

    group = FittingParameterGroup(
        name="kinetics",
        parameters=[
            FittingParameter(name="k1", value=1.0),
            FittingParameter(name="k2", value=2.0),
        ],
    )
    w = AutoForm.from_parameter_group(group)
    # one section widget + one trailing stretch = 2 items
    assert w._layout.count() >= 1
    assert len(w.parameter_widgets) >= 2


def test_value_section_binds_scalar_attributes(qapp):
    """PRD-40 Task 5 primitive: ValueSection int/str fields read and write the
    bound object's attributes (the generic typed-field renderer)."""
    from types import SimpleNamespace

    from chisurf.core import dataspec as ds
    from chisurf.gui.autoform.sections.builtin import ValueWidget

    class _M:
        def __init__(self):
            self.grp = SimpleNamespace(count=5, label="hi")

    m = _M()

    wi = ValueWidget(m, ds.ValueSection(target="grp", attr="count", kind="int", label="Count"))
    assert wi.editor.value() == 5
    wi.editor.setValue(9)  # valueChanged -> _commit -> setattr
    assert m.grp.count == 9

    ws = ValueWidget(m, ds.ValueSection(target="grp", attr="label", kind="str", label="Label"))
    assert ws.editor.text() == "hi"
    ws.editor.setText("bye")
    ws.editor.editingFinished.emit()
    assert m.grp.label == "bye"


def test_field_tooltip_falls_back_to_parameter_registry(qtbot):
    """A field with no explicit ``description`` picks up its tooltip from the
    shared parameter registry, keyed on the bound ``attr`` name.

    Authored view specs get inline help for free: whenever a bound attribute
    matches a registered parameter, the AutoForm field, its editor, and its
    label all show the registry description.
    """
    from types import SimpleNamespace

    from chisurf.core import dataspec as ds
    from chisurf.core import settings
    from chisurf.gui.autoform.sections.builtin import ValueWidget

    # Pick a real, unambiguous registry entry that actually has a description
    # so the test tracks the shipped registry rather than a hand-crafted stub.
    params = settings.parameter_registry.get("parameters", {})
    name = next(
        (k for k, v in params.items() if v.get("description") and not v.get("ambiguous")),
        None,
    )
    assert name is not None, "registry has no unambiguous described parameter"
    expected = params[name]["description"]

    class _M:
        def __init__(self):
            self.grp = SimpleNamespace(**{name: 1.0})

    m = _M()

    # Resolution logic is Qt-free: exercise it through the bound-control mixin
    # directly (no widget teardown), covering registry hit, explicit override
    # and unknown attribute.
    from chisurf.gui.autoform.sections.builtin import _BoundControlMixin

    class _Probe(_BoundControlMixin):
        def __init__(self, model, section):
            self._model = model
            self._section = section

    hit = _Probe(m, ds.ValueSection(target="grp", attr=name, kind="float", label=name))
    assert hit._effective_description() == expected

    override = _Probe(
        m,
        ds.ValueSection(
            target="grp", attr=name, kind="float", label=name, description="Explicit help"
        ),
    )
    assert override._effective_description() == "Explicit help"

    miss = _Probe(
        m, ds.ValueSection(target="grp", attr="totally_unknown_zzz", kind="float", label="x")
    )
    assert miss._effective_description() == ""

    # End-to-end: the resolved description is applied to both the container
    # (which feeds the field's label tooltip) and the editor, since Qt does not
    # propagate a parent's tooltip to its children.
    w = ValueWidget(m, ds.ValueSection(target="grp", attr=name, kind="float", label=name))
    qtbot.addWidget(w)
    assert expected[:20] in w.toolTip()
    assert expected[:20] in w.editor.toolTip()


# ---- LifetimeMixtureModel (AutoForm-based lifetime mixer) ---------------

@pytest.fixture
def mixture_model():
    """Build a LifetimeMixtureModel for AutoForm tests."""
    try:
        import chisurf.core.fitting.fit as fit_mod
        from chisurf.core.data import DataCurve
        from chisurf.core.models.description import tcspc_mixture as LifetimeMixtureModel
    except Exception as exc:
        pytest.skip(f"mixture model import failed: {exc}")
    x = np.linspace(0, 25, 256)
    data = DataCurve(x=x, y=np.ones_like(x))
    fit = fit_mod.Fit(model_class=LifetimeMixtureModel, data=data)
    return fit.model


def test_mixture_new_model_is_pure(qapp, mixture_model):
    """LifetimeMixtureModel is Qt-free — AutoForm builds its editor.

    The class-level ``name`` is the menu label; the instance's ``name`` is set
    to the class name by Base.__init__ (same convention as LifetimeModel).
    """
    from qtpy import QtWidgets

    from chisurf.core.models.description import tcspc_mixture as LifetimeMixtureModel
    assert not isinstance(mixture_model, QtWidgets.QWidget)
    # class attribute is the menu/registry label
    assert LifetimeMixtureModel.name == "Lifetime mixture"


def test_mixture_new_model_view_spec_has_fit_mixer(qapp, mixture_model):
    """The mixture's derived editor declares a fit_mixer section."""
    from chisurf.core.models import view_spec as vs
    spec = mixture_model.view_spec()
    customs = [s for s in spec.flat_sections() if isinstance(s, vs.CustomSection)]
    mixer = next((s for s in customs if s.key == "fit_mixer"), None)
    assert mixer is not None, "the mixture editor must contain a fit_mixer custom section"


def test_mixture_new_model_fit_mixer_section_registered(qapp):
    """The fit_mixer custom section is registered in the section registry."""
    from chisurf.gui.autoform.sections.registry import get_section_factory
    assert get_section_factory("fit_mixer") is not None


def test_mixture_new_model_autoform_renders(qapp, mixture_model):
    """AutoForm builds a non-empty editor from mix_model.view.json."""
    from chisurf.gui.autoform import AutoForm
    w = AutoForm(mixture_model)
    # At least some widgets were created (convolve params etc.)
    assert w._layout.count() > 0


def test_mixture_new_model_fit_mixer_widget_renders(qapp, mixture_model):
    """The FitMixerWidget renders and exposes its controls."""
    from chisurf.gui.autoform.sections.builtin import FitMixerWidget
    w = FitMixerWidget(model=mixture_model)
    assert w.cb is not None  # fit combo box
    assert w.fit_list is not None  # added-fits list
    assert w._fractions_container is not None


def test_mixture_new_model_append_pop_updates_fractions(qapp, mixture_model):
    """append_model / pop_model change _fractions; FitMixerWidget._rebuild_fractions
    must not raise and the fraction count matches the model state."""
    import numpy as np

    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.description import tcspc_lifetime as LifetimeModel
    from chisurf.gui.autoform.sections.builtin import FitMixerWidget

    # Build a donor lifetime fit to mix in
    x = np.linspace(0, 25, 256)
    data = DataCurve(x=x, y=np.ones_like(x))
    donor_fit = fit_mod.Fit(model_class=LifetimeModel, data=data)

    widget = FitMixerWidget(model=mixture_model)
    assert len(mixture_model._fractions) == 0

    # Manually append (simulating what _on_add does via the UI)
    mixture_model.append_model(donor_fit.model, "x_1")
    widget._rebuild_fractions()  # must not raise
    assert len(mixture_model._fractions) == 1

    # Remove it back
    mixture_model.pop_model(0)
    widget._rebuild_fractions()
    assert len(mixture_model._fractions) == 0


def test_mixture_new_model_build_editor(qapp, mixture_model):
    """build_model_editor returns an AutoForm widget for the pure mixture model."""
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.widgets.models.model_editor import build_model_editor
    editor = build_model_editor(mixture_model)
    assert isinstance(editor, AutoForm)
    assert editor.model is mixture_model

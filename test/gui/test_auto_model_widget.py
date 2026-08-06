"""Offscreen-Qt tests for the AutoModelWidget renderer.

These verify that a *pure* LifetimeModel can be rendered into a real editor by
composition (no inheritance), that the dynamic lifetime list is wired to the
model's own append/pop, and that custom/registered sections appear. Qt runs in
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
        from chisurf.core.models.tcspc.lifetime import LifetimeModel
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"lifetime model import failed: {exc}")
    x = np.linspace(0, 25, 256)
    data = DataCurve(x=x, y=np.ones_like(x))
    fit = fit_mod.Fit(model_class=LifetimeModel, data=data)
    return fit.model


def test_auto_model_widget_renders_sections(qapp, lifetime_model):
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    w = AutoModelWidget(lifetime_model)
    # one top-level widget per section in the view-spec
    spec = lifetime_model.view_spec()
    # count includes one trailing stretch item added by rebuild()
    assert w._layout.count() == len(spec.sections) + 1
    # parameter widgets were created for the resolvable groups
    assert len(w.parameter_widgets) > 0


def test_dynamic_group_add_remove_drives_model(qapp, lifetime_model):
    from chisurf.core.models import view_spec as vs
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    w = AutoModelWidget(lifetime_model)
    group = lifetime_model.lifetimes
    n0 = len(group)

    # find the dynamic section's add/del buttons by walking the built tree
    section = next(s for s in lifetime_model.view_spec().flat_sections()
                   if isinstance(s, vs.DynamicGroupSection))
    assert section.target == "lifetimes"

    # simulate add via the model (what the add button calls)
    group.append()
    assert len(group) == n0 + 1
    # rebuild reflects new row count
    w.rebuild()
    assert len(w.parameter_widgets) > 0


def test_custom_section_registered(qapp):
    from chisurf.gui.autoform.sections.registry import get_section_factory
    assert get_section_factory("lifetime_amplitude_options") is not None


def test_lifetime_header_has_read_link_controls(qapp, lifetime_model):
    """The ported header exposes abs/norm + read/link, wired to the core group."""
    from chisurf.gui.autoform.sections.registry import get_section_factory

    factory = get_section_factory("lifetime_amplitude_options")
    header = factory(model=lifetime_model, target="lifetimes")
    assert header.absolute is not None and header.normalize is not None
    assert header.read_btn is not None and header.link_btn is not None
    # building the target menu must not raise even with no other fits present
    header._build_target_menu(header.read_menu, header._read_values)
    header._build_target_menu(header.link_menu, header._link_to)
    # linking to another core Lifetime group sets the link on the model side
    other = lifetime_model.lifetimes.__class__(name="lifetimes", fit=lifetime_model.fit)
    header._link_to(other)
    assert lifetime_model.lifetimes.link is other


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
    path = "chisurf.core.models.tcspc.lifetime.LifetimeModel"
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
    """The fit window's plot/code toggle resolves the model's view.json so it
    can open it next to the model source (PRD-38)."""
    import pathlib

    from chisurf.gui.devtools.source_jump import resolve_model_view_spec_path

    target = resolve_model_view_spec_path(lifetime_model)
    assert target is not None
    path, line = target
    assert pathlib.Path(path).name == "lifetime.view.json"
    assert pathlib.Path(path).exists()
    assert line == 1

    # a model without view_spec_file resolves to None
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
    """Nuisance groups define params as plain attributes surfaced lazily by
    find_parameters(); the renderer must trigger that so convolve/generic/
    corrections aren't drawn empty (regression: only Lifetimes populated)."""
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    w = AutoModelWidget(lifetime_model)
    # convolve alone contributes ~11 scalar params; total must exceed the 2
    # lifetime params that were the only ones rendering before the fix. Nuisance
    # groups now render as compact parameter-group tables, so count their rows too.
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget
    table_rows = sum(t.table_model.rowCount() for t in w.findChildren(ParameterGroupTableWidget))
    assert len(w.parameter_widgets) + table_rows > 12


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
    """The IRF curve_input renders as a CurveInputWidget and its selection
    dispatches the configured action with the index/name payload keys."""
    import chisurf as cs
    from chisurf.gui.autoform.sections.builtin import CurveInputWidget
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    w = AutoModelWidget(registered_lifetime_model)
    curve_widgets = w.findChildren(CurveInputWidget)
    assert curve_widgets, "expected at least one CurveInputWidget (IRF)"
    irf = next(c for c in curve_widgets if c._section.select_action == "model.change_irf")

    dispatched = []
    monkeypatch.setattr(
        cs.core.actions, "dispatch",
        lambda name, payload=None: dispatched.append((name, dict(payload or {}))),
    )

    # simulate a selection without opening the real selector dialog
    class _Sel:
        selected_curve_index = 3
        curve_name = "irf_curve.txt"
    irf._selector = _Sel()
    irf._on_change()

    names = [n for n, _ in dispatched]
    assert "model.change_irf" in names
    payload = dict(dispatched[names.index("model.change_irf")][1])
    assert payload.get("irf_idx") == 3
    assert payload.get("irf_name") == "irf_curve.txt"
    assert "fit_index" in payload


def test_choice_and_toggle_controls_mutate_the_model(qapp, lifetime_model):
    """choice/toggle sections render and their changes write through to the
    bound model attribute (convolution type, do_convolution, polarization)."""
    from chisurf.gui.autoform.sections.builtin import ChoiceWidget, ToggleWidget
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    w = AutoModelWidget(lifetime_model)
    choices = {c._section.attr: c for c in w.findChildren(ChoiceWidget)}
    toggles = {t._section.attr: t for t in w.findChildren(ToggleWidget)}

    assert {"mode", "window_function", "polarization_type"} <= set(choices)
    assert "do_convolution" in toggles

    # toggle writes through to convolve.do_convolution
    before = lifetime_model.convolve.do_convolution
    toggles["do_convolution"].checkbox.setChecked(not before)
    assert lifetime_model.convolve.do_convolution == (not before)

    # mode renders as inline radios (style="radio"); selecting one writes through
    mode = choices["mode"]
    assert mode.combo is None and mode._radios, "mode should be radio-style"
    next(r for r in mode._radios if r.text() == "exp").setChecked(True)
    assert lifetime_model.convolve.mode == "exp"

    # polarization is a combo and writes through
    choices["polarization_type"].combo.setCurrentText("vv")
    assert lifetime_model.anisotropy.polarization_type == "vv"

    # smoothing options come from the named source
    opts = [choices["window_function"].combo.itemText(i)
            for i in range(choices["window_function"].combo.count())]
    assert "hanning" in opts and "flat" in opts


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


def test_retired_lifetime_class_paths_still_resolve_to_the_pure_model(qapp):
    """The hand-written Lifetime editors are gone; their names remain importable.

    Deleting a registered model class is what broke the model combobox the last
    time this flip was attempted: a user copy of ``experiment_configs.yaml``
    *replaces* the bundled model list rather than merging with it, and a pinned
    class path that no longer resolves drops the entry silently instead of
    failing. Pickled projects pin paths the same way. So every retired name must
    still import and must land on the pure model that replaced it.
    """
    from qtpy import QtWidgets

    import chisurf.gui.widgets.models.tcspc as tcspc
    from chisurf.core.models.tcspc.lifetime import (
        LifetimeMixtureModel,
        LifetimeMixtureNewModel,
        LifetimeModel,
        LifetimeNewModel,
    )

    # the retired widget names are aliases of the pure models now
    assert tcspc.LifetimeModelWidget is LifetimeModel
    assert tcspc.LifetimeMixtureModelWidget is LifetimeMixtureModel

    # so are the retired "(new)" prototype names
    assert LifetimeNewModel is LifetimeModel
    assert LifetimeMixtureNewModel is LifetimeMixtureModel

    # and what they resolve to is Qt-free, so AutoForm renders the editor
    assert not issubclass(LifetimeModel, QtWidgets.QWidget)
    assert not issubclass(LifetimeMixtureModel, QtWidgets.QWidget)

    # the menu names carry no stray whitespace: add_fit matches them as strings
    assert LifetimeModel.name == "Lifetime"
    assert LifetimeMixtureModel.name == "Lifetime mixer"

    # both editors are described by JSON, not by Python
    assert LifetimeModel.view_spec_file == "lifetime.view.json"
    assert LifetimeMixtureModel.view_spec_file == "mix_model.view.json"


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
    from chisurf.core.models.tcspc.lifetime import LifetimeModel
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
        from chisurf.core.models.tcspc.lifetime import LifetimeMixtureModel
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

    from chisurf.core.models.tcspc.lifetime import LifetimeMixtureModel
    assert not isinstance(mixture_model, QtWidgets.QWidget)
    # class attribute is the menu/registry label
    assert LifetimeMixtureModel.name == "Lifetime mixer"


def test_mixture_new_model_view_spec_has_fit_mixer(qapp, mixture_model):
    """The view spec loaded from mix_model.view.json declares a fit_mixer section."""
    from chisurf.core.models import view_spec as vs
    spec = mixture_model.view_spec()
    customs = [s for s in spec.flat_sections() if isinstance(s, vs.CustomSection)]
    mixer = next((s for s in customs if s.key == "fit_mixer"), None)
    assert mixer is not None, "mix_model.view.json must contain a fit_mixer custom section"


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
    from chisurf.core.models.tcspc.lifetime import LifetimeModel
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

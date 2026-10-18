"""The fit controller's sampler settings model, apart from any widget.

The controls are rendered from ``fitting_controls.view.json`` by the emtk shell; what these
pin is the Qt-free :class:`~chisurf.core.fitting.optimization_settings.OptimizationSettingsModel`
behind them: each sampler keeps its own settings, the selectors come from the sampler registry,
and what the run is told is what was set.
"""

import chisurf.core.fitting.fit as fit_module


def test_each_sampler_keeps_its_own_settings():
    """Switching sampler must not lose what was set, nor mix the two up.

    They do not take the same knobs: handing one another's to it would be a
    TypeError at the start of a long run.
    """
    from chisurf.core.fitting.optimization_settings import OptimizationSettingsModel

    model = OptimizationSettingsModel()
    model.method = "blocked"
    model.sampler_changed()
    model.step_size = 0.25
    model._remember_sampler_settings()

    model.method = "slice"
    model.sampler_changed()
    model.std = 0.05

    saved = model.sampling_settings()["samplers"]
    assert saved["blocked"]["step_size"] == 0.25
    assert saved["slice"]["std"] == 0.05
    assert "std" not in saved["blocked"]
    assert "step_size" not in saved["slice"]


def test_the_settings_offer_every_sampler_and_format_that_exists():
    """The selectors are populated by the samplers, not by a list in a file.

    Adding a sampler must make it selectable without anyone editing a combo
    box, so the options are compared against the registry itself.
    """
    from chisurf.core.fitting import sample as sample_module
    from chisurf.core.fitting.optimization_settings import OptimizationSettingsModel

    model = OptimizationSettingsModel()
    assert [name for name, _ in model.sampler_options()] == list(sample_module.SAMPLERS)
    assert [name for name, _ in model.chain_format_options()] == list(fit_module.CHAIN_FORMATS)


def test_each_sampler_advertises_its_own_settings():
    """Choosing a sampler shows what *it* takes, derived from its signature."""
    from chisurf.core.fitting.optimization_settings import OptimizationSettingsModel

    model = OptimizationSettingsModel()
    model.method = "blocked"
    model.sampler_changed()
    blocked = {s["attr"] for s in model._sampler_sections()}
    model.method = "slice"
    model.sampler_changed()
    slice_ = {s["attr"] for s in model._sampler_sections()}

    assert "step_size" in blocked and "step_size" not in slice_
    assert "tune" in slice_ and "tune" not in blocked
    # ...and every one of them carries the docstring text as its tooltip.
    assert all(s["description"] for s in model._sampler_sections())


def test_the_settings_are_what_the_run_is_told():
    """A dialog that changed nothing the run reads would be decoration."""
    from chisurf.core.fitting.optimization_settings import OptimizationSettingsModel

    model = OptimizationSettingsModel()
    model.method = "slice"
    model.chain_format = "hdf5"
    model.sampler_changed()
    values = model.sampling_settings()
    assert values["method"] == "slice"
    assert values["chain_format"] == "hdf5"
    assert values["chain_format"] in fit_module.CHAIN_FORMATS

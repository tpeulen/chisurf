"""PCH-experiment model-selector resolution guard (headless, offscreen).

Every model configured for the PCH experiment must resolve to a class exposing
a non-empty ``name`` (so a renamed/deleted widget fails here instead of silently
vanishing from the model combobox).  Explicitly covers the new ``FidaModel``.
"""

from __future__ import annotations

import importlib
import pathlib

import pytest


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _pch_model_paths():
    import yaml

    import chisurf.core.settings as settings

    cfg = pathlib.Path(settings.__file__).parent / "experiment_configs.yaml"
    data = yaml.safe_load(cfg.read_text())
    return list(data.get("pch", {}).get("models", []))


def _resolve(path):
    module_name, class_name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module_name), class_name)


def test_every_configured_pch_model_resolves_with_a_name(qapp):
    paths = _pch_model_paths()
    assert paths, "no PCH models configured"
    problems, names = [], []
    for path in paths:
        try:
            cls = _resolve(path)
        except Exception as exc:
            problems.append(f"{path}: unresolved ({exc})")
            continue
        name = getattr(cls, "name", None)
        if not name or not str(name).strip():
            problems.append(f"{path}: missing/empty .name")
        else:
            names.append(str(name))
    assert not problems, "configured PCH models that won't appear in the menu:\n" + "\n".join(
        problems
    )
    assert any("FIDA" in n for n in names), f"FIDA model missing from {names}"


def test_the_widget_pch_kernel_uses_the_three_dimensional_gaussian(qapp):
    """The kernel behind the model widget — pin its detection volume.

    ``Var/<k> - 1 == eps * gamma_2`` for a compound-Poisson PCH, and ``gamma_2``
    is a pure shape factor: ``2**-1.5`` for the 3-D Gaussian, ``2**-0.5`` if the
    radial volume element ``x**2`` is dropped.  The identity does not depend on
    the eps/N normalisation, so it pins the profile and nothing else.

    This used to import a private kernel from the widget module. There is no
    longer one to import: the widget's copy, the plugin's numba copy and the
    core implementation have been collapsed into a single tttrlib delegation,
    so what the widget reaches is what this reaches.
    """
    import numpy as np

    from chisurf.core.models.pch.pch import pch_open_system

    k_vals = np.arange(60, dtype=float)
    for brightness in (0.5, 1.0):
        p = pch_open_system(k_vals, brightness, 0.5, maxN=12)
        p = p / p.sum()
        mean = float((k_vals * p).sum())
        var = float((k_vals**2 * p).sum()) - mean**2
        gamma_2 = (var / mean - 1.0) / brightness
        assert np.isclose(gamma_2, 2.0**-1.5, rtol=1e-6)


def test_the_widget_pch_kernel_survives_a_long_photon_count_axis(qapp):
    """Pin the Poisson term of the kernel behind the widget.

    ``lam**k / k!`` overflows a ``double`` at ``k = 171`` (zero from there on)
    and yields ``NaN`` further out; the log-space form does neither.
    """
    import numpy as np

    from chisurf.core.models.pch.pch import pch_single_species

    p1 = pch_single_species(np.arange(400, dtype=float), 100.0)
    assert np.isfinite(p1).all()
    assert p1[200] > 0.0


def test_a_photon_count_axis_that_is_not_counts_flattens_rather_than_lies(qapp):
    """A malformed count axis must not be answered for a different one.

    The axis is taken from the dataset, so it is the user's, and the compiled
    kernel takes only ``k_max`` — it builds ``0, 1, ... k_max`` itself and
    cannot represent a gapped or offset axis. Answering anyway returns the
    histogram of an axis nobody asked about, which presents as a bad fit rather
    than as bad data; refusing costs a flat curve and a log line.
    """
    import numpy as np

    from chisurf.core.models.pch.pch import pch_mixture

    for bad in (np.arange(5, 65, dtype=float), np.array([0.0, 1.0, 3.0, 4.0])):
        with pytest.raises(ValueError, match="consecutive integers"):
            pch_mixture(bad, [3.0], [2.0])


def test_a_mixture_needs_one_occupancy_per_brightness(qapp):
    """Unequal per-species lists are refused before they reach the library.

    tttrlib's ``pch_mixture`` subscripts the occupancies with the brightness
    index and does not bounds-check, so an unequal pair reads past the end of a
    ``std::vector``. It does not crash: the memory is zero, the
    ``avg_numbers[s] <= 0.0`` guard then drops the species whose occupancy was
    never supplied, and the caller gets a normalised finite histogram of fewer
    species than it asked for. Filed upstream; this check stays in front of the
    delegation until it is fixed there.
    """
    import numpy as np

    from chisurf.core.models.pch.pch import pch_mixture

    with pytest.raises(ValueError, match="one occupancy per brightness"):
        pch_mixture(np.arange(30, dtype=float), [3.0, 8.0], [2.0])


def test_fida_model_is_a_model_curve(qapp):
    from chisurf.core.models.model import ModelCurve
    from chisurf.gui.widgets.models.pch.fida_widget import FidaModel, FidaModelWidget

    assert issubclass(FidaModel, ModelCurve)
    assert issubclass(FidaModelWidget, FidaModel)
    assert str(getattr(FidaModelWidget, "name", "")).strip()

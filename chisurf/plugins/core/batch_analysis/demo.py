"""Example data for the batch-analysis wizard: a small fake session and its batch run.

A batch needs three things a headless run does not have on its own — datasets, a
template fit and a fitting client — so the demo borrows the session the plugin's
own tests use (:mod:`chisurf.plugins.core.batch_analysis.test.fakes`): three
datasets, one template fit whose ``fit.run`` answers with known parameter and χ²
movements. ``make_demo`` runs that batch and writes the results CSV;
``load_into`` hands the same session to a live wizard.
"""

from __future__ import annotations

from pathlib import Path

STEM = "batch_demo"
N_DATASETS = 3


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the batch wizard."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "batch_analysis"


def _example_model(folder: Path):
    import threading

    from chisurf.plugins.core.batch_analysis.gui.model import BatchModel
    from chisurf.plugins.core.batch_analysis.test.fakes import FakeSession

    model = BatchModel(session=FakeSession())
    model.selected_dataset_indices = list(range(N_DATASETS))
    model.set_save_path(str(folder / f"{STEM}.csv"))
    model.run()
    if model._thread is not None:
        model._thread.join(timeout=120.0)
    model.poll()
    return model


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Run the example batch and write its results CSV."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.csv"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        model = _example_model(folder)
        if not path.is_file():
            raise RuntimeError(f"the example batch wrote nothing: {model.message}")
    return path


def load_into(app) -> Path:
    """Attach the example session to the wizard and stage the run (app or model)."""
    from chisurf.plugins.core.batch_analysis.test.fakes import FakeSession

    model = app.model if hasattr(app, "model") else app
    model.session = FakeSession()
    model.reload_fits()
    model.reload_datasets()
    model.update()
    model.selected_dataset_indices = list(range(N_DATASETS))
    model.set_save_path(str(demo_folder() / f"{STEM}.csv"))
    return model.save_path and Path(model.save_path)

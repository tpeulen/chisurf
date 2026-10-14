"""Guide 21 figures: the Burst MLE emtk app on a Fit24 model choice and on its built-in example.

Run from the repository root, headless, with a scratch settings dir::

    CHISURF_SETTINGS_DIR=$(mktemp -d) IMP_BFF_GPU=off \
        python docs/guides/screenshots/guide_21_burst_mle.py [fit24] [example]

Writes ``docs/guides/figures/21_burst_mle_model_selection.png`` and
``docs/guides/figures/21_burst_mle_synthetic_demo.png``. Read the PNGs afterwards.
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

SIZE = (1400, 900)


def _app():
    from emtk_shot import app_from

    return app_from("burst_mle_analysis")


def grab_fit24() -> None:
    """Fit24 on m000.bur of the BH SPC-132 sample (green = routing 0/8), after Auto IRF/background."""
    from emtk.testing import Driver
    from emtk_shot import render, wait
    from guides_15_25 import _BH_DETECTORS, _sm_dna_copy

    _work, folder = _sm_dna_copy()
    app = _app()
    definition = {
        "detectors": {
            name: dict(d, g_factor=1.0, l1=0.0308, l2=0.0368) for name, d in _BH_DETECTORS.items()
        },
        "windows": {},
        "file_type": "SPC-130",
    }
    app.editor.model.data["detectors"] = definition["detectors"]
    app.model.set_setup(definition)
    driver = Driver(app, SIZE)
    driver.frame(3)
    assert app.model.add_files([folder / "bi4_bur" / "m000.bur"])
    app.model.current_detector = "green"
    driver.frame(3)
    app.auto_extract()
    wait(driver, lambda: not app.job.busy, timeout=400)
    app.model.fit_model = "fit24"
    wait(driver, lambda: not app.job.busy, timeout=400)
    print("fit24:", app.model.model_result_text, flush=True)
    render(app, "21_burst_mle_model_selection.png", size=SIZE, driver=driver)
    app.close()


def grab_example() -> None:
    """Load example (16 synthetic 2 ns bursts) -> Auto IRF/background -> Fit bursts, Fit23."""
    from emtk.testing import Driver
    from emtk_shot import render, wait

    app = _app()
    driver = Driver(app, SIZE)
    driver.frame(3)
    app.model.load_example()
    driver.frame(3)
    app.auto_extract()
    wait(driver, lambda: not app.job.busy, timeout=400)
    app.fit_bursts()
    wait(driver, lambda: not app.job.busy, timeout=400)
    print("example:", app.model.status_text, "|", app.model.model_result_text, flush=True)
    render(app, "21_burst_mle_synthetic_demo.png", size=SIZE, driver=driver)
    app.close()


if __name__ == "__main__":
    wanted = set(sys.argv[1:]) or {"fit24", "example"}
    if "fit24" in wanted:
        grab_fit24()
    if "example" in wanted:
        grab_example()

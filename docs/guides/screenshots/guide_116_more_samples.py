"""Guide 116 figures: Burst Analysis' step 4, *More samples*, on the demo session.

The demo's first measurement (with its buffer, water IRF and Rh110) is walked through the hub to
fitted lifetimes; two further simulated measurements of the same sample and a file that is not a
photon stream are dropped on step 4 and run. Run from the repository root, headless::

    CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \
        python docs/guides/screenshots/guide_116_more_samples.py [OUT_DIR]

Writes ``docs/guides/figures/116_more_samples_simple.png`` and ``116_more_samples_advanced.png``;
with *OUT_DIR*, also every state (Simple and Advanced, running and done, the busy card) there.
Read the PNGs afterwards.
"""

from __future__ import annotations

import copy
import pathlib
import shutil
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

SIZE = (1400, 860)


class _WithOverlay:
    """The hub as the shell hosts it: drawn, then the busy card over it."""

    def __init__(self, hub) -> None:
        from chisurf.emtk.busy_overlay import BusyOverlay

        self.hub = hub
        self.overlay = BusyOverlay(delay_s=0.0)

    def __getattr__(self, name):
        return getattr(self.hub, name)

    def draw(self, painter, x, y, w, h):
        self.hub.draw(painter, x, y, w, h)
        self.overlay.update(self.hub)
        self.overlay.draw(painter, (x, y, w, h))


def main(out: pathlib.Path | None) -> None:
    from emtk.testing import Driver

    from chisurf.core.fluorescence import dyes
    from chisurf.plugins.burst.burst_analysis import demo
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app, receive_photons
    from emtk_shot import FIG, wait

    dyes._entries_from_database = lambda: None  # the dye database as ChiSurf ships it
    work = pathlib.Path(tempfile.mkdtemp(prefix="more_samples_shot_"))
    files = demo.make_demo(work / "demo")
    more = demo.make_more_samples(work / "demo")
    broken = work / "demo" / "sample_dsDNA_4.ptu"
    broken.write_bytes(b"not a photon stream")
    hub = create_app()
    driver = Driver(hub, SIZE)
    driver.frame(3)
    hub.setup_model.data = copy.deepcopy(demo.SETUP)
    hub.setup_model.changed()
    hub.context.channel_settings = hub.setup_model.get_settings()
    # the files are in the workspace, as dropped on the window
    from chisurf.core.plugin.workspace_input import register_result

    uids = {}
    for path in (*files.values(), *more):
        dataset = register_result(str(path), kind="photons", name=pathlib.Path(path).stem)
        uids[str(path)] = str(getattr(dataset, "unique_identifier", ""))
    data = hub.ensure_child("data")
    data.source.auto_import = False
    data.source.add_paths([files[k] for k in ("measurement", "buffer", "irf", "reference")])
    end = time.monotonic() + 120
    while (data.job.busy or not hub.context.calibration) and time.monotonic() < end:
        time.sleep(0.1)
        data.poll_calibration()
    hub.select("selection")
    driver.frame(2)
    hub.fast_forward()
    wait(driver, lambda: all(hub.step_done(r) for r in ("mle", "bva", "two_cde")), timeout=300)
    hub.select("more")
    driver.frame(3)
    step = hub.children["more"]
    dropped = [str(p) for p in (*more, broken)]
    receive_photons(hub, {"files": dropped, "datasets": [uids.get(p, "") for p in dropped]})
    driver.frame(2)
    shots: dict[str, pathlib.Path] = {}

    def grab(name: str, app=None) -> None:
        target = (out or FIG) / name
        (Driver(app, SIZE) if app is not None else driver).screenshot(target)
        shots[name] = target
        print("wrote", target, flush=True)

    assert step.run_step()
    statuses = lambda: [r["status"] for r in step.sample_rows()]  # noqa: E731
    wait(driver, lambda: "running" in statuses(), timeout=60)
    grab("more_samples_simple_running.png")
    grab("more_samples_busy_card.png", _WithOverlay(hub))
    hub.set_advanced(True)
    wait(driver, lambda: "done" in statuses() and "running" in statuses() or not step.running, timeout=120)
    grab("more_samples_advanced_running.png")
    wait(driver, lambda: not step.running, timeout=300)
    driver.frame(3)
    grab("more_samples_advanced_done.png")
    # the row's tooltip: why the third sample failed (the cells stay short)
    for name in ("sample_dsDNA_4", "sample_dsDNA_2"):
        driver.hover(name)
        for _ in range(8):
            time.sleep(0.15)
            driver.hover(name)
        grab(f"more_samples_tooltip_{name[-1]}.png")
    hub.set_advanced(False)
    driver.frame(3)
    grab("more_samples_simple_done.png")
    print("statuses:", statuses(), flush=True)
    shutil.copy(shots["more_samples_simple_done.png"], FIG / "116_more_samples_simple.png")
    shutil.copy(shots["more_samples_advanced_done.png"], FIG / "116_more_samples_advanced.png")
    hub.close()


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None)

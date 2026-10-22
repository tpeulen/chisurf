"""The LlTF tool's example: the simulated VV/VH pair, loaded and fitted."""

from pathlib import Path

from chisurf.plugins.fluorescence_decay.lltf.demo import demo_folder, make_demo
from chisurf.plugins.fluorescence_decay.lltf.gui.app import make_app


def test_make_demo_writes_the_polarized_pair():
    """The demo pair exists beside the settings in VV/VH mode."""
    files = make_demo()
    assert files["decay"].is_file() and files["decay"].stat().st_size > 0
    assert files["irf"].is_file() and files["irf"].stat().st_size > 0
    assert files["decay"].parent == demo_folder()


def test_load_example_selects_the_pair_and_fits():
    """The affordance selects the pair in VV/VH mode; the fit returns a result."""
    import time

    app = make_app()
    model = app.model
    model.load_example()
    assert model.mode == "VV/VH"
    assert Path(model.decay_file).is_file()
    model.start()
    deadline = 120.0
    while model.running and deadline > 0:
        model.poll()
        time.sleep(0.1)
        deadline -= 0.1
    model.poll()
    assert model.result

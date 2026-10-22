"""The k²-distribution calculator's example: the shipped inputs, computed and exported."""

from chisurf.plugins.calculator.kappa2_dist.demo import demo_folder, make_demo
from chisurf.plugins.calculator.kappa2_dist.gui.app import make_app


def test_make_demo_exports_the_distribution():
    """The demo CSV is the tool's own answer in the shipped qt_saved.csv format."""
    path = make_demo()
    text = path.read_text()
    assert text.startswith("# Kappa2 Distribution")
    assert "kappa2,probability" in text
    data = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(data) > 50


def test_load_example_recomputes_and_exports():
    """The affordance recomputes with the shipped inputs and exports beside the settings."""
    app = make_app()
    path = app.load_example()
    assert path.is_file() and path.stat().st_size > 0
    assert path.parent == demo_folder()

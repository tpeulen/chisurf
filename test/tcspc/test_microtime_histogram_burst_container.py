"""Native exports follow the selected burst container and the actual photon source name."""

from pathlib import Path

from chisurf.plugins.tttr.microtime_histogram.gui.model import HistogramModel


def test_selected_burst_container_owns_the_histogram_output(tmp_path):
    """A checked burst container (.pto) overrides the photon source directory for saving."""
    photons = tmp_path / "photons"
    bursts = tmp_path / "analysis"
    photons.mkdir()
    bursts.mkdir()
    source = photons / "measurement_001.ptu"
    container = bursts / "measurement_0.pto"
    source.write_bytes(b"fixture")
    container.write_bytes(b"fixture")
    model = HistogramModel()
    model.add_paths([source])
    assert Path(model.output) == photons / "measurement_(0)-(1).dat"
    model.add_paths([container], bursts=True)
    assert Path(model.output) == bursts / "measurement_(0)-(1).dat"
    model.burst_enabled[str(container.resolve())] = False
    model.update_output_filename()
    assert Path(model.output) == photons / "measurement_(0)-(1).dat"

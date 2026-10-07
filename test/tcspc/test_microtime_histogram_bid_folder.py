"""Native exports follow the selected burst folder and actual photon source name."""

from pathlib import Path

from chisurf.plugins.tttr.microtime_histogram.gui.model import HistogramModel


def test_selected_burst_folder_owns_the_histogram_output(tmp_path):
    """A checked BID/BUR source overrides the photon source directory for saving."""
    photons = tmp_path / "photons"
    bursts = tmp_path / "bi4_bur"
    photons.mkdir()
    bursts.mkdir()
    source = photons / "measurement_001.ptu"
    burst = bursts / "measurement_0.bur"
    source.write_bytes(b"fixture")
    burst.write_text("0\t1\n")
    model = HistogramModel()
    model.add_paths([source])
    assert Path(model.output) == photons / "measurement_(0)-(1).dat"
    model.add_paths([burst], bids=True)
    assert Path(model.output) == bursts / "measurement_(0)-(1).dat"
    model.bid_enabled[str(burst.resolve())] = False
    model.update_output_filename()
    assert Path(model.output) == photons / "measurement_(0)-(1).dat"

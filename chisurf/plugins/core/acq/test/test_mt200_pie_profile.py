"""MT200 PIE profile must use the hardware's actual routing inputs."""
from pathlib import Path
from chisurf.plugins.core.acq.live import settings_file
from chisurf.plugins.core.acq.gui.record_app import RecordModel


def test_mt200_pie_profile_assigns_both_detectors_and_windows(tmp_path):
    profile = Path(__file__).parents[1] / 'profiles' / 'mt200_pie.json'
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model._form_from(settings_file.load(str(profile)))
    experiment = model.make_experiment(1563, 32e-12)
    assert experiment.channels('donor') == [0]
    assert experiment.channels('acceptor') == [2]
    assert experiment.preset == 'pie'
    assert set(experiment.setup['windows']) >= {'prompt', 'delayed'}

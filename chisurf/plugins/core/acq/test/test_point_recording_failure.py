"""Point sequences preserve a failed recording and stop before the next point."""
from types import SimpleNamespace

from chisurf.plugins.core.acq.live import points
from chisurf.plugins.core.acq.live.scanner import ScanSettings


def test_failed_point_stops_sequence_and_model_reports_it(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.live import molecules

    moves = []
    analyzed = []
    class Scanner:
        def move_to(self, x, y):
            moves.append((x, y))
            return (x, y)

    class FailedSession:
        def __init__(self, source, *, ptu_path, index, **kwargs):
            self.ptu_path = ptu_path
            self.error = 'simulated disk full'
            self.index = index
            self.embed = False
        def start(self):
            self.ptu_path.write_bytes(b'partial recording')
        def wait(self):
            return SimpleNamespace(ptu=self.ptu_path, stop_reason='error', dataset_uid='')
        def register(self):
            pass
        def _photon_dataset(self):
            return None

    monkeypatch.setattr(points, 'PointRecordSession', FailedSession)
    monkeypatch.setattr(molecules, 'analyse_point', lambda *a: analyzed.append(a))
    target = tmp_path / 'traces' / 'point.ptu'
    target.parent.mkdir()
    scan = ScanSettings(points=[(1, 2), (3, 4)])
    seq = points.PointSequence(Scanner(), object(), scan,
                               reserved_paths=[target, target.parent / 'point2.ptu'])
    seq.run()
    assert moves == [(1., 2.)]
    assert len(seq.results) == 1
    assert 'simulated disk full' in seq.error
    assert seq.results[0].run.ptu.read_bytes() == b'partial recording'
    assert not (target.parent / 'point2.ptu').exists()

    model = RecordModel(output_dir=tmp_path)
    model.points = [{'index': 0, 'status': 'waiting'}, {'index': 1, 'status': 'waiting'}]
    model.sequence = seq
    model._sequence_finished = False
    model._handled_points = 0
    model._run_shutters = lambda *_: None
    model.poll_points()
    assert model.points[0]['status'] == 'recording error'
    assert model.points[1]['status'] == 'not measured'
    assert 'Point recording error' in model.status_text
    assert 'simulated disk full' in model.status_detail
    assert not analyzed
    assert not model._analysis_threads
    model.sequence = None
    model.close()

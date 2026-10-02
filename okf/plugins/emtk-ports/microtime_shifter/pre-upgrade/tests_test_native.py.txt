"""Native photon shifts, preview agreement, alignment and archival context."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from chisurf.core.fio.tttr_shift import apply_shifts
from chisurf.plugins.tttr.tttr_microtime_shifter.gui.app import create_app


class Stream:
    def __init__(self):
        self.micro_times = np.array([0, 1, 1, 2, 4, 5, 5, 7], dtype=np.int64)
        self.routing_channels = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        self.header = SimpleNamespace(get_effective_number_of_micro_time_channels=lambda: 8)

    def shift_micro_time_by_channel(self, channel, shift):
        mask = self.routing_channels == channel
        self.micro_times[mask] = (self.micro_times[mask] + shift) % 8


class Client:
    def __init__(self):
        self.request = None

    def load_metadata(self, path):
        return {"n_mt": 8, "routing_channels": [0, 1], "n_photons": 8}

    def identify(self, path):
        return {"found": True, "artifact_id": "source-artifact"}

    def histogram(self, paths, **kwargs):
        stream = Stream()
        return {
            "n_mt": 8,
            "histograms": {
                str(ch): np.bincount(
                    stream.micro_times[stream.routing_channels == ch], minlength=8
                ).tolist()
                for ch in [0, 1]
            },
        }

    def apply(self, **kwargs):
        self.request = kwargs
        stream = Stream()
        applied = apply_shifts(stream, kwargs["global_shift"], kwargs["channel_shifts"])
        output = {}
        if kwargs["output_dir"]:
            for path in kwargs["file_paths"]:
                target = Path(kwargs["output_dir"]) / (Path(path).stem + "_shifted.ptu")
                np.savetxt(target, stream.micro_times, fmt="%d")
                output[str(path)] = str(target)
        return {
            "output_paths_by_file": output,
            "applied_shifts_by_file": applied,
            "mmfdb_artifacts": {
                "output_artifacts": {str(p): "shifted-artifact" for p in kwargs["file_paths"]}
            }
            if kwargs["mmfdb"]["enabled"]
            else {},
            "warnings": [],
        }


def load(app, path):
    path.write_bytes(b"original")
    assert app.add_paths([path])
    app.job.future.result(timeout=5)
    app.job.poll()


def test_native_preview_matches_photon_wrapping_and_named_export(tmp_path):
    client = Client()
    app = create_app(client=client)
    source = tmp_path / "source.ptu"
    load(app, source)
    app.global_shift = 1
    app.channel_shifts = {0: 2, 1: -2}
    stream = Stream()
    apply_shifts(stream, 1, app.channel_shifts)
    for channel, hist in app.histograms().items():
        np.testing.assert_array_equal(
            hist, np.bincount(stream.micro_times[stream.routing_channels == channel], minlength=8)
        )
    target = tmp_path / "renamed.ptu"
    assert app.apply(filename=target)
    app.job.future.result(timeout=5)
    app.job.poll()
    np.testing.assert_array_equal(np.loadtxt(target, dtype=int), stream.micro_times)
    assert source.read_bytes() == b"original"
    assert str(target) in app.last_result["output_paths_by_file"].values()
    state = json.loads(json.dumps(app.export_state()))
    app.restore_state(state)
    assert app.global_shift == 1 and app.channel_shifts == {0: 2, 1: -2}
    app.close()


def test_native_auto_align_rising_edges_modulo_bins(tmp_path):
    app = create_app(client=Client())
    load(app, tmp_path / "one.ptu")
    app.trigger_level = 2
    app.trigger_position = 3
    app.auto_align()
    assert app.channel_shifts == {0: 2, 1: 6}
    for histogram in app.histograms().values():
        assert histogram[3] == 2
    app.reset_shift(0)
    app.reset_shift(None)
    assert app.channel_shifts[0] == 0 and app.global_shift == 0
    app.close()


def test_native_db_context_and_no_fake_success_without_outputs(tmp_path):
    client = Client()
    app = create_app(client=client)
    load(app, tmp_path / "one.ptu")
    assert not app.apply(archive=True)
    app.sample_id = "sample-A"
    assert app.apply(archive=True)
    app.job.future.result(timeout=5)
    app.job.poll()
    assert client.request["mmfdb"] == {
        "enabled": True,
        "sample_id": "sample-A",
        "register_missing_inputs": True,
    }
    assert "Registered 1/1" in app.message
    app.close()


def test_native_drag_release_runs_alignment(monkeypatch, tmp_path):
    from emtk import im, implot
    from emtk.pil_painter import PilPainter

    app = create_app(client=Client())
    load(app, tmp_path / "one.ptu")
    real_align = app.auto_align
    aligned = []

    def align():
        aligned.append(True)
        real_align()

    monkeypatch.setattr(app, "auto_align", align)
    x = implot.DragLineResult(True, 3, False, True, True)
    y = implot.DragLineResult(True, 2, False, True, True)
    monkeypatch.setattr(implot, "drag_line_x", lambda *a, **k: x)
    monkeypatch.setattr(implot, "drag_line_y", lambda *a, **k: y)
    with im.frame(PilPainter(800, 500), (0, 0, 800, 500)):
        im.begin("hist")
        app.draw_histogram((0, 0, 800, 500))
        im.end()
    assert not aligned
    x = implot.DragLineResult(False, 3, False, False, False)
    y = implot.DragLineResult(False, 2, False, False, False)
    with im.frame(PilPainter(800, 500), (0, 0, 800, 500)):
        im.begin("hist")
        app.draw_histogram((0, 0, 800, 500))
        im.end()
    assert aligned == [True]
    app.close()


def test_native_real_ptu_shifted_output_matches_preview(tmp_path):
    import hashlib

    import pytest

    from chisurf.plugins.tttr.tttr_microtime_shifter.gui.client import MicrotimeShifterClient

    root = Path(__file__).resolve().parents[5]
    source = root / "test/data/clsm/Leica_SP5.ptu"
    if not source.is_file():
        pytest.skip("Real PTU fixture is unavailable.")
    before = hashlib.sha256(source.read_bytes()).digest()
    client = MicrotimeShifterClient(mmfdb_db_provider=lambda: None)
    app = create_app(client=client)
    assert app.load_files([source])
    app.job.future.result(timeout=30)
    app.job.poll()
    assert app.n_mt > 0 and app.raw_histograms
    app.global_shift = 2
    channel = next(iter(app.channel_shifts))
    app.channel_shifts[channel] = -1
    expected = app.histograms()
    output = tmp_path / "native_shifted.ptu"
    assert app.apply(filename=output)
    app.job.future.result(timeout=30)
    app.job.poll()
    histogram = client.histogram(output)
    for ch, counts in expected.items():
        np.testing.assert_array_equal(histogram["histograms"][str(ch)], counts)
    assert hashlib.sha256(source.read_bytes()).digest() == before
    app.close()


def test_native_real_authenticated_archive_reopens_thread_owned_db(tmp_path):
    import pytest
    from mmfdb.models import SampleDefinition
    from mmfdb.repository import MFDatabase
    from mmfdb.samples.sample_manager import create_sample
    from mmfdb.security.auth import create_session

    from chisurf.core.transform.mmfdb import session_from_auth

    root = Path(__file__).resolve().parents[5]
    source = root / "test/data/clsm/Leica_SP5.ptu"
    if not source.is_file():
        pytest.skip("Real PTU fixture is unavailable.")
    db = MFDatabase(str(tmp_path / "native-archive.db"))
    db.ensure_user("native-shift-user")
    token = create_session(db.conn, "native-shift-user")["token"]
    db.conn.commit()
    session = session_from_auth(db, {"token": token})
    db.session_context = session
    sample = create_sample(db, SampleDefinition("Native shift specimen"))
    app = create_app(mmfdb_db=db, mmfdb_session=session)
    app.files = [source]
    app.sample_id = sample
    app.global_shift = 1
    assert app.apply(archive=True)
    app.job.future.result(timeout=30)
    app.job.poll()
    artifacts = app.last_result["mmfdb_artifacts"]["output_artifacts"]
    assert artifacts[str(source.resolve())]
    assert app.last_result["output_paths_by_file"] == {}
    assert "Registered 1/1" in app.message
    assert (
        db.conn.execute(
            "SELECT COUNT(*) FROM mmfdb_artifact WHERE artifact_kind='processed_data'"
        ).fetchone()[0]
        > 0
    )
    app.close()
    app.close()
    db.close()


def test_native_pto_input_and_output_keep_photon_histograms(tmp_path):
    import pytest

    from chisurf.core.fio.pto import Measurement, is_measurement
    from chisurf.plugins.tttr.tttr_microtime_shifter.gui.client import MicrotimeShifterClient

    source = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    if not source.is_file():
        pytest.skip("Real PTU fixture is unavailable.")
    with Measurement.create(source, out_dir=tmp_path) as measurement:
        pto = measurement.path
    client = MicrotimeShifterClient(mmfdb_db_provider=lambda: None)
    app = create_app(client=client)
    assert app.load_files([pto])
    app.job.future.result(timeout=30)
    app.job.poll()
    assert app.raw_histograms and app.n_mt > 0
    app.global_shift = 1
    expected = app.histograms()
    output = tmp_path / "shifted_measurement.pto"
    assert app.apply(filename=output)
    app.job.future.result(timeout=30)
    app.job.poll()
    assert is_measurement(output)
    shifted = client.histogram(output)["histograms"]
    for channel, counts in expected.items():
        np.testing.assert_array_equal(shifted[str(channel)], counts)
    app.close()


def test_batch_same_filenames_do_not_overwrite_other_photons(tmp_path, monkeypatch):
    from chisurf.plugins.tttr.tttr_microtime_shifter.backend import services

    paths = []
    for name, content in [("a", b"first recording"), ("b", b"second recording")]:
        folder = tmp_path / name
        folder.mkdir()
        path = folder / "same.ptu"
        path.write_bytes(content)
        paths.append(str(path))

    def shift(path, output_dir=None, **kwargs):
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / "same_shifted.ptu"
        output.write_bytes(Path(path).read_bytes())
        return str(output), {0: 0}

    monkeypatch.setattr(services, "shift_file", shift)
    result = services.apply_handler(files=paths, output_dir=str(tmp_path / "out"))
    assert result["ok"]
    outputs = result["result"]["output_paths_by_file"]
    assert len(set(outputs.values())) == 2
    assert [Path(outputs[str(Path(path).resolve())]).read_bytes() for path in paths] == [
        b"first recording",
        b"second recording",
    ]


def test_native_log_toggle_updates_positive_limits_without_locking_zoom(tmp_path, monkeypatch):
    from emtk import im, implot
    from emtk.pil_painter import PilPainter

    app = create_app(client=Client())
    load(app, tmp_path / "one.ptu")
    calls = []
    original = implot.setup_axes_limits

    def limits(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(implot, "setup_axes_limits", limits)
    for log in (False, True, True):
        app.log_y = log
        with im.frame(PilPainter(800, 500), (0, 0, 800, 500)):
            im.begin("hist")
            app.draw_histogram((0, 0, 800, 500))
            im.end()
    assert calls[1][0][2] == 1
    assert calls[0][1]["cond"] == implot.COND_ALWAYS
    assert calls[1][1]["cond"] == implot.COND_ALWAYS
    assert calls[2][1]["cond"] == implot.COND_ONCE
    app.close()


def test_native_sample_reference_mutations_and_authenticated_create(tmp_path, monkeypatch):
    from mmfdb.repository import MFDatabase
    from mmfdb.samples.sample_manager import list_samples
    from mmfdb.security.auth import create_session

    from chisurf.core.transform.mmfdb import session_from_auth

    db = MFDatabase(str(tmp_path / "samples.db"))
    db.ensure_user("native-sample-user")
    token = create_session(db.conn, "native-sample-user")["token"]
    db.conn.commit()
    session = session_from_auth(db, {"token": token})
    app = create_app(mmfdb_db=db, mmfdb_session=session)
    app.sample_definition = json.dumps(
        {
            "name": "Native specimen",
            "entities": [
                {
                    "name": "Protein",
                    "entity_type": "protein",
                    "sequence": "AC",
                    "uniprot_accession": "TEST",
                }
            ],
        }
    )
    monkeypatch.setattr(
        "mmfdb.samples.external_refs.fetch_uniprot",
        lambda accession: {"sequence": "AA", "organism": "Test organism"},
    )
    app.fetch_sample_reference()
    app.job.future.result(timeout=5)
    app.job.poll()
    app.diff_sample_reference()
    definition = json.loads(app.sample_definition)
    assert definition["entities"][0]["reference_sequence"] == "AA"
    assert len(definition["entities"][0]["mutations"]) == 1
    app.create_sample()
    app.job.future.result(timeout=5)
    app.job.poll()
    assert app.sample_id and app.sample_definition is None
    assert any(row.get("name") == "Native specimen" for row in list_samples(db))
    app.close()
    db.close()


def test_native_preferences_reload_inputs_and_keep_shift_controls(tmp_path):
    client = Client()
    app = create_app(client=client)
    load(app, tmp_path / "one.ptu")
    app.global_shift = 2
    app.channel_shifts = {0: -1, 1: 3}
    app.trigger_position = 4
    app.log_y = True
    app.sample_id = "do-not-persist-artifact-context"
    state = app.export_settings()
    assert "histograms" not in state and "sample_id" not in state and "last_result" not in state
    restored = create_app(client=client)
    restored.restore_settings(json.loads(json.dumps(state)))
    restored.job.future.result(timeout=5)
    restored.job.poll()
    assert restored.global_shift == 2 and restored.channel_shifts == {0: -1, 1: 3}
    assert restored.trigger_position == 4 and restored.log_y
    app.close()
    restored.close()

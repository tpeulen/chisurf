"""A batch search runs its files in parallel and gives exactly the sequential result.

Each file is searched and stored in its own process; the results are merged in file order, so
what the GUI and the containers see does not depend on which worker finished first.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from chisurf.plugins.burst.burst_selection.api import selection
from chisurf.plugins.burst.burst_selection.api.models import AnalysisRequest
from chisurf.plugins.burst.burst_selection.tests.test_real_data import (
    BH_SPC_FILE,
    real_data_settings,
)


def _batch(tmp_path: Path, name: str) -> tuple[AnalysisRequest, list[str]]:
    folder = tmp_path / name
    folder.mkdir()
    files = []
    for stem in ("a", "b", "c"):
        target = folder / f"{stem}.spc"
        shutil.copy(BH_SPC_FILE, target)
        files.append(str(target))
    settings = real_data_settings()
    settings.output_formats = ["pto"]
    out = folder / "analysis"
    request = AnalysisRequest(
        files=files,
        settings=settings,
        output_dir=str(out),
        container_dirs={f: str(out) for f in files},
    )
    return request, files


def test_parallel_and_sequential_batches_agree(tmp_path, monkeypatch):
    monkeypatch.setattr(selection, "MIN_PARALLEL_BYTES", 0)
    serial_request, serial_files = _batch(tmp_path, "serial")
    monkeypatch.setenv("CHISURF_BURST_WORKERS", "1")
    assert selection._search_workers(serial_request, None) == 1
    serial = selection.analyze_request(serial_request)

    parallel_request, parallel_files = _batch(tmp_path, "parallel")
    monkeypatch.delenv("CHISURF_BURST_WORKERS")
    assert selection._search_workers(parallel_request, None) > 1
    progress: list[int] = []
    parallel = selection.analyze_request(
        parallel_request, progress_callback=lambda done, total, path: progress.append(done)
    )

    assert progress == [1, 2, 3]
    def by_name(meta):  # the per-file ALEX phase is keyed by each batch's own paths
        return {**meta, "alex_phase_by_file": {
            Path(k).name: v for k, v in meta["alex_phase_by_file"].items()}}

    assert by_name(parallel.metadata) == by_name(serial.metadata)
    for s, p in zip(serial_files, parallel_files):
        assert parallel.dataframes[p] == serial.dataframes[s]
        assert Path(parallel.output_paths_by_file[p]["output_folder"]).name == Path(
            serial.output_paths_by_file[s]["output_folder"]
        ).name
        assert Path(parallel.output_paths_by_file[p]["pto"]).is_file()


def test_small_files_and_shared_containers_stay_sequential(tmp_path):
    request, files = _batch(tmp_path, "small")
    assert selection._search_workers(request, None) == 1  # 1 MB files: a worker start costs more
    request.container_dirs = {}
    request.output_dir = None
    assert selection._search_workers(request, Path(tmp_path)) == 1  # the legacy folder appends

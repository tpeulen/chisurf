"""The burst pipeline benchmark runs end to end (slow, heavy: on the big machine only).

Needs ``CHISURF_BENCH_DATA`` (a folder with DNA13bp_3.ptu and the two reference dyes) and
``CHISURF_BENCH_SETTINGS`` (a settings folder holding the RVZMT150 setup); skipped otherwise.
The numbers it writes are what ``okf/plugins/burst.md`` ("Pipeline wall time") records."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


def test_the_benchmark_writes_every_step_and_frame_time(tmp_path):
    data, settings = os.environ.get("CHISURF_BENCH_DATA"), os.environ.get("CHISURF_BENCH_SETTINGS")
    if not (data and settings and (Path(data) / "DNA13bp_3.ptu").is_file()):
        pytest.skip("set CHISURF_BENCH_DATA and CHISURF_BENCH_SETTINGS to run the benchmark")
    from build_tools.dev_utils import burst_pipeline_bench as bench

    result = bench.gui(tmp_path / "gui", Path(settings), Path(data))
    assert [name for name, _t in result["marks"]][-1] == "mle fit"
    assert {"data", "mle", "mle:inspect"} <= set(result["frames_ms"])
    rows = bench.stages(tmp_path / "stages", Path(settings), Path(data), tmp_path / "gui" / "recipe.json")
    assert any(name.startswith("raw: fit2x fit_many") for name, _t in rows)
    bench.figure(tmp_path / "gui" / "timing.json", tmp_path / "gui" / "timing.json", tmp_path / "f.png")
    assert (tmp_path / "f.png").stat().st_size > 0
    json.loads((tmp_path / "stages" / "stages.json").read_text())

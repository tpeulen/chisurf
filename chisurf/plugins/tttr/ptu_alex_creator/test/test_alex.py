"""Tests for the ALEX Creator plugin (core / api / cli / gui split + batch)."""

from __future__ import annotations

import pathlib
import shutil

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
_PTU = _REPO_ROOT / "test" / "data" / "clsm" / "Leica_SP5.ptu"


def test_view_model_defaults_and_options():
    from chisurf.plugins.tttr.ptu_alex_creator.gui.view_model import AlexViewModel

    m = AlexViewModel()
    assert m.input_format == "Auto"
    assert m.output_format == "PTU"
    assert m.alex_period == 8000
    assert m.input_format_options()[0] == "Auto"
    assert "PTU" in m.output_format_options()
    assert m.can_save() is not None  # nothing loaded
    assert m.can_run_batch() is not None  # no batch files


def test_view_spec_loads():
    from chisurf.plugins.tttr.ptu_alex_creator.gui.view_model import AlexViewModel

    assert AlexViewModel().view_spec() is not None


def test_manifest_and_cli_and_rpc():
    from pathlib import Path

    from chisurf.core.plugin import load_manifest
    from chisurf.plugins.tttr.ptu_alex_creator.backend.services import list_methods
    from chisurf.plugins.tttr.ptu_alex_creator.cli.main import cli

    m = load_manifest(Path(__file__).resolve().parents[1] / "manifest.json")
    assert m is not None
    assert m.entrypoints.emtk and m.entrypoints.cli and m.entrypoints.services
    assert len(m.rpc_methods) == 4
    assert set(cli.commands) == {"convert", "merge"}
    assert "alex.convert" in list_methods() and "alex.merge" in list_methods()


@pytest.mark.skipif(not _PTU.exists(), reason="sample PTU not available")
def test_core_convert_and_histogram(tmp_path):
    import tttrlib

    from chisurf.plugins.tttr.ptu_alex_creator import core

    n = len(tttrlib.TTTR(str(_PTU)))
    out = tmp_path / "single_alex.ptu"
    core.convert_file(str(_PTU), str(out), 8000, 0, "PTU", "Auto")
    assert out.exists() and len(tttrlib.TTTR(str(out))) == n

    hist = core.alex_histogram(str(_PTU), 4000, 0, core.resolve_filetype("Auto", str(_PTU)))
    assert len(hist) == 4000 and int(hist.sum()) == n


@pytest.mark.skipif(not _PTU.exists(), reason="sample PTU not available")
def test_api_batch_convert_and_merge(tmp_path):
    import tttrlib

    from chisurf.plugins.tttr.ptu_alex_creator.api import AlexRequest, run

    n = len(tttrlib.TTTR(str(_PTU)))
    f1 = tmp_path / "a.ptu"
    f2 = tmp_path / "b.ptu"
    shutil.copy(_PTU, f1)
    shutil.copy(_PTU, f2)

    conv = run(
        AlexRequest(
            files=[str(f1), str(f2)],
            output_format="PTU",
            mode="convert",
            output_dir=str(tmp_path / "out"),
        )
    )
    assert len(conv.output_paths) == 2
    assert all(pathlib.Path(p).exists() for p in conv.output_paths)

    merged = run(
        AlexRequest(
            files=[str(f1), str(f2)],
            output_format="PTU",
            mode="merge",
            output_path=str(tmp_path / "m.ptu"),
        )
    )
    assert len(merged.output_paths) == 1
    # merge concatenates every photon from both files
    assert len(tttrlib.TTTR(merged.output_paths[0])) == 2 * n


def test_view_model_offers_the_pto_container_output():
    """PTO is an output choice like the TTTR containers: one converter, both worlds."""
    from chisurf.plugins.tttr.ptu_alex_creator.gui.view_model import AlexViewModel

    options = AlexViewModel().output_format_options()
    assert "PTU" in options and "PTO" in options


@pytest.mark.skipif(not _PTU.exists(), reason="sample PTU not available")
def test_pto_output_packs_one_container_of_every_source(tmp_path):
    """Output "PTO": every input folded, packed into one .pto beside the source."""
    import shutil

    import tttrlib

    from chisurf.plugins.tttr.ptu_alex_creator.api import AlexRequest, run

    n = len(tttrlib.TTTR(str(_PTU)))
    f1 = tmp_path / "a.ptu"
    f2 = tmp_path / "b.ptu"
    shutil.copy(_PTU, f1)
    shutil.copy(_PTU, f2)

    result = run(
        AlexRequest(
            files=[str(f1), str(f2)],
            alex_period=8000,
            period_shift=0,
            output_format="PTO",
            output_dir=str(tmp_path / "out"),
        )
    )
    assert len(result.output_paths) == 1, "one container for the whole list"
    container = pathlib.Path(result.output_paths[0])
    assert container.suffix == ".pto" and container.exists()
    assert len(tttrlib.TTTR(str(container))) == 2 * n, "every photon of both sources"

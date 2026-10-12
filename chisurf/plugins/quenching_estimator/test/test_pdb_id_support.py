from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

import click
import pytest



import importlib

cli = importlib.import_module('chisurf.plugins.quenching_estimator.cli.cli')
from chisurf.plugins.quenching_estimator.core.structure import download_pdb_id, is_pdb_id, resolve_structure_path

AMINO_ACIDS = [
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
]


def _aa_interactions(**overrides: dict[str, float]) -> dict[str, dict[str, float]]:
    interactions = {aa: {"slow_factor": 1.0, "kQ": 0.0} for aa in AMINO_ACIDS}
    for aa, values in overrides.items():
        interactions[aa].update(values)
    return interactions


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._content


def _minimal_project(pdb_source: str) -> dict:
    return {
        "pdb": pdb_source,
        "tau0": 4.2,
        "n_photons": 1000,
        "t_max": 200.0,
        "t_step": 0.02,
        "dg": 0.5,
        "critical_distance": 6.5,
        "av_parameter": {"linker_length": 21.5, "linker_width": 0.5, "radius1": 3.5},
        "amino_acid_interactions": _aa_interactions(TYR={"slow_factor": 0.1, "kQ": 2.0}),
        "fret": {"enabled": False, "dyes": [{"D": 7.0}]},
    }


def test_download_pdb_id_caches_rcsb_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_urlopen(url: str, timeout: int) -> _FakeResponse:
        calls.append(url)
        assert timeout == 30
        return _FakeResponse(b"ATOM      1  N   ALA A   1       0.000   0.000   0.000\n")

    # These cover the plugin's own fetch; the real call delegates to ChiSurf's
    # shared implementation, which this monkeypatched urlopen would never see.
    monkeypatch.setattr("chisurf.plugins.quenching_estimator.core.structure.fetch._shared_downloader", lambda: None)
    monkeypatch.setattr("chisurf.plugins.quenching_estimator.core.structure.fetch.urllib.request.urlopen", fake_urlopen)

    path = download_pdb_id("148l", cache_dir=tmp_path)

    assert path == tmp_path / "148l.pdb"
    assert path.read_text(encoding="utf8").startswith("ATOM")
    assert calls == ["https://files.rcsb.org/download/148L.pdb"]
    assert download_pdb_id("148L", cache_dir=tmp_path) == path
    assert len(calls) == 1


def test_download_pdb_id_falls_back_to_cif(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_urlopen(url: str, timeout: int) -> _FakeResponse:
        calls.append(url)
        if url.endswith(".pdb"):
            raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
        return _FakeResponse(b"data_1ABC\n#\n")

    # These cover the plugin's own fetch; the real call delegates to ChiSurf's
    # shared implementation, which this monkeypatched urlopen would never see.
    monkeypatch.setattr("chisurf.plugins.quenching_estimator.core.structure.fetch._shared_downloader", lambda: None)
    monkeypatch.setattr("chisurf.plugins.quenching_estimator.core.structure.fetch.urllib.request.urlopen", fake_urlopen)

    path = download_pdb_id("1abc", cache_dir=tmp_path)

    assert path == tmp_path / "1abc.cif"
    assert path.read_text(encoding="utf8").startswith("data_1ABC")
    assert calls == [
        "https://files.rcsb.org/download/1ABC.pdb",
        "https://files.rcsb.org/download/1ABC.cif",
    ]


def test_resolve_structure_path_accepts_files_and_pdb_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    local = tmp_path / "local.pdb"
    local.write_text("ATOM\n", encoding="utf8")
    monkeypatch.setattr("chisurf.plugins.quenching_estimator.core.structure.fetch.download_pdb_id", lambda pdb_id, cache_dir=None: tmp_path / f"{pdb_id.lower()}.pdb")

    assert resolve_structure_path(local) == local
    assert resolve_structure_path("1abc") == tmp_path / "1abc.pdb"
    assert is_pdb_id("1abc")
    assert not is_pdb_id("local.pdb")


def test_cli_validation_accepts_pdb_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cached = tmp_path / "148l.pdb"
    cached.write_text("ATOM\n", encoding="utf8")
    monkeypatch.setattr(cli, "resolve_structure_path", lambda source: cached)

    cli._validate_project(_minimal_project("148l"))

    monkeypatch.setattr(cli, "resolve_structure_path", lambda source: (_ for _ in ()).throw(FileNotFoundError("missing")))
    with pytest.raises(click.ClickException):
        cli._validate_project(_minimal_project("missing.pdb"))

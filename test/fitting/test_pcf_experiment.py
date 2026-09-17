"""Headless registration + data-path test for the PCF experiment type."""

from __future__ import annotations

import numpy as np


def test_pcf_registered_in_experiment_types():
    """The pcf experiment type is registered with display name 'PCF'."""
    from chisurf.core.experiments import load_experiment_types

    types = load_experiment_types()
    assert "pcf" in types
    assert types["pcf"].name == "PCF"


def test_pcf_config_block_present():
    """The packaged config carries a pcf block with a reader and the PCF model."""
    import pathlib

    import yaml

    import chisurf as cs

    cfg = yaml.safe_load(
        (
            pathlib.Path(cs.__file__).parent / "core" / "settings" / "experiment_configs.yaml"
        ).read_text()
    )
    assert "pcf" in cfg
    readers = cfg["pcf"]["readers"]
    assert readers[0]["reader_class"] == "chisurf.core.experiments.fcs.FCS"
    assert readers[0]["reader_params"]["experiment_reader"] == "csv"
    assert "chisurf.core.models.pcf.parse.ParsePCFModel" in cfg["pcf"]["models"]


def test_pcf_reader_loads_csv_curve(tmp_path):
    """The reused CSV reader parses a plain x/y PCF table into a DataCurve."""
    from chisurf.core.experiments.fcs import FCS

    x = np.logspace(-4, 0, 40)
    y = np.exp(-((np.log(x / 0.02 * 1000)) ** 2) / 2.0)  # a log-Gaussian-ish shape
    ey = 0.02 * np.ones_like(y)  # the CSV curve reader expects an error column
    path = tmp_path / "pcf.csv"
    np.savetxt(path, np.column_stack([x, y, ey]), delimiter=",")

    reader = FCS(name="PCF-CSV", experiment_reader="csv")
    group = reader.read(filename=str(path))
    curve = group[0]
    assert curve.y.size == x.size
    assert np.allclose(curve.x, x, rtol=1e-6)


def test_pcf_core_model_catalogue_importable():
    """The PCF core model catalogue is importable and lists the 3 distributions."""
    import pathlib

    import yaml

    import chisurf as cs
    from chisurf.core.models.pcf import ParsePCFModel  # noqa: F401 — import smoke

    cat = yaml.safe_load(
        (pathlib.Path(cs.__file__).parent / "core" / "models" / "pcf" / "models.yaml").read_text()
    )
    assert set(cat) == {"PCF Log-Normal", "PCF Log-Gaussian", "PCF Gamma"}

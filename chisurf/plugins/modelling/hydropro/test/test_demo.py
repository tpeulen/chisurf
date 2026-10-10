"""The shipped sphere demo has a known answer: Stokes-Einstein for the radius that was built."""

from __future__ import annotations

import pytest

from chisurf.plugins.modelling.hydropro.core import HydroProSettings, run_hydro
from chisurf.plugins.modelling.hydropro.demo import expected_diffusion, make_demo, standin_path


def test_demo_is_cached_and_regenerated_on_damage(tmp_path):
    pdb = make_demo(tmp_path)
    stamp = pdb.stat().st_mtime_ns
    assert make_demo(tmp_path) == pdb and pdb.stat().st_mtime_ns == stamp
    pdb.write_text("damaged")
    make_demo(tmp_path)
    assert pdb.read_text().startswith("ATOM")


@pytest.mark.parametrize("t, eta", [(20.0, 0.01), (37.0, 0.0069)])
def test_demo_run_recovers_the_stokes_einstein_diffusion(tmp_path, t, eta):
    pdb = make_demo(tmp_path / "demo")
    settings = HydroProSettings(t=t, eta=eta)
    (result,) = run_hydro([pdb], settings, standin_path(pdb.parent), tmp_path / "work")
    assert result.diffusion_coefficient == pytest.approx(expected_diffusion(t, eta), rel=0.03)


def test_load_example_fills_the_window_model(tmp_path):
    from chisurf.plugins.modelling.hydropro.gui.model import HydroProModel

    model = HydroProModel(work_dir=tmp_path / "work")
    model.example_folder = tmp_path / "demo"
    model.load_example()
    model.run()
    assert model.wait()
    assert float(model.cells[str(model.struct_list()[0])]) == pytest.approx(
        expected_diffusion(), rel=0.03
    )

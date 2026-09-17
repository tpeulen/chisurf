import pathlib
import unittest

import utils

TOPDIR = pathlib.Path(__file__).parent.parent

utils.set_search_paths(TOPDIR)

import chisurf.core.experiments
import chisurf.core.fitting.fit
from chisurf.core.models.description import for_family


class FitTests(unittest.TestCase):
    """A donor-only and a donor-acceptor decay of the IBH sample, fitted with a
    shared donor lifetime: the described lifetime and Gaussian FRET models.
    """

    def test_data_group(self):
        dt = 0.0141
        tcspc_experiment = chisurf.core.experiments.core.Experiment(name="TCSPC")
        tcspc_reader = chisurf.core.experiments.tcspc.TCSPCReader(
            is_vv_vh=False, skiprows=10, dt=dt, experiment=tcspc_experiment
        )
        irf = tcspc_reader.read(filename="./test/data/tcspc/ibh_sample/Prompt.txt")
        decay_dd_d0 = tcspc_reader.read(filename="./test/data/tcspc/ibh_sample/Decay_577D.txt")
        decay_dd_da = tcspc_reader.read(
            filename="./test/data/tcspc/ibh_sample/Decay_577D+577A+GTPgS.txt"
        )

        fit_d0 = chisurf.core.fitting.fit.FitGroup(
            data=decay_dd_d0, model_class=for_family("tcspc_lifetime")
        )
        model_d0 = fit_d0.model
        model_d0.set_dataset("response", irf[0])
        self.assertIsNotNone(model_d0.problem, model_d0.missing)
        model_d0.structure = "lifetime.components.2"
        fit_d0.fit_range = 0, 2000
        chi2_d0_before_fit = fit_d0.chi2
        fit_d0.run()
        self.assertLess(fit_d0.chi2, chi2_d0_before_fit)

        fit_da = chisurf.core.fitting.fit.FitGroup(
            data=decay_dd_da, model_class=for_family("tcspc_fret_gaussian")
        )
        model_da = fit_da.model
        model_da.set_dataset("response", irf[0])
        self.assertIsNotNone(model_da.problem, model_da.missing)
        by_id = {p.canonical_id: p for p in model_da.parameters_all}
        d0 = {p.canonical_id: p for p in model_d0.parameters_all}
        by_id["distance.mean.0"].value = 50.0
        by_id["distance.sigma.0"].value = 6.0
        by_id["donor.tau.0"].link = d0["lifetime.tau.0"]
        fit_da.fit_range = 0, 2000
        chi2_da_before_fit = fit_da.chi2
        fit_da.run()
        self.assertLess(fit_da.chi2, chi2_da_before_fit)
        self.assertAlmostEqual(by_id["donor.tau.0"].value, d0["lifetime.tau.0"].value)


if __name__ == "__main__":
    unittest.main()

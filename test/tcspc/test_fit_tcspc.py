import utils
import unittest
import pathlib

TOPDIR = pathlib.Path(__file__).parent.parent

utils.set_search_paths(TOPDIR)

import chisurf.core.experiments
import chisurf.core.models.tcspc.lifetime
import chisurf.core.models.tcspc.fret
import chisurf.core.fitting.fit


class FitTests(unittest.TestCase):

    def test_data_group(self):
        dt = 0.0141
        tcspc_experiment = chisurf.core.experiments.core.Experiment(
            name='TCSPC'
        )
        tcspc_reader = chisurf.core.experiments.tcspc.TCSPCReader(
            is_vv_vh=False,
            skiprows=10,
            dt=dt,
            experiment=tcspc_experiment
        )
        irf = tcspc_reader.read(
            filename='./test/data/tcspc/ibh_sample/Prompt.txt'
        )

        # model_decay of the donor in the absence of FRET
        decay_dd_d0 = tcspc_reader.read(
            filename='./test/data/tcspc/ibh_sample/Decay_577D.txt'
        )
        # model_decay of the donor in the presence of FRET
        decay_dd_da = tcspc_reader.read(
            filename='./test/data/tcspc/ibh_sample/Decay_577D+577A+GTPgS.txt'
        )

        fit_d0 = chisurf.core.fitting.fit.FitGroup(
            data=decay_dd_d0,
            model_class=chisurf.core.models.tcspc.lifetime.LifetimeModel
        )

        model_d0 = fit_d0.model

        # add a lifetime
        model_d0.lifetimes.append()
        model_d0.convolve._irf = irf[0]
        model_d0.update()

        fit_d0.model.find_parameters()

        self.assertSetEqual(
            set(fit_d0.model.parameter_names),
            {'bg', 'sc', 'ts', 'tL1', 'tL2', 'xL2'}
        )
        self.assertTupleEqual(
            fit_d0.fit_range,
            (0, 0)
        )
        fit_d0.fit_range = 0, 2000
        chi2_d0_before_fit = fit_d0.chi2
        fit_d0.run()
        chi2_d0_after_fit = fit_d0.chi2
        self.assertEqual(
            chi2_d0_after_fit < chi2_d0_before_fit,
            True
        )

        fit_da = chisurf.core.fitting.fit.FitGroup(
            data=decay_dd_da,
            model_class=chisurf.core.models.tcspc.fret.GaussianModel
        )
        model_da = fit_da.model

        # The model seeds one distance itself (a zero-component distribution has
        # nothing to convolve), so define the ensemble rather than appending onto
        # whatever it started with -- appending blindly gave two components.
        model_da.gaussians.clear()
        model_da.append(
            mean=50,
            sigma=6,
            species_fraction=1.0
        )
        model_da.find_parameters()

        self.assertSetEqual(
            set(model_da.parameter_names),
            {
                'E_FRET',
                'R(G,1)',
                'bg',
                'x(G,1)',
                'xDOnly',
                'tL1',
                'sc',
                'ts'
            }
        )
        model_da.parameter_dict['tL1'].link = model_d0.parameter_dict['tL1']
        fit_da.fit_range = 0, 2000

        chi2_da_before_fit = fit_da.chi2
        fit_da.run()
        chi2_da_after_fit = fit_da.chi2
        self.assertEqual(
            chi2_da_after_fit < chi2_da_before_fit,
            True
        )

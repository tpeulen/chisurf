import glob
import unittest

import numpy as np
import scipy.stats

import chisurf.core.fio
import chisurf.core.fio.fluorescence
import chisurf.core.fluorescence
import chisurf.core.fluorescence.anisotropy
import chisurf.core.fluorescence.fcs
import chisurf.core.fluorescence.fret
import chisurf.core.fluorescence.general
import chisurf.core.fluorescence.tcspc
from chisurf.core.fluorescence.anisotropy.decay import calculcate_spectrum
from chisurf.core.fluorescence.tcspc.corrections import compute_linearization_table


class Tests(unittest.TestCase):
    """Tests for the fluorescence primitives: anisotropy, FCS, FRET and TCSPC."""

    @staticmethod
    def _decay_from_spectrum(
            spectrum: np.ndarray,
            time_axis: np.ndarray
    ) -> np.ndarray:
        """Evaluate an interleaved (amplitude, lifetime) spectrum on a time axis.

        Parameters
        ----------
        spectrum : numpy.ndarray
            Interleaved amplitudes and lifetimes.
        time_axis : numpy.ndarray
            Time axis the decay is evaluated on.

        Returns
        -------
        numpy.ndarray
            The un-normalised decay ``sum_i a_i * exp(-t / tau_i)``.
        """
        decay = np.zeros_like(time_axis)
        for amplitude, lifetime in zip(spectrum[0::2], spectrum[1::2]):
            decay += amplitude * np.exp(-time_axis / lifetime)
        return decay

    def test_fluorescence_anisotropy_decay_calculcate_spectrum(self):
        """The joint spectrum must reproduce the polarized decays it stands for.

        The reference is derived from the definitions rather than re-recorded
        from the implementation: with ``r(t)`` the anisotropy and
        ``G = S_par / S_perp`` the detection-sensitivity ratio,

            f_VV(t)   = f_VM(t) * (1 + 2 r(t))
            f_VH(t)   = f_VM(t) * (1 - r(t)) / G
            f_VV,m(t) = (1 - l1) f_VV(t) + l1 f_VH(t)
            f_VH,m(t) = l2 f_VV(t) + (1 - l2) f_VH(t)

        ``G`` divides the whole VH channel because it is the parallel/
        perpendicular sensitivity ratio, so the perpendicular channel records
        ``1/G`` of what an equally sensitive one would. That placement is what
        makes the pair invertible — see
        :meth:`test_calculcate_spectrum_recovers_anisotropy`.
        """
        tau, rho, r0 = 4.0, 1.0, 1.0
        lifetime_spectrum = np.array([1.0, tau])
        anisotropy_spectrum = np.array([r0, rho])
        g_factor = 1.5
        times = np.linspace(0.0, 20.0, 64)

        vm = np.exp(-times / tau)
        rt = r0 * np.exp(-times / rho)
        vv = vm * (1.0 + 2.0 * rt)
        vh = vm * (1.0 - rt) / g_factor

        for l1, l2 in [(0.0, 0.0), (0.1, 0.0), (0.0, 0.1), (0.1, 0.2)]:
            kwargs = dict(
                lifetime_spectrum=lifetime_spectrum,
                anisotropy_spectrum=anisotropy_spectrum,
                g_factor=g_factor,
                l1=l1,
                l2=l2
            )
            vv_spectrum = calculcate_spectrum(polarization_type='VV', **kwargs)
            vh_spectrum = calculcate_spectrum(polarization_type='VH', **kwargs)
            self.assertEqual(
                np.allclose(
                    self._decay_from_spectrum(vv_spectrum, times),
                    (1.0 - l1) * vv + l1 * vh
                ),
                True,
                msg=f"VV decay wrong for l1={l1}, l2={l2}"
            )
            self.assertEqual(
                np.allclose(
                    self._decay_from_spectrum(vh_spectrum, times),
                    l2 * vv + (1.0 - l2) * vh
                ),
                True,
                msg=f"VH decay wrong for l1={l1}, l2={l2}"
            )
            # 'VV/VH' is the two channels stacked for joint fitting, nothing else.
            self.assertEqual(
                np.allclose(
                    calculcate_spectrum(polarization_type='VV/VH', **kwargs),
                    np.hstack([vv_spectrum, vh_spectrum])
                ),
                True
            )

        # The lifetime spectrum is passed through untouched for magic angle.
        self.assertEqual(
            np.allclose(
                calculcate_spectrum(
                    lifetime_spectrum=lifetime_spectrum,
                    anisotropy_spectrum=anisotropy_spectrum,
                    polarization_type='AAA',
                    g_factor=g_factor,
                    l1=0.0,
                    l2=0.1
                ),
                lifetime_spectrum
            ),
            True
        )

    def test_calculcate_spectrum_recovers_anisotropy(self):
        """Undoing G on the VH channel must return the anisotropy that went in.

        ``r = (I_VV - G I_VH) / (I_VV + 2 G I_VH)`` is the definition of the
        anisotropy, so with no channel mixing the generated pair has to invert
        back to ``r(t)`` exactly. This is what pins the ``G`` placement: a VH
        model that *multiplies* by ``G`` instead of dividing — as this function
        did until RF-953 — inverts ``r0 = 0.38`` back to 0.08 at ``G = 1.5``,
        and to a negative anisotropy above ``G = 2``.
        """
        tau, rho, r0 = 4.0, 1.5, 0.38
        lifetime_spectrum = np.array([1.0, tau])
        anisotropy_spectrum = np.array([r0, rho])
        times = np.linspace(0.0, 20.0, 64)
        rt = r0 * np.exp(-times / rho)

        for g_factor in [0.8, 1.0, 1.5, 2.2]:
            kwargs = dict(
                lifetime_spectrum=lifetime_spectrum,
                anisotropy_spectrum=anisotropy_spectrum,
                g_factor=g_factor,
                l1=0.0,
                l2=0.0
            )
            vv = self._decay_from_spectrum(
                calculcate_spectrum(polarization_type='VV', **kwargs), times
            )
            vh = self._decay_from_spectrum(
                calculcate_spectrum(polarization_type='VH', **kwargs), times
            )
            gs = g_factor * vh
            self.assertEqual(
                np.allclose((vv - gs) / (vv + 2.0 * gs), rt),
                True,
                msg=f"anisotropy not recovered for g={g_factor}"
            )

    def test_vm_vv_vh(self):
        times = np.linspace(0, 50, 32)
        lifetime_spectrum = np.array([1., 4], dtype=float)
        times, vm = chisurf.core.fluorescence.general.calculate_fluorescence_decay(
            lifetime_spectrum=lifetime_spectrum,
            time_axis=times
        )
        anisotropy_spectrum = np.array([0.1, 0.6, 0.38 - 0.1, 10.0])
        vv, vh = chisurf.core.fluorescence.anisotropy.decay.vm_rt_to_vv_vh(
            times,
            vm,
            anisotropy_spectrum
        )
        # Reference computed analytically, independent of the implementation:
        # every (beta_i, rho_i) pair of the interleaved rotation spectrum
        # contributes, so r(0) = sum(beta_i) = r0 = 0.38.
        rt_ref = (
            0.1 * np.exp(-times / 0.6) + (0.38 - 0.1) * np.exp(-times / 10.0)
        )
        vv_ref = vm * (1. + 2. * rt_ref)
        vh_ref = vm * (1. - rt_ref)
        self.assertAlmostEqual(float(rt_ref[0]), 0.38)
        self.assertEqual(
            np.allclose(
                vv_ref,
                vv
            ),
            True
        )
        self.assertEqual(
            np.allclose(
                vh_ref,
                vh
            ),
            True
        )

    def test_vm_rt_to_vv_vh_recovers_anisotropy(self):
        """The time-domain helper must place G exactly where its sibling does.

        ``G = S_par / S_perp`` is the parallel/perpendicular sensitivity ratio,
        so the perpendicular channel records ``1/G`` of what an equally
        sensitive one would: ``f_VH = f_VM * (1 - (1 - 3 l2) r) / G``. Undoing
        it with the Schaffer correction the rest of the stack applies,

            r = (f_VV - G f_VH) / ((1 - 3 l2) f_VV + (2 - 3 l1) G f_VH)

        has to return the anisotropy that went in for any ``G, l1, l2``, and at
        ``l1 = l2 = 0`` the decays have to agree term for term with the
        spectrum-domain :func:`calculcate_spectrum` that the fitting models
        call — the assertion RF-953 failed, where the two forward models sat a
        factor ``g**2`` apart in VH.
        """
        tau, rho, r0 = 4.0, 1.5, 0.38
        lifetime_spectrum = np.array([1.0, tau])
        anisotropy_spectrum = np.array([r0, rho])
        times = np.linspace(0.0, 20.0, 64)
        rt = r0 * np.exp(-times / rho)
        vm = np.exp(-times / tau)

        for l1, l2 in [(0.0, 0.0), (0.05, 0.03), (0.1, 0.05)]:
            for g_factor in [0.8, 1.0, 1.5, 2.2]:
                vv, vh = chisurf.core.fluorescence.anisotropy.decay.vm_rt_to_vv_vh(
                    times, vm, anisotropy_spectrum, g_factor, l1, l2
                )
                gs = g_factor * vh
                self.assertEqual(
                    np.allclose(
                        (vv - gs) / ((1.0 - 3.0 * l2) * vv + (2.0 - 3.0 * l1) * gs),
                        rt
                    ),
                    True,
                    msg=f"anisotropy not recovered for g={g_factor}, l1={l1}, l2={l2}"
                )

        # The spectrum-domain sibling still mixes l1/l2 with the Koshioka 2x2
        # matrix (RF-954), so the two forward models are only comparable where
        # that parameterisation does not enter.
        for g_factor in [0.8, 1.0, 1.5, 2.2]:
            vv, vh = chisurf.core.fluorescence.anisotropy.decay.vm_rt_to_vv_vh(
                times,
                vm,
                anisotropy_spectrum,
                g_factor=g_factor
            )
            kwargs = dict(
                lifetime_spectrum=lifetime_spectrum,
                anisotropy_spectrum=anisotropy_spectrum,
                g_factor=g_factor,
                l1=0.0,
                l2=0.0
            )
            self.assertEqual(
                np.allclose(
                    self._decay_from_spectrum(
                        calculcate_spectrum(polarization_type='VV', **kwargs), times
                    ),
                    vv
                ),
                True,
                msg=f"VV disagrees with calculcate_spectrum for g={g_factor}"
            )
            self.assertEqual(
                np.allclose(
                    self._decay_from_spectrum(
                        calculcate_spectrum(polarization_type='VH', **kwargs), times
                    ),
                    vh
                ),
                True,
                msg=f"VH disagrees with calculcate_spectrum for g={g_factor}"
            )

    def test_fcs(self):
        directory = './test/data/tttr/BH/132/'
        spc_files = glob.glob(directory + '/BH_SPC132.spc')
        photons = chisurf.core.fio.fluorescence.photons.Photons(spc_files, reading_routine="bh132")
        cr_filter = np.ones_like(photons.macro_times, dtype=float)
        w1 = np.ones_like(photons.macro_times, dtype=float)
        w2 = np.ones_like(photons.macro_times, dtype=float)
        points_per_decade = 5
        number_of_decades = 10
        results = chisurf.core.fluorescence.fcs.correlate.log_corr(
            macro_times=photons.macro_times,
            tac_channels=photons.micro_times,
            rout=photons.routing_channels,
            cr_filter=cr_filter,
            weights_1=w1,
            weights_2=w2,
            B=points_per_decade,
            nc=number_of_decades,
            fine=False,
            number_of_tac_channels=photons.n_tac
        )
        np_1 = results['number_of_photons_ch1']
        np_2 = results['number_of_photons_ch2']
        dt_1 = results['measurement_time_ch1']
        dt_2 = results['measurement_time_ch2']
        tau = results['correlation_time_axis']
        corr = results['correlation_amplitude']

        # Every photon enters both channels, so this is an autocorrelation.
        self.assertEqual(np_1, photons.nPh)
        self.assertEqual(np_2, photons.nPh)
        self.assertEqual(dt_1, dt_2)
        self.assertGreater(dt_1, 0)

        # Multi-tau: points_per_decade lags per coarsening step, nc steps.
        self.assertEqual(len(tau), points_per_decade * number_of_decades)
        self.assertEqual(len(corr), len(tau))
        self.assertEqual(tau[0], 0)
        self.assertEqual(np.all(np.diff(tau.astype(np.float64)) > 0), True)

        raw = corr.copy()
        cr = chisurf.core.fluorescence.fcs.correlate.normalize(
            np_1, np_2, dt_1, dt_2, tau, corr, points_per_decade
        )
        # ``normalize`` rescales ``corr`` in place and returns the smaller of
        # the two count rates.
        self.assertEqual(np.array_equal(raw, corr), False)
        self.assertEqual(np.all(np.isfinite(corr)), True)
        self.assertEqual(np.all(corr > 0), True)
        self.assertAlmostEqual(cr, min(np_1 / dt_1, np_2 / dt_2))
        # The zero-lag channel carries the self-correlation and dominates.
        self.assertEqual(corr[0], corr.max())

        cr /= photons.dt
        dur = float(min(dt_1, dt_2)) * photons.dt / 1000.  # seconds
        tau = tau.astype(np.float64)
        tau *= photons.dt
        self.assertGreater(cr, 0.0)
        self.assertGreater(dur, 0.0)
        self.assertEqual(np.all(np.isfinite(tau)), True)

    def test_acceptor(self):
        times = np.linspace(0, 50, 1024)
        tau_da = 3.5
        decay_da = np.exp(-times / tau_da)
        acceptor_lifetime_spectrum = np.array(
            [0.1, 0.5, 0.9, 2.0]
        )

        transfer_efficiency = 0.3
        decay_ad = chisurf.core.fluorescence.fret.acceptor.da_a0_to_ad(
            times=times,
            decay_da=decay_da,
            acceptor_lifetime_spectrum=acceptor_lifetime_spectrum,
            transfer_efficiency=transfer_efficiency
        )
        eff = decay_ad.sum() / (decay_ad.sum() + decay_da.sum())

        self.assertAlmostEqual(
            eff,
            transfer_efficiency
        )

        for target_value in np.linspace(0.1, 0.9):
            scaled_acceptor = chisurf.core.fluorescence.fret.acceptor.scale_acceptor(
                donor=decay_da,
                acceptor=decay_ad,
                transfer_efficiency=target_value
            )
            eff = sum(scaled_acceptor) / (sum(scaled_acceptor) + sum(decay_da))
            self.assertAlmostEqual(
                eff,
                target_value
            )

    def convolve_lifetime_spectrum(self):
        reference_decay = np.array(
            [0.00000000e+00, 4.52643742e-06, 4.30136935e-05, 3.02142457e-04,
             1.65108038e-03, 7.06796476e-03, 2.38186826e-02, 6.35639959e-02,
             1.35361393e-01, 2.32352532e-01, 3.25883836e-01, 3.80450045e-01,
             3.79182520e-01, 3.33586262e-01, 2.69710789e-01, 2.08975297e-01,
             1.60624297e-01, 1.25068007e-01, 9.94465318e-02, 8.07767559e-02,
             6.68428191e-02, 5.61578412e-02, 4.77471111e-02, 4.09691949e-02,
             3.53963836e-02, 3.07383493e-02, 2.67937209e-02, 2.34193202e-02,
             2.05105461e-02, 1.79888012e-02, 1.57933761e-02, 1.38761613e-02,
             1.21981607e-02, 1.07271560e-02, 9.43611289e-03, 8.30206791e-03,
             7.30533192e-03, 6.42890327e-03, 5.65802363e-03, 4.97983239e-03,
             4.38309103e-03, 3.85795841e-03, 3.39580432e-03, 2.98905244e-03,
             2.63104654e-03, 2.31593553e-03, 2.03857411e-03, 1.79443629e-03,
             1.57954010e-03, 1.39038167e-03]
        )
        time_axis = np.linspace(0, 25, 50)
        irf_position = 5.0
        irf_width = 1.0
        irf = scipy.stats.norm.pdf(time_axis, loc=irf_position, scale=irf_width)
        lifetime_spectrum = np.array([0.8, 1.1, 0.2, 4.0])
        model_decay = np.zeros_like(time_axis)
        chisurf.core.fluorescence.tcspc.convolve.convolve_lifetime_spectrum(
            model_decay,
            lifetime_spectrum=lifetime_spectrum,
            instrument_response_function=irf,
            time_axis=time_axis
        )
        self.assertEqual(
            np.allclose(
                model_decay,
                reference_decay
            ),
            True
        )

    def test_fluorescence_tcspc_corrections_compute_linearization_table(self):
        x = np.linspace(0, 40, 128)
        dnl_fraction = 0.01
        counts = 10000
        mean = np.sin(x) * dnl_fraction * counts + (1 - dnl_fraction) * counts
        np.random.seed(0)
        data = np.random.poisson(mean).astype(np.float64)
        lin_table = compute_linearization_table(data, 12, "hanning", 10, 90)
        ref_lintable = np.array(
            [1., 1., 1., 1., 1.,
             1., 0.99980049, 0.99922759, 0.99823618, 0.99681489,
             0.99518504, 0.99393009, 0.99341097, 0.99356403, 0.99429588,
             0.99518651, 0.99570281, 0.99588077, 0.99593212, 0.99620644,
             0.99725223, 0.99907418, 1.00121338, 1.00320785, 1.00486314,
             1.00613769, 1.00711954, 1.00770543, 1.00739009, 1.00586985,
             1.00286934, 0.99849134, 0.99377306, 0.98981455, 0.98744986,
             0.98683355, 0.9874091, 0.98868764, 0.99063644, 0.99339915,
             0.99669779, 1.00031741, 1.00394849, 1.00699941, 1.00914148,
             1.01040307, 1.01119998, 1.01183167, 1.01202324, 1.01120659,
             1.00905205, 1.0055979, 1.0012921, 0.99701193, 0.99370229,
             0.99214721, 0.99253283, 0.99448162, 0.99720137, 0.99972508,
             1.001355, 1.00164798, 1.00115969, 1.00083382, 1.00120239,
             1.0025449, 1.00450071, 1.00633953, 1.00702856, 1.00606332,
             1.00373424, 1.00058981, 0.99734557, 0.99442657, 0.9925278,
             0.99219378, 0.99332066, 0.9954457, 0.99805603, 1.00079518,
             1.00285328, 1.00367601, 1.00341471, 1.00277917, 1.00262715,
             1.00308127, 1.00383407, 1.00447143, 1.00466959, 1.00415533,
             1.00289327, 1.00144407, 1.00036365, 0.99984595, 0.99978234,
             0.99991273, 1., 1., 1., 1.,
             1., 1., 1., 1., 1.,
             1., 1., 1., 1., 1.,
             1., 1., 1., 1., 1.,
             1., 1., 1., 1., 1.,
             1., 1., 1., 1., 1.,
             1., 1., 1.]
        )
        self.assertEqual(
            np.allclose(
                lin_table,
                ref_lintable
            ),
            True
        )

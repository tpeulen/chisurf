"""User-entered and FCS-derived reference fits for setup quality and cross-day monitoring."""
from datetime import datetime, timezone
import math
from pathlib import Path
import statistics

from chisurf.plugins.core.acq.live.reference_history import ReferenceHistory, ReferenceHistoryError


REFERENCE_DYES = [
    ('Rh110', 'Rhodamine 110 (Rh110)'),
    ('Rh6G', 'Rhodamine 6G (Rh6G)'),
    ('Atto488', 'ATTO 488 (COOH)'),
    ('Fluorescein', 'Fluorescein (FITC)'),
    ('Alexa647', 'Alexa Fluor 647 (AF647)'),
    ('Cy5', 'Cyanine 5 (Cy5)'),
]

DYE_D25_UM2_S = {
    'Rh110': 470.0,
    'Rhodamine 110': 470.0,
    'Rh6G': 414.0,
    'Rhodamine 6G': 414.0,
    'Atto488': 400.0,
    'ATTO 488 (COOH)': 400.0,
    'Fluorescein': 425.0,
    'Alexa647': 330.0,
    'Alexa Fluor 647': 330.0,
    'Cy5': 360.0,
}


def compute_confocal_parameters(dye: str, temp_c: float, tau_d_ms: float, s: float) -> tuple[float, float, float]:
    """Compute (D in µm²/s, w0 in nm, V_eff in fL) for a known dye diffusion and FCS fit."""
    d25 = DYE_D25_UM2_S.get(dye, 430.0)
    T_K = float(temp_c) + 273.15
    T_ref = 298.15
    try:
        from chisurf.core.fluorescence import diffusion
        eta_ref = diffusion.water_viscosity(T_ref)
        eta_T = diffusion.water_viscosity(T_K)
        D_T = d25 * (T_K / T_ref) * (eta_ref / eta_T)
    except Exception:
        D_T = d25 * (T_K / T_ref)

    if tau_d_ms <= 0 or not math.isfinite(tau_d_ms):
        return D_T, float('nan'), float('nan')

    # tau_D = w0^2 / (4 D)  =>  w0 = sqrt(4 * D * tau_D)
    tau_s = float(tau_d_ms) * 1e-3
    w0_um = math.sqrt(4.0 * D_T * tau_s)
    w0_nm = w0_um * 1e3

    # V_eff = pi^(3/2) * s * w0^3 (w0 in um gives V_eff directly in um^3 = fL)
    s_val = max(0.1, float(s))
    v_eff_fl = (math.pi ** 1.5) * s_val * (w0_um ** 3)
    return D_T, w0_nm, v_eff_fl


class SetupQualityModel:
    def __init__(self, model):
        self.model = model
        self.dye = 'Rh110'
        self.temperature_c = 22.0
        self.lifetime_ns = '4.0'
        self.diffusion_ms = ''
        self.brightness_khz = ''
        self.cpm_total_khz = ''
        self.kappa_s = 5.0
        self.laser_nm = self.power_uw = self.optics = self.detector = ''
        self.excitation = 'cw'
        self.rep_rate_mhz = self.file = self.fit_notes = ''
        self.message = ''
        self._rows_cache_key = None
        self._rows_cache = None

    @property
    def simulated(self):
        return self.model.source_kind == 'simulator' or self.model.simulation_connected

    @property
    def history(self):
        # Settings can redirect output_dir while the simulated rig remains attached, and the
        # photon simulator can run without a rig. Keep simulation in a separate namespace in
        # either case, independently of the directory name or how it was chosen.
        filename = ('setup-reference-history-simulation.json' if self.simulated
                    else 'setup-reference-history.json')
        return ReferenceHistory(Path(self.model.output_dir) / filename)

    def pull_from_live_fcs(self, fcs_data: dict | None = None) -> bool:
        """Populate setup quality parameters from live FCS analysis results."""
        if not fcs_data:
            return False
        tau_d_s = fcs_data.get('tau_d_s')
        if tau_d_s and tau_d_s > 0:
            self.diffusion_ms = f"{tau_d_s * 1e3:.3f}"
        s = fcs_data.get('s')
        if s and s > 0:
            self.kappa_s = float(s)
        cpm_b = fcs_data.get('cpm_bright')
        if cpm_b and cpm_b > 0:
            self.brightness_khz = f"{cpm_b:.2f}"
        cpm_t = fcs_data.get('cpm_total')
        if cpm_t and cpm_t > 0:
            self.cpm_total_khz = f"{cpm_t:.2f}"
        if hasattr(self.model, 'laser_effective_wavelength'):
            self.laser_nm = str(getattr(self.model, 'laser_effective_wavelength', '488'))
        return True

    def save_reference(self):
        try:
            lifetime = float(self.lifetime_ns) if self.lifetime_ns else 4.0
            if not math.isfinite(lifetime) or lifetime <= 0:
                raise ValueError('Lifetime must be positive and finite')
            tau_diff_s = float(self.diffusion_ms) / 1000.0 if self.diffusion_ms else float('nan')
            brightness_cps = float(self.brightness_khz) * 1000.0 if self.brightness_khz else float('nan')
            if not math.isfinite(tau_diff_s) or tau_diff_s <= 0:
                raise ValueError('Diffusion time must be positive and finite')
            if not math.isfinite(brightness_cps) or brightness_cps <= 0:
                raise ValueError('Brightness must be positive and finite')

            _, w0_nm, v_eff_fl = compute_confocal_parameters(
                self.dye, self.temperature_c, float(self.diffusion_ms), self.kappa_s
            )

            cpm_tot_khz = float(self.cpm_total_khz) if self.cpm_total_khz else float(self.brightness_khz)
            self.history.add(
                timestamp_utc=datetime.now(timezone.utc), dye=self.dye,
                laser_nm=float(self.laser_nm or 488.0), power_uw=float(self.power_uw or 5.0),
                power_verified=False, excitation_mode=self.excitation,
                rep_rate_mhz=None if self.excitation == 'cw' else float(self.rep_rate_mhz or 20.0),
                optical_configuration=self.optics or 'confocal', detector=self.detector or 'det0',
                tau_diff_s=tau_diff_s,
                brightness_cps=brightness_cps,
                provenance={
                    'lifetime_ns': lifetime, 'file': self.file, 'fit_notes': self.fit_notes,
                    'timestamp_kind': 'entry_time', 'measurement_time': None,
                    'w0_nm': w0_nm, 'v_eff_fl': v_eff_fl, 'kappa_s': self.kappa_s,
                    'cpm_total_khz': cpm_tot_khz,
                },
            )
        except (ValueError, ReferenceHistoryError, OSError) as exc:
            self.message = str(exc)
            return False
        self.message = 'Reference saved; setup quality record updated.'
        self._rows_cache_key = None
        return True

    def check_quality_bounds(self) -> tuple[bool, str]:
        """Verify whether setup metrics across days have exceeded maintenance bounds."""
        records = self.history.records()
        if not records:
            return False, ""
        for dye in ('Rh110', 'Alexa647', self.dye):
            matches = [r for r in records if r.get('dye') == dye]
            if len(matches) >= 2:
                latest = matches[-1]
                prev = matches[:-1]
                base_cpm = statistics.median(r.get('brightness_cps', 0) for r in prev)
                cur_cpm = latest.get('brightness_cps', 0)
                if base_cpm > 0 and cur_cpm < 0.80 * base_cpm:
                    pct = (1.0 - cur_cpm / base_cpm) * 100.0
                    return True, f"{dye} brightness dropped {pct:.1f}% below baseline."
                verdict = self.history.evaluate(latest)
                if verdict.get('status') == 'recommend_inspection':
                    return True, f"{dye} out of established bounds."
        return False, ""

    def quality_rows(self):
        history = self.history
        path = Path(self.model.output_dir) / (
            'setup-reference-history-simulation.json' if self.simulated
            else 'setup-reference-history.json')
        try:
            stat = path.stat()
            key = (path, stat.st_ino, stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            key = (path, None)
        if key == self._rows_cache_key:
            return [dict(row) for row in self._rows_cache]
        records = history.records()
        rows = []
        for dye in ('Rh110', 'Alexa647'):
            matches = [r for r in records if r['dye'] == dye]
            if not matches:
                rows.extend({'dye': dye, 'metric': metric, 'value': '—', 'status': 'missing'}
                            for metric in ('Lifetime', 'Diffusion time', 'Brightness'))
                continue
            record = matches[-1]
            verdict = history.evaluate(record)
            checks = {check['metric']: check for check in verdict['checks']}

            def metric_status(metric):
                check = checks.get(metric)
                if check is not None:
                    return ('within_reference' if check['level'] == 'within'
                            else 'recommend_inspection')
                if verdict['status'] in ('within_reference', 'recommend_inspection'):
                    return 'no_bounds'
                return verdict['status']

            rows.extend([
                {'dye': dye, 'metric': 'Lifetime', 'value': record['provenance'].get('lifetime_ns', '—'), 'status': 'no_verdict'},
                {'dye': dye, 'metric': 'Diffusion time', 'value': record['tau_diff_s'] * 1000, 'status': metric_status('tau_diff_s')},
                {'dye': dye, 'metric': 'Brightness', 'value': record['brightness_cps'] / 1000, 'status': metric_status('brightness_cps')},
            ])
        self._rows_cache_key, self._rows_cache = key, rows
        return [dict(row) for row in rows]

    def history_graph_data(self):
        """Extract historical calibration metrics across dates for plotting."""
        records = self.history.records()
        dates, cpm_bright, v_eff, dyes = [], [], [], []
        for i, r in enumerate(records):
            ts = r.get('timestamp_utc', '')[:10]
            dates.append(f"{ts} (#{i+1})")
            cpm_bright.append(r.get('brightness_cps', 0) / 1000.0)
            prov = r.get('provenance', {})
            v = prov.get('v_eff_fl')
            if v is None:
                tau_ms = r.get('tau_diff_s', 0) * 1000.0
                _, _, v = compute_confocal_parameters(r.get('dye', 'Rh110'), 22.0, tau_ms, 5.0)
            v_eff.append(float(v) if v is not None and math.isfinite(v) else 0.0)
            dyes.append(r.get('dye', ''))
        return dates, cpm_bright, v_eff, dyes

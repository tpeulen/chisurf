"""A sequential, modal acquisition wizard; no stage picker or unrelated run reuse.

Approved optical labels, target powers and acceptance limits are entered in Advanced
mode. Guided mode exposes only the current physical task and its acquisition. The
software cannot sense a filter or sample identity: those remain operator-confirmed.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import time
from emtk import im, Wizard, WizardStep
from emtk.view_form import FormState, draw_sections


class MeasurementWizardModel:
    STEPS = ('setup', 'optics', 'power', 'water', 'buffer', 'fcs',
             'green_reference', 'red_reference', 'dna', 'sample', 'done')
    TITLES = {'setup': 'Choose the approved experiment', 'optics': 'Check the optics',
              'power': 'Set the laser powers', 'water': 'Measure water (instrument response)',
              'buffer': 'Measure buffer only', 'fcs': 'FCS first: concentration and power',
              'green_reference': 'Measure the green reference dye',
              'red_reference': 'Measure the red reference dye', 'dna': 'Measure the DNA reference',
              'sample': 'Acquire your samples', 'done': 'Measurements saved'}
    SAMPLES = {'water': 'Insert water for the scattering / timing-response measurement. No fluorescent dye.',
               'buffer': 'Remove the water. Insert the same buffer used for your samples, with NO dye.',
               'fcs': 'Insert your FCS PRE-DILUTION (your stock mixed once, e.g. 1:10 in buffer).',
               'green_reference': 'Replace buffer with the approved dilute GREEN reference (normally Rh110).',
               'red_reference': 'Replace the green reference with the approved RED reference (Alexa647 or Atto655).',
               'dna': 'Replace the dye reference with your approved FRET DNA reference.',
               'sample': 'Remove the reference. Insert your sample and check its label against the sample name.'}

    def __init__(self, record):
        self.record = record
        self._index = 0
        self.protocol: dict = {}
        self.physical_done = False
        self.message = 'Choose an approved setup. Missing setup values must be entered by a trained operator in Advanced mode.'
        self.measurements = {}
        self.audit = []
        self._owned_session = None
        self._display_session = None
        self._owned_step = None
        self._accepted = False
        self._quality = []
        self.power_index = 0
        self.power_drives = {}
        self._power_pending = False
        self.power_session_targets_uw = {}
        self.sample_count = 1
        self.fcs_plan = None
        self.fcs_n = None
        self.protocol_name = ''
        self.kind = 'fret'
        self.filters_text = self.splitter_text = self.dyes_text = ''
        self.green_laser = self.red_laser = ''
        self.green_target_uw = self.red_target_uw = 0.
        self.seconds = 10.
        self.min_photons = 0
        self.irf_fwhm_max_ns = self.background_max_khz = 0.
        self.fcs_seconds = 300.
        self.fcs_target_n = 1.
        self.load_protocol()

    @property
    def path(self):
        return Path(self.record.output_dir)/'guided-protocol.json'

    @property
    def step_id(self):
        return self.STEPS[self._index]

    def load_protocol(self):
        try:
            self.protocol = json.loads(self.path.read_text())
        except FileNotFoundError:
            return False
        except (OSError, ValueError) as exc:
            self.message = f'Approved setup could not be loaded: {exc}'
            return False
        self.protocol_name = self.protocol.get('name', '')
        self.kind = self.protocol.get('kind', 'fret')
        self.filters_text = self.protocol.get('filters', '')
        self.splitter_text = self.protocol.get('splitter', '')
        self.dyes_text = self.protocol.get('dyes', '')
        targets = list(self.protocol.get('laser_targets_uw', {}).items())
        if targets:self.green_laser,self.green_target_uw=targets[0]
        if len(targets)>1:self.red_laser,self.red_target_uw=targets[1]
        for key in ('seconds','min_photons','irf_fwhm_max_ns','background_max_khz','fcs_seconds'):
            if key in self.protocol:setattr(self,key,self.protocol[key])
        self.fcs_target_n=float(self.protocol.get('smfret_target_n',1.) or 1.)
        return True

    def save_protocol(self):
        try:
            targets = {self.green_laser: self.green_target_uw}
            if self.kind == 'fret':
                if self.red_laser == self.green_laser:
                    raise ValueError('Select distinct green and red heads for FRET.')
                targets[self.red_laser] = self.red_target_uw
            protocol = {**self.protocol,**dict(name=self.protocol_name, kind=self.kind, filters=self.filters_text,
                            splitter=self.splitter_text, dyes=self.dyes_text, laser_targets_uw=targets,
                            seconds=self.seconds, min_photons=int(self.min_photons),
                            irf_fwhm_max_ns=self.irf_fwhm_max_ns, background_max_khz=self.background_max_khz)}
            errors = self.protocol_problems(protocol)
            if errors:
                raise ValueError('; '.join(errors))
            for name, target in targets.items():
                self.record.power_book.raw_target(name, target)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            staged = self.path.with_suffix('.json.part')
            staged.write_text(json.dumps(protocol, indent=2, allow_nan=False))
            staged.replace(self.path)
            self.protocol = protocol
            self.message = 'Approved setup saved. Guided mode uses these optics, powers, times and limits.'
            return True
        except (ValueError, OSError) as exc:
            self.message = str(exc)
            return False

    @staticmethod
    def protocol_problems(protocol):
        missing = [f'Enter {k} in the approved setup.' for k in ('name', 'filters', 'splitter', 'dyes')
                   if not str(protocol.get(k, '')).strip()]
        targets = protocol.get('laser_targets_uw', {})
        if not isinstance(targets, dict) or not targets:
            missing.append('Approve the laser target powers.')
        else:
            try:
                if any(not str(k).strip() or not math.isfinite(float(v)) or float(v)<=0 for k,v in targets.items()):
                    raise ValueError()
            except (ValueError,TypeError):
                missing.append('Laser names and target powers must be valid and positive.')
        for key in ('seconds', 'min_photons', 'irf_fwhm_max_ns', 'background_max_khz'):
            try:
                if not math.isfinite(float(protocol.get(key, 0))) or float(protocol.get(key, 0)) <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                missing.append(f'Approve a positive {key} value.')
        limits=protocol.get('reference_limits')
        if limits is not None:
            if not isinstance(limits,dict):missing.append('Reference limits must be a mapping of stages to metric ranges.')
            else:
                for stage,metrics in limits.items():
                    if not isinstance(metrics,dict):
                        missing.append(f'Reference limits for {stage} must name metric ranges.');continue
                    for metric,bounds in metrics.items():
                        try:
                            if not isinstance(bounds,(list,tuple)) or len(bounds)!=2:raise ValueError()
                            low,high=map(float,bounds)
                            if not (math.isfinite(low) and math.isfinite(high) and low<=high):raise ValueError()
                        except (ValueError,TypeError):
                            missing.append(f'Reference limit {stage}/{metric} must be [finite minimum, finite maximum].')
        return missing

    def safe_for_changes(self):
        if self.record.running:
            return False
        try:
            return bool(self.record.laser.state().emission_blocked) and \
                float(self.record.shutters.get_parameter('reported_excitation', -1)) == 0.
        except Exception:
            return False

    def simulation_practice(self):
        return bool(getattr(self.record,'simulation_connected',False) and self.record.source_kind=='simulator'
                    and self.protocol.get('simulation') is True)

    def make_safe(self):
        self.record.cancel_power_target()
        self.record.laser_off()
        self.record._shutters_at_end()

    def heading(self):
        return f'{self._index+1} / {len(self.STEPS)} — {self.TITLES[self.step_id]}'

    def instructions(self):
        step = self.step_id
        if step == 'setup':
            p = self.protocol
            return (f"Setup: {p.get('name', 'NOT CONFIGURED')}\nDyes: {p.get('dyes', 'not configured')}\n"
                    'Enter operator, project and sample below. The wizard will block light before each physical change.')
        if step == 'optics':
            return (f"Light must be blocked.\n1) Check the filter labels against this approved setup:\n{self.protocol['filters']}\n"
                    f"2) Fit/select this beam splitter:\n{self.protocol['splitter']}\n"
                    'One confirmation covers both checks. Do not look into an open beam. If a label differs, stop and ask a trained operator.')
        if step == 'power':
            targets = list(self.protocol['laser_targets_uw'].items())
            if self.power_index >= len(targets):
                return 'All selected laser targets were reached individually. Continue to the water measurement.'
            name, target = targets[self.power_index]
            return (f'Selected laser: {name}. Target: {target:g} µW (you may edit it below).\n'
                    'Close the instrument cover and keep the beam path clear. The next button allows light and tunes ONLY this head; other heads are set to zero.\n'
                    'Do not move filters or samples while power is being adjusted.')
        if step == 'fcs':
            return (self.SAMPLES['fcs'] +
                    '\nStart LOW to protect the detectors, then increase gradually while watching the Correlation amplitude. '
                    f'Let it run about {self.fcs_seconds/60:g} minutes: the wizard reads how many molecules are in focus and '
                    'then tells you exactly how many µL to dilute for the single-molecule measurements.')
        if step in self.SAMPLES:
            if step in self.measurements:
                return 'This step has a saved, checked recording. Review the quality table, then continue.'
            dilution = ''
            if self.fcs_plan and self.fcs_plan.get('ok'):
                dilution = '\n'.join(['Use the FCS dilution for single-molecule:'] + [f'  {line}' for line in self.fcs_plan['instructions']]) + '\n'
            seconds = self.fcs_seconds if step == 'fcs' else self.protocol.get('seconds', 0)
            return self.SAMPLES[step] + f"\nLight must be blocked while changing samples.\n{dilution}Check the label, close the cover, then tick the confirmation.\nThe next button allows light and records for {seconds:g} s."
        return ('Reference and sample files are saved separately. Physical checks were operator-confirmed, not sensor-verified.\n'
                'Reference acquisition is not a claim that gamma, lifetime or alignment calibration has been validated; retain the quality/provenance record for analysis.')

    def next_step(self):
        step = self.step_id
        if self.record.running:
            self.message = 'Wait for this measurement to finish, or stop it. No stage can be skipped.'
            return False
        if step == 'setup':
            issues = self.protocol_problems(self.protocol)
            simulated=self.simulation_practice()
            if not simulated and (self.record.source_kind != 'device' or self.record.device is None):
                issues.append('Connect a real TCSPC device; a simulator is not a calibration measurement.')
            if not simulated and (getattr(self.record.device, 'phacq_driver', '') == 'fake' or getattr(self.record.laser, 'kind', '') == 'simulated'):
                issues.append('Guided instrument measurements require real acquisition and laser hardware, not simulators.')
            if self.protocol.get('simulation') and not simulated:
                issues.append('A simulated practice protocol cannot authorize real instrument measurements.')
            for field in ('operator_name', 'project_name', 'sample_name'):
                if not str(getattr(self.record, field, '')).strip():
                    issues.append('Enter ' + field.replace('_', ' ') + '.')
            if issues:
                self.message = '\n'.join(issues)
                return False
            self.make_safe()
        elif step == 'optics':
            if not self.safe_for_changes() or not self.physical_done:
                self.message = 'Wait for laser-off AND closed-shutter readback, then confirm the displayed physical check.'
                return False
        elif step == 'power':
            if self.power_index < len(self.protocol['laser_targets_uw']):
                self.message = 'Set and verify every approved laser target first.'
                return False
        elif step in self.SAMPLES:
            if step not in self.measurements:
                self.message = 'Acquire and pass the checks for this step first.'
                return False
        elif step == 'done':
            return False
        self.audit.append({'step': step, 'confirmed_by': getattr(self.record, 'operator_name', ''),
                           'kind': 'operator-confirmed' if step in ('filters', 'splitter') else 'software-checked',
                           'time': time.strftime('%Y-%m-%dT%H:%M:%S')})
        self._display_session = None
        self._index += 1
        if self.protocol.get('kind') == 'polarization' and self.step_id in ('red_reference', 'dna'):
            self._index = self.STEPS.index('sample')
        self.physical_done = False
        self._quality = []
        self.message = 'Follow this step only. Do not change any other instrument controls.'
        self.save_audit()
        return True

    def can_previous(self):
        return (self._index > 0 and not self.record.running and not self._power_pending
                and not self.measurements and self.safe_for_changes())

    def previous_step(self):
        if not self.can_previous():
            self.message='Previous is unavailable while measuring or after reference acquisition. Recorded files are preserved.'
            return False
        self._display_session=None
        self._index-=1
        self.physical_done=False
        self._quality=[]
        if self.step_id=='power':
            self.power_index=0
            self.power_drives={}
        self.message='Repeat this physical check; earlier confirmations are not reused.'
        return True

    def enabled(self, action):
        if action == 'abort':return True
        if self.record.running or self._power_pending:return False
        if action == 'next_step':
            if self.step_id=='setup':
                source_ok=self.simulation_practice() or (self.record.source_kind=='device' and self.record.device is not None and not self.protocol.get('simulation'))
                return not self.protocol_problems(self.protocol) and source_ok and all(str(getattr(self.record,a,'')).strip() for a in ('operator_name','project_name','sample_name'))
            if self.step_id=='optics':return self.safe_for_changes() and self.physical_done
            if self.step_id=='power':return self.power_index>=len(self.protocol['laser_targets_uw'])
            return self.step_id in self.measurements
        if action == 'physical_done':return self.safe_for_changes()
        if action == 'set_approved_power':return self.step_id=='power' and self.power_index<len(self.protocol['laser_targets_uw'])
        if action == 'set_stage_power':return self.step_id=='fcs' and not self.record.running and not self._power_pending
        if action == 'start_measurement':return self.step_id in self.SAMPLES and self.step_id not in self.measurements and self.physical_done and self.safe_for_changes()
        if action in ('next_sample','finish_session'):return self.step_id=='sample' and self.step_id in self.measurements
        return True

    def _current_power_target(self):
        targets=list(self.protocol['laser_targets_uw'].items())
        if self.step_id=='fcs':return targets[0] if targets else (None,None)
        if self.power_index>=len(targets):return None,None
        return targets[self.power_index]

    def set_session_target(self,name,uw):
        """Set the operator's own session target for one head, bounded by its calibration."""
        try:
            uw=float(uw)
            max_uw=max((float(u) for _,u in self.record.power_book.points(name)),default=0.)
            if not (math.isfinite(uw) and 0.<uw<=max_uw):
                raise ValueError(f'{name}: {uw:g} µW is outside the calibrated range (max {max_uw:g} µW).')
        except (TypeError,ValueError) as exc:
            self.message=str(exc);return False
        self.power_session_targets_uw[name]=uw
        return True

    @property
    def stage_target_uw(self):
        name,target=self._current_power_target() or (None,0.)
        return self.power_session_targets_uw.get(name,target if name is not None else 0.)

    @stage_target_uw.setter
    def stage_target_uw(self,value):
        name,_=self._current_power_target() or (None,None)
        if name is not None:self.set_session_target(name,value)

    def set_approved_power(self):
        if self.step_id != 'power' or self.record.running:
            return False
        targets = list(self.protocol['laser_targets_uw'].items())
        if self.power_index >= len(targets) or self._power_pending:
            return False
        try:
            name, target = targets[self.power_index]
            target = self.power_session_targets_uw.get(name, target)
            return self._servo_single_head(name, target)
        except Exception as exc:
            self.make_safe()
            self.message = str(exc)
            return False

    def set_stage_power(self):
        """Adjust the first head's power from a measurement stage; explicit allow-light each time."""
        if self.step_id != 'fcs' or self.record.running or self._power_pending:
            return False
        targets = list(self.protocol['laser_targets_uw'].items())
        if not targets:
            return False
        name, target = targets[0]
        return self._servo_single_head(name, self.power_session_targets_uw.get(name, target))

    def _servo_single_head(self, name, target):
        try:
            self.record.power_poll(force=True)
            slots = {label: slot for slot, label in self.record.power_head_options()}
            if name not in slots:
                raise ValueError(f'Approved laser {name} is not connected. Stop; do not substitute another head.')
            self.record.power_book.raw_target(name, target)
            self.record.laser_off()
            for slot, _ in self.record.power_head_options():
                if slot != slots[name]:
                    self.record.laser.set_head(slot, intensity_pct=0.)
            self.record.power_selected_slot = slots[name]
            self.record.power_target_uw = target
            # the user has explicitly pressed an "Allow light" button for this head
            self.record.set_shutter('Excitation', True)
            if float(self.record.shutters.get_parameter('reported_excitation', -1)) != 1:
                raise ValueError('Excitation shutter has not reported open. Retry after its readback settles.')
            self.record.laser.set_emission(True)
            if not self.record.set_power_target():
                raise ValueError(self.record.power_message)
            self._power_pending = True
            self.message = 'Adjusting only the selected head. Wait for verified power.'
            return True
        except Exception as exc:
            self.make_safe()
            self.message = str(exc)
            return False

    def start_measurement(self):
        step = self.step_id
        if step not in self.SAMPLES or step in self.measurements or self.record.running:
            return False
        problems=self.protocol_problems(self.protocol)
        if problems:
            self.message='; '.join(problems)
            return False
        if not self.safe_for_changes() or not self.physical_done:
            self.message = 'Light must be blocked for sample changes. Confirm the sample label and closed cover first.'
            return False
        try:
            if self.power_index < len(self.protocol['laser_targets_uw']):
                raise ValueError('Approved laser powers have not been verified.')
            self.record.power_poll(force=True)
            slots = {label: slot for slot,label in self.record.power_head_options()}
            if set(slots) != set(self._approved_connected_heads):
                raise ValueError('The connected laser configuration changed. Restart guided setup.')
            for slot,label in self.record.power_head_options():
                active=True
                if step=='green_reference':active=label==list(self.protocol['laser_targets_uw'])[0]
                if step=='red_reference':active=label==list(self.protocol['laser_targets_uw'])[-1]
                if step=='fcs':active=label==list(self.protocol['laser_targets_uw'])[0]
                self.record.laser.set_head(slot, intensity_pct=self.power_drives.get(label, 0.) if active else 0.)
            if self.simulation_practice():self.record._instrument_sim.stage=step
            self.record.laser.set_emission(True)
            self.record.stop_after = True
            self.record.duration_s = float(self.fcs_seconds if step=='fcs' else self.protocol['seconds'])
            self.record.run_name = f"guided_sample{self.sample_count}_{{date}}" if step=='sample' else f"guided_{step}_{{date}}"
            self.record._guided_analysis_stage=step
            limits=dict((self.protocol.get('reference_limits') or {}).get(step) or {})
            if step=='water':limits.setdefault('irf_fwhm_ns',[0.,float(self.protocol['irf_fwhm_max_ns'])])
            if step=='buffer':limits.setdefault('rate_khz',[0.,float(self.protocol['background_max_khz'])])
            self.record._guided_analysis_limits=limits
            self.record._guided_start_authorized = True
            try:
                if not self.record.start():
                    raise ValueError(self.record.status_detail)
            finally:
                self.record._guided_start_authorized = False
            self._owned_session = self.record.session
            self._display_session = self._owned_session
            self._owned_step = step
            self.physical_done = False
            self._accepted = False
            self.message = 'Recording this step. Wait; do not change the sample or optics.'
            return True
        except Exception as exc:
            self.make_safe()
            self.message = str(exc)
            return False

    def accept_measurement(self):
        if self._owned_session is None or self.record.session is not self._owned_session or self._owned_step != self.step_id:
            self.message = 'No recording belongs to this step. An unrelated or earlier recording cannot be used.'
            return False
        session = self._owned_session
        if self.record.running or session.result is None:
            self.message = 'This step is still recording.'
            return False
        result = session.result
        snap = session.snapshot()
        rows = [dict(metric='Photon count', value=result.photons, limit=f">= {self.protocol['min_photons']}",
                     status='pass' if result.photons >= self.protocol['min_photons'] else 'fail',
                     guidance='If low: check the sample, alignment and shutter before repeating.'),
                dict(metric='Recording completed', value=result.stop_reason, limit='duration reached',
                     status='pass' if result.stop_reason=='duration reached' else 'fail',
                     guidance='An interrupted or failed run is retained, but cannot advance this step.'),
                dict(metric='Live analysis complete', value=str(result.analysis_complete),
                     limit='complete', status='pass' if result.analysis_complete and not snap.get('analysis_gap') else 'fail',
                     guidance='Live analysis was incomplete. Repeat this stage before using its results.'),
                dict(metric='Data loss / source errors', value=str(snap.get('source_error','')) or snap.get('dropped',0),
                     limit='none', status='fail' if snap.get('source_error') or snap.get('dropped') else 'pass',
                     guidance='Do not continue if acquisition lost data.')]
        try:
            self._read_saved_result(result, rows)
        except Exception as exc:
            rows.append(dict(metric='Saved file check',value=str(exc),limit='readable and complete',status='fail',
                             guidance='Keep the file; do not advance. Resolve the acquisition/readback error.'))
        live_checks=(snap.get('reference_live') or {}).get('quality') or []
        self._quality=rows+live_checks
        self._accepted=all(row['status']=='pass' for row in rows) and not any(row['status']=='fail' for row in live_checks)
        if self._accepted:
            self.measurements[self.step_id]={'path':str(result.ptu),'photons':result.photons,
                                            'quality':rows,'targets_uw':dict(self.protocol['laser_targets_uw']),
                                            'simulation':self.simulation_practice()}
            if self.step_id=='fcs':self._record_fcs_outcome(snap)
            if self.step_id=='fcs' and not (self.fcs_plan and self.fcs_plan.get('ok')):
                del self.measurements['fcs']
                self._accepted=False
                self.message=('The FCS correlation is not usable yet. Increase the power a little '
                              '(Allow light and set this power), or improve the sample, then record this stage again.')
                return False
            self.message='Recording saved. Review the curves and checks, then press Next. Unverified rows are not a validated diffusion/lifetime calibration.'
            self.save_audit()
        else:
            self.message='Checks failed. The file is preserved. Correct the listed problem and repeat this step.'
        return self._accepted

    def _read_saved_result(self,result,rows):
        """Re-read the saved file independently; a mismatch is a failed check, never a silent pass."""
        import numpy as np
        import tttrlib
        data = tttrlib.TTTR(str(result.ptu), 'PTU')
        photons = np.asarray(data.event_types)==0
        if int(photons.sum()) != result.photons:
            raise ValueError('Saved photon count does not match the recording result.')
        if self.step_id == 'water':
            from chisurf.plugins.core.acq.live.calibration.measurements import irf_fwhm_ns
            widths = []
            for ch in np.unique(np.asarray(data.routing_channels)[photons]):
                sel=photons & (np.asarray(data.routing_channels)==ch)
                hist=np.bincount(np.asarray(data.micro_times)[sel].astype(int))
                width,_=irf_fwhm_ns(hist,float(data.header.micro_time_resolution)*1e9)
                if width is not None:widths.append(width)
            width=max(widths) if widths else None
            rows.append(dict(metric='IRF main-peak FWHM (worst detector)',value=width if width is not None else 'unavailable',
                             limit=f"<= {self.protocol['irf_fwhm_max_ns']} ns",
                             status='pass' if width is not None and width<=self.protocol['irf_fwhm_max_ns'] else 'fail',
                             guidance='If wide or unavailable: stop and ask for timing/alignment inspection.'))
        if self.step_id == 'buffer':
            rate=result.photons/max(float(result.elapsed_s),1e-12)/1000
            rows.append(dict(metric='Buffer count rate',value=rate,limit=f"<= {self.protocol['background_max_khz']} kHz",
                             status='pass' if rate<=self.protocol['background_max_khz'] else 'fail',
                             guidance='If high: check contamination and stray light before repeating.'))

    def _record_fcs_outcome(self,snap):
        """Read the FCS amplitude-derived N and derive the explicit µL dilution for smFRET."""
        metrics=((snap.get('reference_live') or {}).get('metrics') or {})
        values=[float(m['n_amplitude_estimate']) for m in metrics.values() if isinstance(m,dict)
                and m.get('n_amplitude_estimate') is not None
                and math.isfinite(float(m['n_amplitude_estimate'])) and float(m['n_amplitude_estimate'])>0]
        self.fcs_n=sum(values)/len(values) if values else None
        self.fcs_plan=self._build_dilution_plan()
        if self.measurements.get('fcs') is not None:
            self.measurements['fcs'].update(n_estimate=self.fcs_n,dilution=list(self.fcs_plan['instructions']))

    def _build_dilution_plan(self):
        if not self.fcs_n or self.fcs_n<=0:
            return {'ok':False,'instructions':['No usable correlation amplitude; repeat the FCS measurement before diluting.'],'achieved':None}
        if self.fcs_n<=self.fcs_target_n*1.05:
            return {'ok':True,'achieved':self.fcs_n,'reason':'',
                    'instructions':[f'~{self.fcs_n:.2f} molecules in focus is already single-molecule level; use this dilution directly.']}
        try:
            from chisurf.plugins.core.acq.live.dilution import plan_dilution
            plan=plan_dilution(self.fcs_n,self.fcs_target_n)
            return {'ok':bool(plan.ok),'instructions':list(plan.instruction_lines),
                    'achieved':float(plan.achieved_conc),'reason':getattr(plan,'reason','')}
        except Exception as exc:  # advisor unavailable: honest ratio, no invented volumes
            return {'ok':False,
                    'instructions':[f'Dilution advisor unavailable ({exc}). Dilute about '
                                    f'{self.fcs_n/self.fcs_target_n:.0f}-fold to reach ~{self.fcs_target_n:g} molecule(s) in focus.'],
                    'achieved':None}

    def poll(self):
        if self._power_pending:
            servo=self.record.power_servo
            if servo is not None and not servo.active:
                self._power_pending=False
                if servo.status=='reached' and self.step_id=='power':
                    name=list(self.protocol['laser_targets_uw'])[self.power_index]
                    self.record.power_poll(force=True)
                    self.power_drives[name]=self.record.power_head().intensity_pct
                    self._approved_connected_heads=[label for _,label in self.record.power_head_options()]
                    self.power_index+=1
                    self.message=servo.message+' Light blocked. Continue with the next head or measurement.'
                elif servo.status=='reached':
                    name=list(self.protocol['laser_targets_uw'])[0]
                    self.record.power_poll(force=True)
                    self.power_drives[name]=self.record.power_head().intensity_pct
                    self.message=servo.message+' Light blocked. Re-run this stage or continue as instructed.'
                else:self.message=servo.message
                self.make_safe()
                if (self.step_id=='power' and servo.status=='reached'
                        and self.power_index<len(self.protocol['laser_targets_uw'])
                        and not self.record.running):
                    self.set_approved_power()  # one allow-light gesture chains every head
        if self._owned_session is not None and not self.record.running and not self._accepted:
            if self._owned_session.result is not None:
                self.make_safe()
                if self.accept_measurement() and self.step_id not in ('sample','done'):
                    self.next_step()  # a green stage advances without an extra Next click
                    self.message='Checks passed — advanced automatically. '+self.message
                self._owned_session=None  # no repeated file scans every frame

    def next_sample(self):
        """Loop the sample step: the calibration and references stay valid for every sample."""
        if self.step_id!='sample' or 'sample' not in self.measurements or self.record.running:
            self.message='Accept the current sample first.'
            return False
        del self.measurements['sample']
        self.sample_count+=1
        self.physical_done=False;self._accepted=False;self._quality=[]
        self._owned_session=None
        self._display_session=None
        self.message=(f'Sample {self.sample_count}: insert the next sample, confirm its label, then record. '
                      'The calibration and references stay valid.')
        self.save_audit()
        return True

    def finish_session(self):
        if self.step_id!='sample' or 'sample' not in self.measurements:
            self.message='Accept the current sample first.'
            return False
        return self.next_step()

    @staticmethod
    def light_level(rows):
        """Novice traffic light: green unless something fails or is still pending.

        Unconfigured scientific checks are *unverified*, not warnings: they are shown
        as "no verdict" in the table and must not keep a fully passing stage yellow.
        """
        rows=list(rows or [])
        bad=[r for r in rows if r.get('status')=='fail']
        if bad:
            return 'red','Improve: '+'; '.join(r.get('guidance') or r.get('metric','') for r in bad)[:400]
        warn=[r for r in rows if r.get('status') in ('watch','waiting')]
        if warn:
            return 'yellow','Not ready yet: '+'; '.join((r.get('guidance') or r.get('metric','')) for r in warn)[:400]
        return 'green','Good'

    def display_snapshot(self):
        """Only display data from this stage and sample's own recording session."""
        if self._display_session is None or self.record.session is not self._display_session:
            return {}
        return getattr(self.record,'snapshot',None) or {}

    def quality_rows(self):
        live=self.display_snapshot().get('reference_live') or {}
        if self.record.running and live.get('stage')==self.step_id and live.get('quality'):
            return live['quality']
        return self._quality or [dict(metric='Current step',value=self.TITLES[self.step_id],limit='complete in order',
                                      status='waiting',guidance=self.message)]

    def abort(self):
        if self.record.running:self.record.stop()
        self.make_safe()
        self.message='Stopped. Files are retained. Light blocked; verify instrument readback before touching optics.'
        self.save_audit()

    def save_audit(self):
        path=Path(self.record.output_dir)/'guided-progress.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'protocol':self.protocol,'step':self.step_id,'audit':self.audit,
                                    'measurements':self.measurements},indent=2,allow_nan=False))


class MeasurementWizard:
    """Modal window; the host must not draw interactive controls behind it."""
    def __init__(self, record):
        from chisurf.plugins.core.acq.gui.calibration_panel import CalibrationPanel
        self.model=MeasurementWizardModel(record)
        self.record=record
        self.navigation=Wizard('Guided measurement',
            [WizardStep(key,self.model.TITLES[key],self.model.instructions,
                        can_next=lambda:self.model.enabled('next_step')) for key in self.model.STEPS],
            index_source=lambda:self.model._index,on_next=self.model.next_step,
            on_back=self.model.previous_step,can_back=self.model.can_previous,
            on_cancel=self._stop,size=(1240,900),cancel_label='Stop / block light')
        self.window=self.navigation.window
        self.form=FormState()
        self.form.custom['wizard_quality']=CalibrationPanel._draw_data_table
        self.form.custom['wizard_body']=self._body
        self.setup_form=FormState()

    def _body(self,section,model,state,width):
        m=self.model
        if m.step_id=='setup':
            draw_sections([{'type':'value','kind':'str','attr':a,'label':label,'description':'Stored with every measurement.'}
                           for a,label in [('operator_name','Operator'),('project_name','Project'),('sample_name','Sample label')]],
                          self.record,self.form)
            if getattr(self.record, '_guided_configure_allowed', False):
                if im.collapsing_header('Edit approved setup (Advanced)'):
                    im.begin_child('approved_setup', (width, 220))
                    self.draw_setup(allow_edit=True)
                    im.end_child()
        if m.step_id=='optics' or m.step_id in m.SAMPLES:
            draw_sections([{'type':'toggle','attr':'physical_done',
                            'label':'I checked the labels, completed this task and closed the cover',
                            'description':'An explicit operator confirmation; the software cannot sense a filter or sample identity.'}],m,self.form)
        if m.step_id=='power' and m._current_power_target()[0] is not None:
            draw_sections([{'type':'value','attr':'stage_target_uw','label':'Target for this laser (µW)','kind':'float',
                            'description':'Your own session target, bounded by this head\'s calibration; applies to every following measurement.'}],m,self.form)
        if m.step_id=='fcs':
            draw_sections([{'type':'value','attr':'stage_target_uw','label':'Green laser target (µW)','kind':'float',
                            'description':'Start low and raise gradually while watching the correlation; bounded by the calibration.'}],m,self.form)
        buttons=[]
        if m.step_id=='power':
            buttons.append({'action':'set_approved_power','label':'Allow light and set approved power',
                            'description':'Explicit permission to illuminate only the selected head and tune its approved target.'})
        if m.step_id=='fcs':
            buttons.append({'action':'set_stage_power','label':'Allow light and set this power',
                            'description':'Explicit permission: illuminate only the green head at the entered target.'})
        if m.step_id in m.SAMPLES:
            buttons.append({'action':'start_measurement','label':'Allow light and record this sample',
                            'description':'Record only this stage using approved timing and target powers.'})
            if m.step_id=='sample' and 'sample' in m.measurements:
                buttons.append({'action':'next_sample','label':'Measure another sample (same calibration)',
                                'description':'The calibration, references and DNA corrections stay valid; only the sample changes.'})
                buttons.append({'action':'finish_session','label':'Finish guided session',
                                'description':'End after this sample; all files and the audit trail are kept.'})
        if buttons:draw_sections([{'type':'button_row','buttons':buttons}],m,self.form)

    def _stop(self):
        self.model.abort()
        return False

    def _task_body(self, step):
        m=self.model
        self._body(None,m,self.form,im.get_content_region_avail()[0])
        draw_sections([{'type':'info','source':'message'}],m,self.form)
        level,text=m.light_level(m.quality_rows())
        im.text_colored({'green':(0.30,0.85,0.35,1.),'yellow':(0.93,0.75,0.20,1.),'red':(0.93,0.35,0.30,1.)}[level],
                        f'[{level.upper()}] {text}')
        if m.step_id in ('dna','sample','fcs'):
            snap=m.display_snapshot()
            if snap:
                elapsed=float(snap.get('elapsed_s') or 0.)
                im.text(f"Bursts: {snap.get('bursts','—')}   Measurement time: {elapsed:.0f} s   Photons: {snap.get('photons','—')}")
        from chisurf.plugins.core.acq.gui.guided_plots import draw_guided_plots
        draw_guided_plots(m,self.form)
        if im.button('Leave guided mode (stop and block light)'):
            m.abort();self.record.ui_mode='simple';self.record.advanced=False;self.window.hide()
        im.set_item_tooltip('Ends the guided session safely before exposing ordinary controls.')
        draw_sections([
            {'type':'custom','key':'wizard_quality','options':{'source':'quality_rows','row_key':'metric','height':140,'fit_rows':True,
             'tooltip_key':'guidance','selection_note':False,
             'columns':[{'key':key,'title':title,**({'background':{'pass':'#24683d','fail':'#8b3535','watch':'#806523','unverified':'#4a4a4a','waiting':'#4a4a4a'}} if key=='status' else {})} for key,title in [('metric','Check'),('value','Measured'),('limit','Required'),('status','Status')]]}},
        ],m,self.form)

    def draw(self,box):
        self.model.poll()
        self.window.title='Guided measurement — SIMULATION ONLY' if self.model.simulation_practice() else 'Guided measurement'
        self.form.rects.clear()
        self.setup_form.rects.clear()
        self.navigation.draw(box,self._task_body)
        self.form.rects.update(self.navigation.rects)
        if 'wizard_next' in self.form.rects:self.form.rects['next_step']=self.form.rects['wizard_next']
        if 'wizard_cancel' in self.form.rects:self.form.rects['wizard_abort']=self.form.rects['wizard_cancel']

    def draw_setup(self, *, allow_edit=False):
        m=self.model
        draw_sections([{'type':'info','source':'message'}],m,self.setup_form)
        if not self.record.advanced and not allow_edit:
            im.text_wrapped('Guided measurement runs as a modal wizard. Choose Guided mode above. A trained operator configures its approved optics, powers and quality limits in Advanced mode.')
            return
        fields=[('protocol_name','Setup name','str'),('kind','Experiment: fret / polarization','str'),
                ('filters_text','Exact filter labels / positions','str'),('splitter_text','Exact beam-splitter label / position','str'),
                ('dyes_text','Dyes / reference samples','str'),('green_laser','Green laser name (as in Laser page)','str'),
                ('green_target_uw','Green target (µW)','float'),('red_laser','Red laser name (FRET)','str'),
                ('red_target_uw','Red target (µW)','float'),('seconds','Seconds per recording','float'),
                ('min_photons','Minimum photons per step','int'),('irf_fwhm_max_ns','Maximum IRF main-peak FWHM (ns)','float'),
                ('background_max_khz','Maximum buffer rate (kHz)','float')]
        sections=[{'type':'value','attr':a,'label':label,'kind':kind,'description':'Approved setup value for inexperienced operators; no universal scientific limit is supplied.'}
                  for a,label,kind in fields]
        sections.append({'type':'button_row','buttons':[{'action':'save_protocol','label':'Save approved setup',
                         'description':'Validate optical labels, target calibration ranges and acceptance limits, then save for Guided mode.'}]})
        draw_sections(sections,m,self.setup_form)

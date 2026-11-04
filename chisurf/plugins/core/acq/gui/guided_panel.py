"""Guided experimental measurements, rendered from the shared workflow library.

No hardware is driven here. The operator records the sample and optical setup,
acquires through Record, and attaches the resulting measurements. Quality values
and prerequisite checks come from the same backend used by scripts.
"""
from __future__ import annotations

import json
from pathlib import Path
from emtk.view_form import FormState, draw_sections
from chisurf.plugins.core.acq.live.calibration.library import build_workflow
from chisurf.plugins.core.acq.live.calibration.workflow import CalibrationWorkflow


class GuidedPanelModel:
    """Editable stage inputs, explicit confirmation, and persisted provenance."""

    def __init__(self, path, record_model=None):
        self.path = str(path)
        self.record_model = record_model
        self.workflow_kind = 'fret'
        self.workflow = build_workflow(self.workflow_kind)
        self.step_id = self.workflow.steps[0].id
        self.message = ''
        self.note = ''
        self.sections = []
        self.select_step()

    def kind_options(self):
        return [('fret', 'FRET / PIE'), ('polarization', 'Polarization / MFD')]

    def change_kind(self, _value=None):
        # never discard the current working calibration silently
        if not self.save_workflow():
            return False
        self.workflow = build_workflow(self.workflow_kind)
        self.step_id = self.workflow.steps[0].id
        self.select_step()
        self.message = 'New workflow; the previous workflow was saved to the displayed file.'
        return True

    def step_options(self):
        return [(s.id, f'{i + 1}. {s.name} [{self.workflow.state[s.id].state}]')
                for i, s in enumerate(self.workflow.steps)]

    @property
    def step(self):
        return next(s for s in self.workflow.steps if s.id == self.step_id)

    def select_step(self, _value=None):
        state = self.workflow.state[self.step_id]
        self.note = state.note
        inputs = []
        for i, spec in enumerate(self.step.inputs):
            value = state.values.get(spec.key, spec.default)
            attr = f'input_{i}'
            if spec.kind == 'boolean':
                setattr(self, attr, bool(value))
                section = {'type': 'toggle', 'attr': attr}
            elif spec.kind == 'choice':
                setattr(self, attr, value)
                section = {'type': 'choice', 'attr': attr,
                           'options': [(v, str(v)) for v in spec.choices]}
            else:
                if isinstance(value, (list, dict)):
                    value = json.dumps(value)
                setattr(self, attr, '' if value is None else str(value))
                section = {'type': 'value', 'kind': 'str', 'attr': attr}
            section.update(label=spec.name + (f' ({spec.unit})' if spec.unit else ''),
                           description=spec.describe or f'Measured input for {self.step.name}.')
            inputs.append(section)
        limits = []
        for i, metric in enumerate(self.step.metrics):
            for bound, label in [('minimum', 'min'), ('maximum', 'max')]:
                attr = f'limit_{label}_{i}'
                value = getattr(metric.limits, bound)
                setattr(self, attr, '' if value is None else str(value))
                limits.append({'type': 'value', 'kind': 'str', 'attr': attr,
                               'label': f'{metric.name} {label}',
                               'description': 'Your acceptance bound; empty means no bound.'})
        self.sections = [
            {'type': 'choice', 'attr': 'workflow_kind', 'label': 'Experiment',
             'options_source': 'kind_options', 'call': 'change_kind',
             'description': 'FRET or polarization guided calibration; no hardware is switched.'},
            {'type': 'choice', 'attr': 'step_id', 'label': 'Stage',
             'options_source': 'step_options', 'call': 'select_step',
             'description': 'Stages retain their measurements; prerequisites gate confirmation.'},
            {'type': 'info', 'source': 'instructions'},
            {'type': 'panel', 'title': 'Measurements', 'sections': inputs, 'n_col': 1},
            {'type': 'value', 'attr': 'note', 'kind': 'str', 'label': 'Confirmation / skip note',
             'description': 'Record your reasoning, physical actions and any unresolved limitations.'},
            {'type': 'button_row', 'buttons': [
                {'action': 'use_recording', 'label': 'Use latest recording',
                 'description': 'Attach the latest PTU and its measured count/time where applicable; no synthetic measurements.'},
                {'action': 'apply_inputs', 'label': 'Evaluate',
                 'description': 'Evaluate measured inputs and user-configured metric limits.'},
                {'action': 'confirm_step', 'label': 'Confirm stage', 'role': 'primary',
                 'description': 'Record explicit confirmation only after prerequisites and inputs are present.'},
            ]},
            {'type': 'button_row', 'buttons': [
                {'action': 'reopen_step', 'label': 'Reopen', 'description': 'Invalidate this confirmation and dependent stages before editing.'},
                {'action': 'skip_step', 'label': 'Skip with reason', 'description': 'Only explicitly skippable stages can be skipped, with a reason.'},
            ]},
            {'type': 'info', 'source': 'status'},
            {'type': 'custom', 'key': 'guided_quality', 'options': {
                'source': 'quality_rows', 'row_key': 'metric', 'height': 150,
                'columns': [{'key': key, 'title': title} for key, title in [
                    ('metric', 'Metric'), ('value', 'Measured'), ('unit', 'Unit'),
                    ('limit', 'Your limits'), ('status', 'Status'), ('guidance', 'Guidance')]]}},
            {'type': 'panel', 'title': 'Acceptance limits (optional)', 'collapsible': True,
             'collapsed': True, 'sections': limits, 'n_col': 1},
            {'type': 'value', 'attr': 'path', 'kind': 'str', 'label': 'Workflow JSON',
             'description': 'Persistent measured values, limits, confirmations and result provenance.'},
            {'type': 'button_row', 'buttons': [
                {'action': 'save_workflow', 'label': 'Save workflow', 'description': 'Save this workflow without changing hardware.'},
                {'action': 'load_workflow', 'label': 'Load workflow', 'description': 'Load an existing calibration and its recorded provenance.'},
            ]},
        ]

    def instructions(self):
        return self.step.goal + "\n\n" + self.step.instructions

    def status(self):
        blockers = self.workflow.blockers(self.step_id)
        return (self.message or self.workflow.state[self.step_id].state) + "\n" + '; '.join(blockers)

    def enabled(self, action):
        confirmed = self.workflow.state[self.step_id].confirmed
        if action in ('apply_inputs', 'confirm_step', 'use_recording') or action.startswith('input_'):
            return not confirmed
        if action == 'reopen_step':
            return confirmed
        if action == 'skip_step':
            return self.step.skippable and not confirmed
        return True

    def apply_inputs(self):
        try:
            if self.workflow.state[self.step_id].confirmed:
                raise ValueError('Reopen the confirmed stage before editing.')
            # validate every value before mutating the workflow
            staged = {}
            for i, spec in enumerate(self.step.inputs):
                value = getattr(self, f'input_{i}')
                if value is None or value == '':
                    continue
                staged[spec.key] = self.workflow._cast(spec, value)
            for i, metric in enumerate(self.step.metrics):
                lo, hi = getattr(self, f'limit_min_{i}'), getattr(self, f'limit_max_{i}')
                if lo == hi == '':
                    self.workflow.clear_limits(self.step_id, metric.key)
                else:
                    low, high = float(lo) if lo else None, float(hi) if hi else None
                    if low is not None and high is not None and low > high:
                        raise ValueError('Minimum acceptance bound exceeds maximum.')
                    self.workflow.configure_limits(self.step_id, metric.key, minimum=low, maximum=high)
            self.workflow.state[self.step_id].values = staged
            self.message = 'Inputs evaluated; limits are yours, not universal pass/fail thresholds.'
            return True
        except (ValueError, TypeError) as exc:
            self.message = str(exc)
            return False

    def confirm_step(self):
        if not self.apply_inputs():
            return False
        try:
            self.workflow.confirm(self.step_id, note=self.note)
        except ValueError as exc:
            self.message = str(exc)
            return False
        if not self.save_workflow():
            return False
        idx = next(i for i, s in enumerate(self.workflow.steps) if s.id == self.step_id)
        self.step_id = self.workflow.steps[min(idx + 1, len(self.workflow.steps) - 1)].id
        self.select_step()
        self.message = 'Stage confirmed and saved. Follow the next instructions.'
        return True

    def reopen_step(self):
        try:
            self.workflow.unconfirm(self.step_id, note=self.note)
            self.select_step()
            return self.save_workflow()
        except ValueError as exc:
            self.message = str(exc)
            return False

    def skip_step(self):
        try:
            self.workflow.skip(self.step_id, reason=self.note)
            return self.save_workflow()
        except ValueError as exc:
            self.message = str(exc)
            return False

    def use_recording(self):
        record = self.record_model
        if record is None or record.saved_path is None or record.running:
            self.message = 'Finish a recording first; no file or measured values were substituted.'
            return False
        snap = record.snapshot or {}
        values = {'file': str(record.saved_path), 'photons': snap.get('photons'),
                  'acquisition_time_s': snap.get('elapsed_s')}
        for i, spec in enumerate(self.step.inputs):
            if values.get(spec.key) is not None:
                setattr(self, f'input_{i}', str(values[spec.key]))
        self.message = 'Attached latest recording. Check sample, units, channels and fit assumptions.'
        return self.apply_inputs()

    def quality_rows(self):
        return [{'metric': m['name'], 'value': '' if m['value'] is None else m['value'],
                 'unit': m['unit'], 'limit': m['limits_text'], 'status': m['verdict'],
                 'guidance': m['detail'] or m['describe']}
                for m in self.workflow.metrics(self.step_id)] or [
                    {'metric': 'Prerequisites / operator confirmation', 'value': '', 'unit': '',
                     'limit': '', 'status': self.workflow.state[self.step_id].state,
                     'guidance': '; '.join(self.workflow.blockers(self.step_id)) or self.step.goal}]

    def save_workflow(self):
        try:
            self.workflow.save(self.path)
            self.message = 'Workflow saved.'
            return True
        except (OSError, ValueError) as exc:
            self.message = str(exc)
            return False

    def load_workflow(self):
        try:
            self.workflow = CalibrationWorkflow.load(self.path)
            self.workflow_kind = self.workflow.kind
            self.step_id = next((s.id for s in self.workflow.steps if not self.workflow.state[s.id].confirmed),
                                self.workflow.steps[-1].id)
            self.select_step()
            self.message = 'Loaded measured workflow and confirmations.'
            return True
        except (OSError, ValueError, KeyError) as exc:
            self.message = str(exc)
            return False


class GuidedPanel:
    """Embed the generated AutoForm in the acquisition app's scrollable dock."""
    def __init__(self, model):
        from chisurf.plugins.core.acq.gui.calibration_panel import CalibrationPanel
        self.model = model
        self.form = FormState()
        self.form.custom['guided_quality'] = CalibrationPanel._draw_data_table

    def draw(self):
        draw_sections(self.model.sections, self.model, self.form)

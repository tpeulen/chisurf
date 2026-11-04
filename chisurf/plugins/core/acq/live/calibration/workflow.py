"""The guided calibration workflow engine.

A calibration is a list of *stages* the user walks through in order. The engine
owns the discipline, never the science:

* **Prerequisites.** Each stage names the stages that must be confirmed (or
  explicitly skipped with a reason) before it unlocks. Confirming a stage while
  its inputs or prerequisites are open is refused, and the refusal says what is
  missing. Unconfirming a stage cascades to the stages that consumed its
  results.
* **Confirmations.** A stage is closed by an explicit user confirmation with a
  note; confirmed values are locked until the stage is unconfirmed.
* **Transparent quality metrics.** Each stage declares metrics that compute a
  value from the stage's inputs. Every metric says what it computes
  (``describe``) and why a value is unavailable (``detail``). Whether a value
  is *good* is decided only by limits the user configures on that metric -- a
  shipped workflow carries no numerical thresholds. Confirmations record
  out-of-bounds metrics as warnings rather than refusing: the judgement is the
  user's, the record shows it.
* **Measured results.** Confirming a stage records its calibrations as
  :class:`MeasuredResult` -- value, unit, when, from which stage, on which
  sample and file, and whether the value was entered (the user's own fit) or
  computed here from the attached data.

Persistence is JSON: the step list (by library spec id), the state, the
configured limits and the results. The metric computations are rebound from the
library on load. No function here drives hardware.
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

FORMAT = "chisurf-calibration-workflow"
VERSION = 1

__all__ = [
    "CalibrationWorkflow",
    "InputSpec",
    "MeasuredResult",
    "MetricLimits",
    "MetricSpec",
    "StepConfirmed",
    "StepSpec",
    "StepState",
    "FORMAT",
    "VERSION",
]


class StepConfirmed(RuntimeError):
    """The stage is confirmed; unconfirm it (with a note) before editing."""


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


@dataclass
class MetricLimits:
    """The user's accept/reject bounds for one metric. Shipped empty."""

    minimum: float | None = None
    maximum: float | None = None

    def is_empty(self) -> bool:
        return self.minimum is None and self.maximum is None

    def describe(self) -> str:
        if self.is_empty():
            return "no limits configured (the value is reported, not judged)"
        low = "-inf" if self.minimum is None else f"{self.minimum:g}"
        high = "+inf" if self.maximum is None else f"{self.maximum:g}"
        return f"limits: {low} ... {high}"

    def to_dict(self) -> dict:
        return {"minimum": self.minimum, "maximum": self.maximum}


@dataclass
class InputSpec:
    """One value a stage needs from the user."""

    key: str
    name: str
    kind: str  # number | text | boolean | choice | file | table
    describe: str = ""
    unit: str = ""
    required: bool = True
    choices: tuple = ()
    default: Any = None
    fields: tuple = ()  # table: the required numeric columns of each row


@dataclass
class MetricSpec:
    """One transparent quality metric of a stage.

    ``compute`` receives the step's values; with ``needs_workflow`` it also
    receives the workflow (for metrics that read another stage's values).
    """

    key: str
    name: str
    unit: str
    describe: str
    compute: Callable[..., tuple[float | None, str]]
    limits: MetricLimits = field(default_factory=MetricLimits)
    needs_workflow: bool = False


@dataclass
class StepSpec:
    """One stage of a calibration workflow.

    ``requires`` names earlier stages by id (or library spec id). ``guards``
    are stage-specific blockers computed from the live workflow (the guard
    returns a message, or ``None``). ``result_builders`` produce the measured
    results recorded on confirmation.
    """

    id: str
    spec_id: str
    name: str
    goal: str
    instructions: str
    inputs: list[InputSpec] = field(default_factory=list)
    metrics: list[MetricSpec] = field(default_factory=list)
    requires: tuple[str, ...] = ()
    reference: str = ""
    skippable: bool = False
    guards: tuple[Callable[["CalibrationWorkflow", "StepSpec"], str | None], ...] = ()
    result_builders: tuple[Callable[["CalibrationWorkflow", "StepSpec"], list], ...] = ()

    def input(self, key: str) -> InputSpec | None:
        for spec in self.inputs:
            if spec.key == key:
                return spec
        return None

    def metric(self, key: str) -> MetricSpec | None:
        for spec in self.metrics:
            if spec.key == key:
                return spec
        return None


@dataclass
class StepState:
    """What the user has done with one stage so far."""

    values: dict = field(default_factory=dict)
    confirmed: bool = False
    confirmed_at: str = ""
    note: str = ""
    warnings: list[str] = field(default_factory=list)
    skip_reason: str = ""

    @property
    def skipped(self) -> bool:
        return bool(self.skip_reason)

    @property
    def state(self) -> str:
        if self.confirmed:
            return "confirmed"
        if self.skipped:
            return "skipped"
        wf = getattr(self, "_workflow", None)
        step_id = getattr(self, "_step_id", "")
        if wf is not None and wf.prerequisites_met(step_id):
            return "ready"
        return "pending"


@dataclass
class MeasuredResult:
    """A calibration as it was measured: value, provenance, evidence."""

    quantity: str
    value: float | None
    unit: str
    step_id: str
    step_name: str
    source: str  # entered | computed | fitted
    measured_at: str
    sample: str = ""
    file: str = ""
    note: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "quantity": self.quantity, "value": self.value, "unit": self.unit,
            "step_id": self.step_id, "step_name": self.step_name, "source": self.source,
            "measured_at": self.measured_at, "sample": self.sample, "file": self.file,
            "note": self.note, "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, doc: dict) -> "MeasuredResult":
        return cls(
            quantity=doc["quantity"], value=doc["value"], unit=doc.get("unit", ""),
            step_id=doc.get("step_id", ""), step_name=doc.get("step_name", ""),
            source=doc.get("source", ""), measured_at=doc.get("measured_at", ""),
            sample=doc.get("sample", ""), file=doc.get("file", ""),
            note=doc.get("note", ""), extra=dict(doc.get("extra", {})),
        )


class CalibrationWorkflow:
    """An editable calibration workflow and its state.

    Parameters
    ----------
    kind, name : the workflow kind (``fret``, ``polarization``, ``power_diode``) and title.
    steps : the ordered :class:`StepSpec` list (fresh instances from the library).
    inventory : :class:`~.lasers.LaserInventory` or ``None``
        Needed by the power workflow's guards; owned (and persisted) by the host,
        not by this workflow.
    """

    def __init__(
        self,
        kind: str,
        name: str,
        steps: list[StepSpec],
        inventory=None,
    ) -> None:
        self.kind = kind
        self.name = name
        self.inventory = inventory
        self.steps: list[StepSpec] = []
        self.state: dict[str, StepState] = {}
        self.results: list[MeasuredResult] = []
        for step in steps:
            self._register(step)

    # -- composition ------------------------------------------------------------------------------
    def _register(self, step: StepSpec) -> None:
        if step.id in self.state:
            raise ValueError(f"duplicate step id {step.id!r}")
        self.steps.append(step)
        state = StepState()
        for spec in step.inputs:
            if spec.default is not None:
                state.values[spec.key] = spec.default
        state._workflow = self
        state._step_id = step.id
        self.state[step.id] = state

    def _step(self, step_id: str) -> StepSpec:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(f"no step {step_id!r}")

    def add_step(self, spec: StepSpec, index: int | None = None) -> StepSpec:
        """Add a stage (a fresh spec from the library, or a custom one). A taken
        id is suffixed ``#2``, ``#3``, ..."""
        if spec.id in self.state:
            n = 2
            while f"{spec.id}#{n}" in self.state:
                n += 1
            spec = StepSpec(
                id=f"{spec.id}#{n}", spec_id=spec.spec_id or spec.id, name=spec.name,
                goal=spec.goal, instructions=spec.instructions, inputs=spec.inputs,
                metrics=spec.metrics, requires=spec.requires, reference=spec.reference,
                skippable=spec.skippable, guards=spec.guards,
                result_builders=spec.result_builders,
            )
        self._register(spec)
        if index is not None:
            self.steps.remove(spec)
            self.steps.insert(max(0, min(int(index), len(self.steps) - 1)), spec)
        return spec

    def remove_step(self, step_id: str) -> None:
        step = self._step(step_id)
        if self.state[step_id].confirmed:
            raise ValueError(
                f"{step_id} is confirmed; unconfirm it (with a note) before removing it"
            )
        del self.state[step_id]
        self.steps.remove(step)

    def move_step(self, step_id: str, index: int) -> None:
        step = self._step(step_id)
        index = max(0, min(int(index), len(self.steps) - 1))
        self.steps.remove(step)
        self.steps.insert(index, step)

    # -- values -----------------------------------------------------------------------------------
    def set_value(self, step_id: str, key: str, value: Any) -> None:
        state = self.state[step_id]
        if state.confirmed:
            raise StepConfirmed(
                f"{step_id} is confirmed; unconfirm it (with a note) before editing"
            )
        step = self._step(step_id)
        spec = step.input(key)
        if spec is None:
            raise ValueError(f"{step_id} has no input {key!r}")
        state.values[key] = self._cast(spec, value)

    def set_points(self, step_id: str, key: str, rows) -> None:
        """Convenience for table inputs: the measured points, entered as rows."""
        step = self._step(step_id)
        spec = step.input(key)
        if spec is None or spec.kind != "table":
            raise ValueError(f"{step_id} has no table input {key!r}")
        state = self.state[step_id]
        if state.confirmed:
            raise StepConfirmed(
                f"{step_id} is confirmed; unconfirm it (with a note) before editing"
            )
        state.values[key] = self._cast(spec, rows)

    def _cast(self, spec: InputSpec, value: Any) -> Any:
        if spec.kind == "number":
            try:
                return float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{spec.name} must be a number") from None
        if spec.kind == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)) and value in (0, 1):
                return bool(value)
            text = str(value).strip().lower()
            if text in ("true", "yes", "1", "on"):
                return True
            if text in ("false", "no", "0", "off"):
                return False
            raise ValueError(f"{spec.name} must be a yes/no value")
        if spec.kind == "choice":
            if value in spec.choices:
                return value
            for choice in spec.choices:
                try:
                    if type(choice)(value) == choice:
                        return choice
                except (TypeError, ValueError):
                    continue
            raise ValueError(
                f"{spec.name} must be one of {list(spec.choices)} (only lasers verified "
                "installed may be selected)"
                if spec.key == "laser_nm"
                else f"{spec.name} must be one of {list(spec.choices)}"
            )
        if spec.kind == "table":
            return self._cast_table(spec, value)
        # text / file
        text = str(value)
        return os.path.expanduser(text) if spec.kind == "file" else text

    def _cast_table(self, spec: InputSpec, value: Any) -> list[dict]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"{spec.name} is not valid JSON") from None
        if not isinstance(value, list):
            raise ValueError(f"{spec.name} must be a list of rows")
        rows = []
        for i, row in enumerate(value, 1):
            if not isinstance(row, Mapping):
                raise ValueError(f"row {i} is not a mapping of {list(spec.fields)}")
            out = {}
            for field_name in spec.fields:
                if field_name not in row:
                    raise ValueError(f"row {i} is missing {field_name!r}")
                try:
                    out[field_name] = float(row[field_name])
                except (TypeError, ValueError):
                    raise ValueError(f"row {i}: {field_name!r} is not a number") from None
            rows.append(out)
        return rows

    # -- limits -----------------------------------------------------------------------------------
    def configure_limits(self, step_id: str, metric_key: str, *, minimum: float | None = None,
                         maximum: float | None = None) -> None:
        """Set the user's accept/reject bounds on one metric (at least one bound)."""
        step = self._step(step_id)
        metric = step.metric(metric_key)
        if metric is None:
            raise KeyError(f"{step_id} has no metric {metric_key!r}")
        if minimum is None and maximum is None:
            raise ValueError("no bounds given: set minimum and/or maximum")
        metric.limits.minimum = None if minimum is None else float(minimum)
        metric.limits.maximum = None if maximum is None else float(maximum)

    def clear_limits(self, step_id: str, metric_key: str) -> None:
        step = self._step(step_id)
        metric = step.metric(metric_key)
        if metric is None:
            raise KeyError(f"{step_id} has no metric {metric_key!r}")
        metric.limits = MetricLimits()

    # -- readiness --------------------------------------------------------------------------------
    def _requirement_satisfied(self, requirement: str) -> bool:
        for other in self.steps:
            if other.id == requirement or other.spec_id == requirement:
                state = self.state[other.id]
                if state.confirmed or state.skipped:
                    return True
        return False

    def prerequisites_met(self, step_id: str) -> bool:
        step = self._step(step_id)
        return all(self._requirement_satisfied(r) for r in step.requires)

    def _has_value(self, values: Mapping, spec: InputSpec) -> bool:
        if spec.key not in values:
            return False
        value = values[spec.key]
        if value is None or (isinstance(value, str) and not value.strip()):
            return False
        if spec.kind == "table" and isinstance(value, (list, tuple)) and not value:
            return False
        return True

    def blockers(self, step_id: str) -> list[str]:
        step = self._step(step_id)
        state = self.state[step_id]
        out = []
        for requirement in step.requires:
            if not self._requirement_satisfied(requirement):
                names = [o.name for o in self.steps
                         if o.id == requirement or o.spec_id == requirement]
                where = names[0] if names else "not in the workflow (removed?)"
                out.append(
                    f"requires {requirement} ({where}) to be confirmed or skipped first"
                )
        for spec in step.inputs:
            if spec.required and not self._has_value(state.values, spec):
                out.append(f"missing input {spec.key!r} ({spec.name})")
            elif spec.kind == "file" and self._has_value(state.values, spec):
                path = str(state.values[spec.key])
                if not os.path.isfile(path):
                    out.append(f"the file {path} does not exist")
        for guard in step.guards:
            message = guard(self, step)
            if message:
                out.append(message)
        return out

    def can_confirm(self, step_id: str) -> tuple[bool, list[str]]:
        state = self.state[step_id]
        if state.confirmed:
            return False, [f"{step_id} is already confirmed"]
        if state.skipped:
            return False, [f"{step_id} is skipped ({state.skip_reason})"]
        blockers = self.blockers(step_id)
        return not blockers, blockers

    # -- metrics ----------------------------------------------------------------------------------
    def metrics(self, step_id: str) -> list[dict]:
        step = self._step(step_id)
        values = self.state[step_id].values
        out = []
        for metric in step.metrics:
            try:
                if metric.needs_workflow:
                    value, detail = metric.compute(values, self)
                else:
                    value, detail = metric.compute(values)
            except Exception as exc:  # noqa: BLE001 - a broken metric is shown, not raised
                value, detail = None, f"{type(exc).__name__}: {exc}"
            if value is None:
                verdict = "not computable"
            elif metric.limits.is_empty():
                verdict = "not configured"
            elif (metric.limits.minimum is not None and value < metric.limits.minimum) or (
                metric.limits.maximum is not None and value > metric.limits.maximum
            ):
                verdict = "outside bounds"
            else:
                verdict = "within bounds"
            out.append(
                {
                    "key": metric.key, "name": metric.name, "unit": metric.unit,
                    "describe": metric.describe, "value": value, "detail": detail,
                    "verdict": verdict, "limits": metric.limits.to_dict(),
                    "limits_text": metric.limits.describe(),
                }
            )
        return out

    # -- confirmations ----------------------------------------------------------------------------
    def confirm(self, step_id: str, note: str = "") -> list[MeasuredResult]:
        ok, blockers = self.can_confirm(step_id)
        if not ok:
            raise ValueError(
                f"cannot confirm {step_id}: " + "; ".join(blockers)
            )
        step = self._step(step_id)
        state = self.state[step_id]
        outside = [m["key"] for m in self.metrics(step_id) if m["verdict"] == "outside bounds"]
        results: list[MeasuredResult] = []
        for build in step.result_builders:
            results.extend(build(self, step))
        state.confirmed = True
        state.confirmed_at = _now_iso()
        state.note = note
        state.warnings = outside
        self.results.extend(results)
        return results

    def unconfirm(self, step_id: str, note: str = "") -> list[str]:
        """Reopen a stage; every stage that consumed its results reopens too."""
        state = self.state[step_id]
        if not state.confirmed:
            raise ValueError(f"{step_id} is not confirmed")
        affected = [step_id]
        frontier = [step_id]
        while frontier:
            current = frontier.pop()
            for other in self.steps:
                if other.id in affected or not self.state[other.id].confirmed:
                    continue
                depends = any(
                    r == current or r == self._step(current).spec_id
                    for r in other.requires
                )
                if depends:
                    self.state[other.id].confirmed = False
                    self.state[other.id].note = (
                        (self.state[other.id].note + " | " if self.state[other.id].note else "")
                        + f"reopened: prerequisite {current} was unconfirmed"
                    )
                    self.state[other.id].warnings = []
                    affected.append(other.id)
                    frontier.append(other.id)
        state.confirmed = False
        state.note = note
        state.warnings = []
        self.results = [r for r in self.results if r.step_id not in affected]
        return affected

    def skip(self, step_id: str, reason: str) -> None:
        step = self._step(step_id)
        state = self.state[step_id]
        if state.confirmed:
            raise ValueError(f"{step_id} is confirmed; unconfirm it before skipping")
        if not step.skippable:
            raise ValueError(f"{step_id} is not skippable")
        if not str(reason).strip():
            raise ValueError("a skip needs a reason")
        state.skip_reason = str(reason)

    def unskip(self, step_id: str) -> None:
        state = self.state[step_id]
        if not state.skipped:
            raise ValueError(f"{step_id} is not skipped")
        state.skip_reason = ""

    # -- suggested values from earlier stages ------------------------------------------------------
    def suggested_values(self, step_id: str) -> dict:
        """Recorded results that match the stage's input keys (e.g. alpha, delta)."""
        latest: dict[str, MeasuredResult] = {}
        for result in self.results:
            latest[result.quantity] = result
        step = self._step(step_id)
        out = {}
        for spec in step.inputs:
            result = latest.get(spec.key)
            if result is not None and result.value is not None:
                out[spec.key] = result.value
        return out

    def adopt_suggestions(self, step_id: str) -> dict:
        """Fill unset inputs from the recorded results (never overrides the user)."""
        adopted = {}
        for key, value in self.suggested_values(step_id).items():
            if key not in self.state[step_id].values:
                self.set_value(step_id, key, value)
                adopted[key] = value
        return adopted

    # -- reporting ---------------------------------------------------------------------------------
    def status(self, step_id: str) -> dict:
        step = self._step(step_id)
        state = self.state[step_id]
        raw = state.state
        state_name = raw
        if raw == "pending" and self.prerequisites_met(step_id):
            state_name = "ready"
        return {
            "id": step.id, "spec_id": step.spec_id, "name": step.name,
            "goal": step.goal, "instructions": step.instructions,
            "requires": list(step.requires), "skippable": step.skippable,
            "reference": step.reference,
            "state": state_name,
            "blockers": self.blockers(step_id) if state_name in ("pending", "ready") else [],
            "values": dict(state.values),
            "metrics": self.metrics(step_id),
            "warnings": list(state.warnings),
            "confirmed_at": state.confirmed_at,
            "note": state.note,
            "skip_reason": state.skip_reason,
        }

    def overview(self) -> dict:
        steps = [self.status(step.id) for step in self.steps]
        complete = all(s["state"] in ("confirmed", "skipped") for s in steps)
        return {
            "kind": self.kind, "name": self.name,
            "overall": "complete" if complete else "in progress",
            "steps": steps,
        }

    def summary(self) -> dict:
        """The latest measured result per quantity, as dicts with provenance."""
        latest: dict[str, MeasuredResult] = {}
        for result in self.results:
            latest[result.quantity] = result
        return {q: r.to_dict() for q, r in latest.items()}

    def latest(self, quantity: str) -> MeasuredResult | None:
        found = None
        for result in self.results:
            if result.quantity == quantity:
                found = result
        return found

    # -- persistence --------------------------------------------------------------------------------
    def save(self, path: str | Path) -> None:
        doc = {
            "format": FORMAT,
            "version": VERSION,
            "kind": self.kind,
            "name": self.name,
            "steps": [{"id": s.id, "spec_id": s.spec_id} for s in self.steps],
            "state": {
                s.id: {
                    "values": self.state[s.id].values,
                    "confirmed": self.state[s.id].confirmed,
                    "confirmed_at": self.state[s.id].confirmed_at,
                    "note": self.state[s.id].note,
                    "warnings": list(self.state[s.id].warnings),
                    "skip_reason": self.state[s.id].skip_reason,
                }
                for s in self.steps
            },
            "limits": {
                s.id: {
                    m.key: m.limits.to_dict()
                    for m in s.metrics
                    if not m.limits.is_empty()
                }
                for s in self.steps
                if any(not m.limits.is_empty() for m in s.metrics)
            },
            "results": [r.to_dict() for r in self.results],
        }
        Path(path).write_text(json.dumps(doc, indent=2))

    @classmethod
    def load(cls, path: str | Path, inventory=None) -> "CalibrationWorkflow":
        from . import library  # local import: the library imports this module

        doc = json.loads(Path(path).read_text())
        if doc.get("format") != FORMAT:
            raise ValueError(f"{path} is not a {FORMAT} document")
        steps = []
        for entry in doc.get("steps", []):
            spec_id = entry.get("spec_id", "")
            try:
                spec = library.step_spec(spec_id)
            except KeyError:
                raise ValueError(
                    f"unknown step spec {spec_id!r}: the workflow cannot be rebuilt "
                    "without it (was it a custom step?)"
                ) from None
            spec.id = entry["id"]
            steps.append(spec)
        wf = cls(doc.get("kind", ""), doc.get("name", ""), steps, inventory=inventory)
        for step_id, saved in doc.get("state", {}).items():
            if step_id not in wf.state:
                continue
            state = wf.state[step_id]
            state.values = dict(saved.get("values", {}))
            state.confirmed = bool(saved.get("confirmed", False))
            state.confirmed_at = saved.get("confirmed_at", "")
            state.note = saved.get("note", "")
            state.warnings = list(saved.get("warnings", []))
            state.skip_reason = saved.get("skip_reason", "")
        for step_id, metric_limits in doc.get("limits", {}).items():
            for metric_key, limits in metric_limits.items():
                step = next((s for s in wf.steps if s.id == step_id), None)
                metric = step.metric(metric_key) if step else None
                if metric is not None:
                    metric.limits = MetricLimits(**limits)
        wf.results = [MeasuredResult.from_dict(r) for r in doc.get("results", [])]
        return wf

import inspect
import pathlib
import unittest

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import chisurf as cs
from chisurf.core.actions._infra import ActionDispatcher, ActionRegistry, ActionSpec

# The parameter actions that are debounced and address a fit by ``fit_index``.
FIT_SCOPED_ACTIONS = (
    "parameter.value",
    "parameter.fixed",
    "parameter.bounds.set",
    "parameter.bounds.on",
    "parameter.unlink",
)


class TestDebounceIdentityIsFitScoped(unittest.TestCase):
    """The debounce identity of a per-fit action has to include the fit.

    ``debounce_keys`` defines *which* calls count as repeats of each other.  An
    action whose handler targets ``cs.fits[fit_index]`` but whose identity is the
    parameter name alone makes two different fits share one debounce slot, so a
    write to the second fit is swallowed as a duplicate of the first.
    """

    def _real_spec(self, name: str) -> ActionSpec:
        spec = cs.action_registry.get(name)
        self.assertIsNotNone(spec, f"action {name!r} is not registered")
        return spec

    def test_fit_scoped_actions_carry_fit_index_in_their_identity(self):
        for name in FIT_SCOPED_ACTIONS:
            with self.subTest(action=name):
                spec = self._real_spec(name)
                self.assertGreater(spec.debounce_ms, 0)
                self.assertIn(
                    "fit_index",
                    inspect.signature(spec.handler).parameters,
                    "handler no longer targets a fit by index — update this test",
                )
                self.assertIsNotNone(spec.debounce_keys)
                self.assertIn("fit_index", spec.debounce_keys)

    def test_two_fits_do_not_share_one_debounce_slot(self):
        """Writes to two fits inside the window both run; a true repeat coalesces."""
        for name in ("parameter.value", "parameter.fixed"):
            with self.subTest(action=name):
                real = self._real_spec(name)
                calls = []
                reg = ActionRegistry()
                reg.register(
                    ActionSpec(
                        name=real.name,
                        schema=real.schema,
                        debounce_ms=real.debounce_ms,
                        debounce_keys=real.debounce_keys,
                        handler=lambda **kw: calls.append(kw),
                    )
                )
                dispatcher = ActionDispatcher(registry=reg, history_provider=lambda: None)
                self.addCleanup(self._cancel_pending, dispatcher)

                payload = {"parameter_name": "tau1", "value": 1.0, "fixed": True, "fit_index": 0}
                dispatcher.execute(name=real.name, payload=dict(payload))
                dispatcher.execute(name=real.name, payload=dict(payload, fit_index=1))
                self.assertEqual([0, 1], [c["fit_index"] for c in calls])

                # Same parameter, same fit → a genuine repeat, still debounced.
                dispatcher.execute(name=real.name, payload=dict(payload, fit_index=1))
                self.assertEqual(2, len(calls))

    @staticmethod
    def _cancel_pending(dispatcher: ActionDispatcher) -> None:
        """Cancel the trailing-edge timers a debounced call leaves behind."""
        for timer in list(dispatcher._pending_timers.values()):
            timer.cancel()


if __name__ == "__main__":
    unittest.main()

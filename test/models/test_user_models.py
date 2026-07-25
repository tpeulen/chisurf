"""User-supplied model code: the ``__override__`` injection mechanism.

This file used to test a registry — ``register_user_model``,
``load_user_models``, ``iter_user_models_for_experiment`` and a
``_user_model_registry`` dict. None of those has ever existed: ``git log -S``
over the whole history finds no commit that added or removed them, and the
documentation page describing the same registry was rewritten against the real
mechanism in ``43e60f7f3``. The tests were asserting an API that was only ever
imagined, so they failed on an ``AttributeError`` before reaching an assertion.

What the code actually offers is two things:

* :func:`chisurf.core.models.inject_user_models`, run once at import, which
  execs user files named ``<dotted.module>__override__<timestamp>.py`` into the
  namespace of the module they name. That is what these tests cover.
* Adding a whole model class by naming its dotted path under ``models:`` in
  ``~/.chisurf/experiment_configs.yaml``, resolved by ``Main._resolve_class``.
  That path lives on the GUI class and is out of scope for this non-GUI suite.
"""

import importlib
import os
import pathlib
import sys
import unittest

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import chisurf.core.models


class TestInjectUserModels(unittest.TestCase):
    """``inject_user_models`` execs override files into their target module."""

    def setUp(self):
        """A scratch settings dir, and an importable module to be overridden."""
        from test import utils as test_utils

        self._tmp = test_utils.temporary_directory()
        self.settings_dir = pathlib.Path(self._tmp.__enter__())
        self.models_dir = self.settings_dir / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # The override target must be importable, since inject_user_models
        # resolves it with importlib.import_module before exec'ing into it.
        self.module_name = "chisurf_user_model_target"
        (self.settings_dir / f"{self.module_name}.py").write_text(
            "ORIGINAL = 'packaged'\n", encoding="utf-8"
        )
        sys.path.insert(0, str(self.settings_dir))
        self.target = importlib.import_module(self.module_name)

        self._settings_override = os.environ.get("CHISURF_SETTINGS_DIR")
        os.environ["CHISURF_SETTINGS_DIR"] = str(self.settings_dir)

    def tearDown(self):
        """Undo the settings redirection, the path entry and the import."""
        if self._settings_override is None:
            os.environ.pop("CHISURF_SETTINGS_DIR", None)
        else:
            os.environ["CHISURF_SETTINGS_DIR"] = self._settings_override
        sys.modules.pop(self.module_name, None)
        if str(self.settings_dir) in sys.path:
            sys.path.remove(str(self.settings_dir))
        self._tmp.__exit__(None, None, None)

    def _write_override(self, timestamp, body):
        """Place one ``<module>__override__<timestamp>.py`` file."""
        path = self.models_dir / f"{self.module_name}__override__{timestamp}.py"
        path.write_text(body, encoding="utf-8")
        return path

    def test_override_is_executed_in_the_target_module_namespace(self):
        """The file's definitions land in the module it names, replacing its own.

        Exec'ing into ``module.__dict__`` is what makes an override an override:
        the new definition is visible to every existing reference to that
        module, not just to whoever imports the user's file.
        """
        self._write_override(
            "20260101",
            "ORIGINAL = 'overridden'\n"
            "def added_by_user():\n"
            "    return 42\n",
        )
        chisurf.core.models.inject_user_models()

        self.assertEqual(self.target.ORIGINAL, "overridden")
        self.assertEqual(self.target.added_by_user(), 42)
        # The same object, so code holding a reference sees the override too.
        self.assertIs(sys.modules[self.module_name], self.target)

    def test_only_the_newest_timestamp_is_applied(self):
        """Several overrides of one module collapse to the latest timestamp.

        The timestamps are compared as strings, so the fixed-width form the
        editor writes orders correctly; that is the property being pinned.
        """
        self._write_override("20260101", "ORIGINAL = 'older'\n")
        self._write_override("20260601", "ORIGINAL = 'newer'\n")
        self._write_override("20260301", "ORIGINAL = 'middle'\n")

        chisurf.core.models.inject_user_models()
        self.assertEqual(self.target.ORIGINAL, "newer")

    def test_plain_python_files_are_ignored(self):
        """A ``.py`` without ``__override__`` in its name is not imported.

        Worth stating because the mechanism is easy to misread as "everything in
        ~/.chisurf/models gets loaded" — it is not, and a file dropped there
        under any other name does nothing at all.
        """
        (self.models_dir / "just_a_module.py").write_text(
            "raise AssertionError('this file must never be executed')\n",
            encoding="utf-8",
        )
        chisurf.core.models.inject_user_models()
        self.assertEqual(self.target.ORIGINAL, "packaged")

    def test_a_broken_override_is_logged_and_does_not_propagate(self):
        """One bad user file must not stop startup, or the app will not open.

        ``inject_user_models`` runs at import of ``chisurf.core.models``, so an
        exception escaping it makes chisurf unimportable until the user finds
        and deletes the file by hand.
        """
        self._write_override("20260101", "this is not valid python(\n")
        try:
            chisurf.core.models.inject_user_models()
        except Exception as exception:  # pragma: no cover - the failure we guard
            self.fail(f"a broken override escaped inject_user_models: {exception!r}")
        self.assertEqual(self.target.ORIGINAL, "packaged")

    def test_missing_models_directory_is_not_an_error(self):
        """Most installations have no ``models`` folder; that is the normal case."""
        import shutil

        shutil.rmtree(self.models_dir)
        chisurf.core.models.inject_user_models()
        self.assertEqual(self.target.ORIGINAL, "packaged")


if __name__ == "__main__":
    unittest.main()

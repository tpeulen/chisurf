import contextlib
import os
import shutil
import sys
import tempfile
import unittest

# If we're using Python 2.6, add in more modern unittest convenience methods
if not hasattr(unittest.TestCase, "assertIn"):

    def assertIn(self, member, container, msg=None):
        return self.assertTrue(member in container, msg or f"{member} not found in {container}")

    def assertNotIn(self, member, container, msg=None):
        return self.assertTrue(
            member not in container, msg or f"{member} unexpectedly found in {container}"
        )

    def assertIsInstance(self, obj, cls, msg=None):
        return self.assertTrue(isinstance(obj, cls), msg or f"{obj} is not an instance of {cls}")

    def assertLessEqual(self, a, b, msg=None):
        return self.assertTrue(a <= b, msg or f"{a} not less than or equal to {b}")

    def assertGreaterEqual(self, a, b, msg=None):
        return self.assertTrue(a >= b, msg or f"{a} not greater than or equal to {b}")

    unittest.TestCase.assertIn = assertIn
    unittest.TestCase.assertNotIn = assertNotIn
    unittest.TestCase.assertIsInstance = assertIsInstance
    unittest.TestCase.assertLessEqual = assertLessEqual
    unittest.TestCase.assertGreaterEqual = assertGreaterEqual


def set_search_paths(topdir):
    """Set search paths so that we can import Python modules"""
    os.environ["PYTHONPATH"] = str(topdir) + os.pathsep + os.environ.get("PYTHONPATH", "")
    sys.path.insert(0, topdir)


def get_input_file_name(topdir, fname):
    """Return full path to a test input file"""
    return os.path.join(topdir, "test", "input", fname)


@contextlib.contextmanager
def temporary_directory(dir=None):
    _tmpdir = tempfile.mkdtemp(dir=dir)
    yield _tmpdir
    shutil.rmtree(_tmpdir, ignore_errors=True)


if "coverage" in sys.modules:
    import atexit

    # Collect coverage information from subprocesses
    __site_tmpdir = tempfile.mkdtemp()
    with open(os.path.join(__site_tmpdir, "sitecustomize.py"), "w") as fh:
        fh.write(
            f"""
import coverage
import atexit
import os

_cov = coverage.coverage(branch=True, data_suffix=True, auto_data=True,
                         data_file=os.path.join('{os.getcwd()}', '.coverage'))
_cov.start()

def _coverage_cleanup(c):
    c.stop()
atexit.register(_coverage_cleanup, _cov)
"""
        )

    os.environ["PYTHONPATH"] = __site_tmpdir + os.pathsep + os.environ.get("PYTHONPATH", "")

    def __cleanup(d):
        shutil.rmtree(d, ignore_errors=True)

    atexit.register(__cleanup, __site_tmpdir)

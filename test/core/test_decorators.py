import utils
import unittest
import pathlib
import warnings

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)


import chisurf.core.support.decorators

DeprecatedWarning = chisurf.core.support.decorators.DeprecatedWarning
UnsupportedWarning = chisurf.core.support.decorators.UnsupportedWarning
deprecated = chisurf.core.support.decorators.deprecated
_deprecation_state = chisurf.core.support.decorators._deprecation_state
_running_version = chisurf.core.support.decorators._running_version
_version_key = chisurf.core.support.decorators._version_key


def _warn_of(function, *args, **kwargs):
    """Call ``function`` and return the single warning it raised, if any."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        function(*args, **kwargs)
    return caught[0].message if caught else None


class Tests(unittest.TestCase):

    def test_register(self):
        @chisurf.core.support.decorators.register
        class A1():
            pass

        @chisurf.core.support.decorators.register
        class B():
            pass

        @chisurf.core.support.decorators.register
        class A2(A1):
            pass

        class A3(A1):
            pass

        a1_1 = A1()
        a1_2 = A1()
        a2_1 = A2()
        a3_1 = A3()
        b = B()
        self.assertEqual(
            a1_2 in a1_1.get_instances(),
            True
        )
        self.assertEqual(
            a2_1 in a1_1.get_instances(),
            False
        )
        self.assertEqual(
            a3_1 in a1_1.get_instances(),
            True
        )
        self.assertEqual(
            b in a1_1.get_instances(),
            False
        )

    def test_set_module(self):
        name = 'test_module_name'
        @chisurf.core.support.decorators.set_module(name)
        def example():
            pass
        self.assertEqual(
            example.__module__,
            name
        )


class DeprecationTests(unittest.TestCase):
    """Pin the version bookkeeping of :func:`chisurf.core.support.decorators.deprecated`."""

    def test_version_key_orders_dev_below_release(self):
        self.assertLess(_version_key("20.01.01"), _version_key("26.dev4401"))
        self.assertLess(_version_key("26.dev0"), _version_key("26.1"))
        self.assertLess(_version_key("19.10.31"), _version_key("20.01.01"))

    def test_deprecation_state_reaches_the_unsupported_branch(self):
        self.assertEqual(
            _deprecation_state("19.10.31", "20.01.01", "26.dev4401"), (True, True)
        )
        self.assertEqual(
            _deprecation_state("19.10.31", "20.01.01", "19.11.01"), (True, False)
        )
        self.assertEqual(
            _deprecation_state("27.01.01", None, "26.dev4401"), (False, False)
        )

    def test_running_version_is_the_default(self):
        # RF-662: the default used to be None, which short-circuited the
        # comparison and made UnsupportedWarning unreachable from any
        # decoration in the tree.
        self.assertIsNotNone(_running_version())

        @deprecated(deprecated_in="19.10.31", removed_in="20.01.01")
        def past_its_removal():
            """Do nothing."""

        message = _warn_of(past_its_removal)
        self.assertIsInstance(message, UnsupportedWarning)
        self.assertEqual(str(message), "past_its_removal is unsupported as of 20.01.01.")

    def test_before_the_removal_version_warns_as_deprecated(self):
        @deprecated(
            deprecated_in="19.10.31",
            removed_in="20.01.01",
            current_version="19.11.01",
            details="Use tttrlib instead",
        )
        def not_yet_removed():
            """Do nothing."""

        message = _warn_of(not_yet_removed)
        self.assertIsInstance(message, DeprecatedWarning)
        self.assertNotIsInstance(message, UnsupportedWarning)
        self.assertIn("will be removed in 20.01.01", str(message))

    def test_future_deprecation_stays_silent(self):
        @deprecated(deprecated_in="99.01.01")
        def not_yet_deprecated():
            """Do nothing."""

        self.assertIsNone(_warn_of(not_yet_deprecated))

    def test_bare_decoration_warns_now(self):
        # ``deprecated_in=None`` documents "deprecated as of now"; that has to
        # hold whether or not a current version is available to compare against.
        @deprecated(details="Use the replacement")
        def deprecated_now():
            """Do nothing."""

        message = _warn_of(deprecated_now)
        self.assertIsInstance(message, DeprecatedWarning)
        self.assertNotIsInstance(message, UnsupportedWarning)

    def test_explicit_none_disables_the_comparison(self):
        @deprecated(deprecated_in="19.10.31", removed_in="20.01.01", current_version=None)
        def no_version_known():
            """Do nothing."""

        message = _warn_of(no_version_known)
        self.assertIsInstance(message, DeprecatedWarning)
        self.assertNotIsInstance(message, UnsupportedWarning)

    def test_removed_in_needs_deprecated_in(self):
        with self.assertRaises(TypeError):
            deprecated(removed_in="20.01.01")

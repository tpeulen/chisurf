"""Tests for the process-global out-of-fit parameter-group registry.

See :mod:`chisurf.core.registry.parameter_groups`.
"""

import gc
import pathlib
import unittest

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import chisurf.core.fitting.parameter as fp
import chisurf.core.models  # noqa: F401
import chisurf.core.parameter  # noqa: F401  (initialises chisurf.core.settings)
from chisurf.core.registry import parameter_groups as reg


def _make_group(names):
    """Build a FittingParameterGroup carrying one FittingParameter per name."""
    group = fp.FittingParameterGroup()
    for n in names:
        setattr(group, "_" + n, fp.FittingParameter(value=1.0, name=n))
    group.find_parameters()
    return group


class RegistryTests(unittest.TestCase):
    def setUp(self):
        for owner_id, _label, _group in list(reg.iter_registered_parameter_groups()):
            reg.unregister_parameter_group(owner_id)

    def tearDown(self):
        self.setUp()

    def test_register_and_iter(self):
        g = _make_group(["a", "b"])
        reg.register_parameter_group(g, owner_id="tool1", label="Tool One")
        entries = reg.iter_registered_parameter_groups()
        self.assertEqual(len(entries), 1)
        owner_id, label, group = entries[0]
        self.assertEqual(owner_id, "tool1")
        self.assertEqual(label, "Tool One")
        self.assertIs(group, g)
        self.assertIs(reg.get_registered_parameter_group("tool1"), g)

    def test_empty_owner_id_rejected(self):
        g = _make_group(["a"])
        with self.assertRaises(ValueError):
            reg.register_parameter_group(g, owner_id="", label="x")

    def test_reregister_replaces(self):
        g1 = _make_group(["a"])
        g2 = _make_group(["b"])
        reg.register_parameter_group(g1, owner_id="tool", label="v1")
        reg.register_parameter_group(g2, owner_id="tool", label="v2")
        entries = reg.iter_registered_parameter_groups()
        self.assertEqual(len(entries), 1)
        self.assertIs(entries[0][2], g2)
        self.assertEqual(entries[0][1], "v2")

    def test_unregister_removes(self):
        g = _make_group(["a"])
        reg.register_parameter_group(g, owner_id="tool", label="x")
        reg.unregister_parameter_group("tool")
        self.assertEqual(reg.iter_registered_parameter_groups(), [])
        reg.unregister_parameter_group("unknown")  # no error

    def test_weakref_eviction(self):
        g = _make_group(["a"])
        reg.register_parameter_group(g, owner_id="tool", label="x")
        del g
        gc.collect()
        self.assertEqual(reg.iter_registered_parameter_groups(), [])
        self.assertIsNone(reg.get_registered_parameter_group("tool"))

    def test_change_notification(self):
        calls = []
        cb = reg.subscribe(lambda: calls.append(1))
        try:
            g = _make_group(["a"])
            reg.register_parameter_group(g, owner_id="tool", label="x")
            reg.unregister_parameter_group("tool")
            self.assertEqual(len(calls), 2)
        finally:
            reg.unsubscribe(cb)

    def test_unregister_breaks_inbound_link(self):
        master_group = _make_group(["m"])
        follower_group = _make_group(["f"])
        master = master_group.parameters_all_dict["m"]
        follower = follower_group.parameters_all_dict["f"]

        reg.register_parameter_group(master_group, owner_id="master", label="M")
        reg.register_parameter_group(follower_group, owner_id="follower", label="F")
        follower.link = master
        self.assertTrue(follower.is_linked)

        # Removing the master group must sever the dangling follower link.
        reg.unregister_parameter_group("master")
        self.assertFalse(follower.is_linked)

    def test_unregister_breaks_outbound_link(self):
        master_group = _make_group(["m"])
        follower_group = _make_group(["f"])
        master = master_group.parameters_all_dict["m"]
        follower = follower_group.parameters_all_dict["f"]

        reg.register_parameter_group(master_group, owner_id="master", label="M")
        reg.register_parameter_group(follower_group, owner_id="follower", label="F")
        follower.link = master
        self.assertTrue(follower.is_linked)

        # Removing the follower's own group clears its outbound link.
        reg.unregister_parameter_group("follower")
        self.assertFalse(follower.is_linked)


if __name__ == "__main__":
    unittest.main()

import gc
import unittest

import numpy as np

from chisurf.core import nodes

cn = nodes._bff  # the bff Port/Node runtime that replaced chinet


class TestPortNodeStability(unittest.TestCase):
    """
    Stress test for the port/node runtime (IMP.bff, chinet's successor) to
    verify it is free of access violations and handles heavy node/port
    allocation gracefully.
    """

    def test_massive_port_allocation(self):
        """Allocate many ports and trigger GC to ensure no crashes."""
        print("\nAllocating 20,000 ports...")
        ports = []
        for i in range(20000):
            p = cn.Port(value=float(i))
            ports.append(p)
            if i % 5000 == 0:
                gc.collect()

        self.assertEqual(len(ports), 20000)
        self.assertEqual(ports[1000].value, 1000.0)

        # Clear and force GC
        del ports
        gc.collect()
        print("Port allocation stable.")

    def test_complex_graph_evaluation(self):
        """Create a deep graph and evaluate it many times."""
        print("Building complex graph...")
        root_port = cn.Port(1.0)
        nodes_ = []

        # Create a chain of 1000 nodes
        prev_port = root_port
        for i in range(1000):
            node = cn.Node()
            p_in = cn.Port(0.0)
            p_out = cn.Port(0.0)
            p_in.link = prev_port
            node.add_input_port("in", p_in)
            node.add_output_port("out", p_out)
            nodes_.append(node)
            prev_port = p_out

        print(f"Graph with {len(nodes_)} nodes built. Evaluating...")
        for i in range(10):
            root_port.value = float(i)
            # Linked reads pull through the chain; writing the root
            # propagates to the followers.
            gc.collect()

        print("Graph evaluation stable.")

    def test_random_linking_and_unlinking(self):
        """Randomly link and unlink ports to check for reference cycle leaks or crashes."""
        print("Random linking/unlinking stress test...")
        rng = np.random.default_rng(42)
        ports = [cn.Port(0.0) for _ in range(1000)]
        linked = 0
        for _ in range(5000):
            i, j = rng.integers(0, 1000, size=2)
            if i != j:
                # The runtime enforces the link DAG (LinkCycleError, a
                # ValueError); random pairs sometimes would close a cycle.
                try:
                    ports[i].link = ports[j]
                    linked += 1
                except ValueError:
                    pass
            if _ % 1000 == 0:
                # Randomly break some links
                k = rng.integers(0, 1000)
                ports[k].link = None

        self.assertGreater(linked, 0)
        gc.collect()
        print("Linking stress test stable.")


if __name__ == "__main__":
    unittest.main()

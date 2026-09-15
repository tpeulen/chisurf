import logging

from chisurf.gui.widgets.node_editor.model import PortSpec
from chisurf.gui.widgets.node_editor.registry import NodeRegistry, NodeType

logger = logging.getLogger(__name__)

# Create a local registry for optical nodes to avoid polluting the global math registry
optical_registry = NodeRegistry()


def build_optical_registry():
    """Populates the optical registry if it's empty."""
    if len(optical_registry.all_types()) > 0:
        return
    
    optical_registry.register(NodeType(
        id="light_source",
        title="Light Source",
        inputs=[],
        outputs=[PortSpec("Light", True)],
        category="Optical",
        default_config={
            "source_mode": "manual",
            "probe_id": None,
            "manual_lines": "488:1.0, 640:1.0"
        },
        width=240
    ))
    
    optical_registry.register(NodeType(
        id="sample",
        title="Sample / Fluorophore",
        inputs=[PortSpec("In", False, port_type="spectral")],
        outputs=[
            PortSpec("Out", True, port_type="spectral"),
            PortSpec("Dye Data", True, port_type="dye_data")
        ],
        category="Optical",
        default_config={"probe_ids": [], "probe_id": None},
        width=240
    ))
    
    optical_registry.register(NodeType(
        id="filter",
        title="Filter",
        inputs=[PortSpec("In", False, port_type="spectral")],
        outputs=[PortSpec("Out", True, port_type="spectral")],
        category="Optical",
        default_config={"probe_id": None},
        width=240
    ))
    
    optical_registry.register(NodeType(
        id="splitter",
        title="Splitter (Dichroic/Pol)",
        inputs=[PortSpec("In", False, port_type="spectral")],
        outputs=[
            PortSpec("Transmission", True, port_type="spectral"), 
            PortSpec("Reflection", True, port_type="spectral")
        ],
        category="Optical",
        default_config={"probe_id": None},
        width=240
    ))
    
    optical_registry.register(NodeType(
        id="detector",
        title="Detector",
        inputs=[PortSpec("In", False, port_type="spectral")],
        outputs=[],
        category="Optical",
        default_config={"probe_id": None},
        width=240
    ))
 
    optical_registry.register(NodeType(
        id="combiner",
        title="Combiner",
        inputs=[
            PortSpec("Path 1", False, port_type="spectral"), 
            PortSpec("Path 2", False, port_type="spectral")
        ],
        outputs=[PortSpec("Out", True, port_type="spectral")],
        category="Optical",
        default_config={},
        width=240
    ))

    optical_registry.register(NodeType(
        id="forster_radius",
        title="Förster Radius",
        inputs=[
            PortSpec("Dye Data", False, port_type="dye_data"),
            PortSpec("kappa2", False, port_type="number"),
            PortSpec("n", False, port_type="number")
        ],
        outputs=[],
        category="Analysis",
        default_config={
            "kappa2": 0.6667,
            "n": 1.33,
            "_last_results": []
        },
        width=240
    ))

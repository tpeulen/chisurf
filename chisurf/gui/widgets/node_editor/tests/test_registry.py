"""Unit tests for node type registry."""

import pytest

from chisurf.gui.widgets.node_editor.model import PortSpec
from chisurf.gui.widgets.node_editor.registry import NodeType, registry


def test_registry_register_and_get():
    """Test registering and retrieving node types."""
    # Clear registry for test
    registry._types.clear()

    node_type = NodeType(
        id="test_node",
        title="Test Node",
        inputs=[PortSpec("In", False)],
        outputs=[PortSpec("Out", True)],
        factory=lambda cfg: None,
        default_config={"value": 1},
    )

    registry.register(node_type)
    retrieved = registry.get("test_node")
    assert retrieved == node_type

    assert "test_node" in registry.available_ids()
    assert registry.all_types() == {"test_node": node_type}


def test_registry_duplicate_id():
    """Test that registering duplicate ID raises error."""
    registry._types.clear()

    node_type1 = NodeType(id="dup", title="First", inputs=[], outputs=[], factory=None)
    node_type2 = NodeType(id="dup", title="Second", inputs=[], outputs=[], factory=None)

    registry.register(node_type1)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(node_type2)


def test_registry_get_missing():
    """Test getting non-existent node type."""
    registry._types.clear()
    assert registry.get("missing") is None

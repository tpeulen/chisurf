"""Finding a molecule in a tree of 576 nodes, without disturbing what is drawn.

The nuclear pore's hierarchy has 31 nucleoporins in 544 copies. Scrolling that
to find one is the problem the search box solves — and the thing it must not do
is change the picture. Filtering is about *what the tree lists*; the check boxes
are about what is drawn, and the two must stay independent in both directions.
"""
from __future__ import annotations

import pytest
from qtpy import QtCore

from chisurf.plugins.chimol.chimol.app.hierarchy_panel import HierarchyDock
from chisurf.plugins.chimol.chimol.io.hierarchy import HierarchyNode


@pytest.fixture(scope="module")
def _qt_app():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def dock(_qt_app):
    """A panel holding two molecules of three copies each."""
    root = HierarchyNode(name="Assembly", node_type="ROOT")
    root.atom_indices = list(range(60))
    row = 0
    for mol in ("Nup84", "Nsp1"):
        node = root.add_child(HierarchyNode(name=mol, node_type="MOLECULE"))
        for copy in range(3):
            chain = node.add_child(
                HierarchyNode(name=f"{mol}@{copy}", node_type="CHAIN")
            )
            chain.atom_indices = list(range(row, row + 10))
            node.atom_indices.extend(chain.atom_indices)
            row += 10
    widget = HierarchyDock()
    widget.set_hierarchy(root)
    return widget


def _labels(view, parent=QtCore.QModelIndex()):
    """Every row the view would show, depth first."""
    model = view.model()
    out = []
    for row in range(model.rowCount(parent)):
        index = model.index(row, 0, parent)
        out.append(str(model.data(index)))
        out.extend(_labels(view, index))
    return out


def test_the_search_narrows_the_tree(dock):
    """Typing a molecule name leaves it, its copies and the path to them."""
    assert len(_labels(dock.tree_view)) == 9  # root + 2 molecules + 6 chains

    dock.search_field.setText("Nup84")
    shown = _labels(dock.tree_view)

    assert any("Nup84" in text and "MOLECULE" in text for text in shown)
    assert not any("Nsp1" in text for text in shown), "the other molecule must go"
    # The copies survive because their *ancestor* matched -- a plain row filter
    # would have dropped them and left an empty expandable row.
    assert sum("Nup84@" in text for text in shown) == 3


def test_a_copy_keeps_the_branch_that_leads_to_it(dock):
    """Matching a leaf keeps its parents, or the view has nothing to show it under."""
    dock.search_field.setText("Nsp1@2")
    shown = _labels(dock.tree_view)

    assert any("Assembly" in text for text in shown), "the root must survive"
    assert any("Nsp1" in text and "MOLECULE" in text for text in shown)
    assert sum("Nsp1@" in text for text in shown) == 1


def test_the_search_is_case_insensitive(dock):
    dock.search_field.setText("nUp84")
    assert any("Nup84" in text for text in _labels(dock.tree_view))


def test_no_match_shows_nothing_rather_than_everything(dock):
    """An empty result is empty -- not the unfiltered tree."""
    dock.search_field.setText("does-not-exist")
    assert _labels(dock.tree_view) == []


def test_clearing_the_search_restores_the_whole_tree(dock):
    dock.search_field.setText("Nup84")
    dock.search_field.setText("")
    assert len(_labels(dock.tree_view)) == 9


# --------------------------------------------------------------------------- #
# Filtering and visibility are independent
# --------------------------------------------------------------------------- #
def test_filtering_does_not_change_what_is_drawn(dock):
    """A search must not hide a single bead.

    The tempting implementation -- un-check what does not match -- would make
    typing in a search box silently alter the picture.
    """
    seen = []
    dock.hidden_rows_changed.connect(seen.append)

    dock.search_field.setText("Nup84")
    dock.search_field.setText("")

    assert seen == [], "filtering emitted a visibility change"
    assert list(dock.model.hidden_rows()) == []


def test_unchecking_through_the_filter_still_hides_rows(dock):
    """The check boxes act on the source model, so they work while filtered."""
    dock.search_field.setText("Nup84")

    proxy = dock.tree_view.model()
    root = proxy.index(0, 0, QtCore.QModelIndex())
    molecule = proxy.index(0, 0, root)
    assert "Nup84" in str(proxy.data(molecule))

    proxy.setData(molecule, QtCore.Qt.Unchecked, QtCore.Qt.CheckStateRole)

    # Nup84's three copies of ten rows each.
    assert sorted(dock.model.hidden_rows()) == list(range(30))

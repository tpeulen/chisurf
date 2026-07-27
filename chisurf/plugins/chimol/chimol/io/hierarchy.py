"""The tree a structure is organised into, whoever read it.

A structure is not a flat list of particles, and the file formats this viewer
reads say so in their own vocabularies:

* an **RMF** written by IMP carries ``State`` / ``Molecule`` / ``Copy`` /
  ``Fragment`` / ``Residue`` nodes explicitly -- the hierarchy *is* the file's
  data model;
* an **integrative mmCIF** carries the same shape under different names:
  ``entity`` is the molecule, ``struct_asym`` is the copy of it that appears in
  this assembly, and a sphere covers a ``seq_id`` range of it;
* an ordinary PDB entry has the thin version of it -- chains and residues.

They are the same tree, so they share one node type. The alternative -- a
hierarchy the RMF reader fills and every other reader leaves empty -- is what
made the panel blank for an mmCIF that describes its own organisation in
detail.

A node names itself, says what kind of thing it is, and knows which rows of the
flat coordinate array belong to it. That last part is what makes the tree
useful rather than decorative: it is what lets a click on ``Nup84`` mean
something to the viewer.

Nodes compare by **identity**, not by value: a tree model asks "is this the same
node?" constantly, and a dataclass ``__eq__`` would answer by walking every field
of two whole subtrees -- expensively, and wrongly for two distinct copies of the
same molecule, which are equal field for field.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["HierarchyNode", "NODE_TYPES"]

#: The node kinds in use, loosely following IMP's vocabulary because that is
#: the richer of the two and the mmCIF names map onto it cleanly.
NODE_TYPES = (
    "ROOT",
    "STATE",
    "ASSEMBLY",
    "MOLECULE",
    "CHAIN",
    "FRAGMENT",
    "RESIDUE",
    "PARTICLE",
)


@dataclass(eq=False)
class HierarchyNode:
    """One node of a structure's tree.

    Attributes
    ----------
    name : str
        What to call it: an entity description (``Nup84``), a chain id, a
        residue number. Shown in the hierarchy panel.
    rmf_index : int
        The node's index in the source file when it has one (RMF does), or
        ``-1``. Named for RMF because that is the only format that numbers its
        nodes.
    node_type : str
        One of :data:`NODE_TYPES`.
    children : list of HierarchyNode
        Its children, in file order.
    parent : HierarchyNode or None
        Set when the node is attached; not repeated in ``repr`` so printing a
        tree does not recurse upwards.
    chain_id, res_num, res_type, copy_index, radius
        Structural metadata, where the source has it.
    atom_indices : list of int
        Rows of the object's flat coordinate array that belong to this node,
        *including* those of its descendants. Empty when the node is purely
        organisational.
    """

    name: str
    rmf_index: int = -1
    node_type: str = "PARTICLE"
    children: list[HierarchyNode] = field(default_factory=list)
    parent: HierarchyNode | None = field(default=None, repr=False)
    parent_index: int | None = None

    chain_id: str | None = None
    res_num: int | None = None
    res_type: str | None = None
    copy_index: int | None = None
    radius: float | None = None

    atom_indices: list[int] = field(default_factory=list)

    def add_child(self, child: HierarchyNode) -> HierarchyNode:
        """Attach *child* and return it, so builders can chain.

        Parameters
        ----------
        child : HierarchyNode
            The node to attach.

        Returns
        -------
        HierarchyNode
            The same node, now parented.
        """
        child.parent = self
        self.children.append(child)
        return child

    def descendants(self):
        """Yield every node beneath this one, depth first.

        Yields
        ------
        HierarchyNode
            Each descendant, excluding ``self``.
        """
        for child in self.children:
            yield child
            yield from child.descendants()

    def count(self) -> int:
        """How many nodes the tree holds, counting this one.

        Returns
        -------
        int
            The node count.
        """
        return 1 + sum(1 for _ in self.descendants())

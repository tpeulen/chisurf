from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence, List, Dict, Any, Tuple
import numpy as np
import copy

from .atoms import BEAD_RES_NAME, make_bead_rows
from .hierarchy import HierarchyNode

try:
    import RMF
except ImportError:
    RMF = None

class RmfNotAvailableError(RuntimeError):
    pass

#: The hierarchy node is not RMF's -- an integrative mmCIF describes the same
#: tree in its own vocabulary, and the panel that shows it does not care which
#: reader filled it. It lives in ``io/hierarchy.py``; this name is kept because
#: RMF is where the tree is richest and most of the call sites are here.
RmfHierarchyNode = HierarchyNode

def _residue_numbers(res_nums: Sequence[int], chains: Sequence[str]) -> np.ndarray:
    """Give every bead a residue identity, inventing one only where the file has none.

    A bead's residue number is what the trace and every ``resi`` selection key
    on, and beads that share ``(chain, res_id)`` are treated as one residue --
    so a model whose particles carry no residue index at all would collapse to a
    single trace point per chain. Particles the file *does* number keep their
    number; the rest are numbered sequentially within their chain.

    Parameters
    ----------
    res_nums : sequence of int
        Per particle, the residue index the hierarchy gave, or ``-1``.
    chains : sequence of str
        Per particle, its chain.

    Returns
    -------
    numpy.ndarray
        Residue numbers, one per particle.
    """
    numbers = np.asarray(res_nums, dtype=np.int64)
    missing = numbers < 0
    if not missing.any():
        return numbers

    counters: Dict[str, int] = {}
    filled = numbers.copy()
    for index in np.nonzero(missing)[0]:
        chain = chains[index]
        counters[chain] = counters.get(chain, 0) + 1
        filled[index] = counters[chain]
    return filled


def _varies(frames: np.ndarray) -> bool:
    """Whether a ``(n_frames, ...)`` array is anything other than one repeated.

    Parameters
    ----------
    frames : numpy.ndarray
        Per-frame values.

    Returns
    -------
    bool
        ``False`` for a single frame, or when every frame equals the first.
    """
    # Compared against ``frames[0]``, which broadcasts. Against ``frames[:1]``
    # it does not: ``np.array_equal`` checks shapes first, so a series that
    # never changes reads as one that always does.
    return bool(frames.shape[0] > 1 and not np.all(frames == frames[0]))


class _RmfHierarchyInfo:
    """Track structural information encountered through the RMF hierarchy."""
    def __init__(self):
        self.chain_id = None
        self.copy_index = None
        self.res_num = None
        self.res_type = None
        
    def handle_node(self, node: RMF.NodeConstHandle, loader: _RmfLoader) -> _RmfHierarchyInfo:
        rhi = self
        
        # Chain
        if loader.chainf.get_is(node):
            rhi = copy.copy(rhi)
            c = loader.chainf.get(node)
            rhi.chain_id = c.get_chain_id()
            
        # Copy
        if loader.copyf.get_is(node):
            rhi = copy.copy(rhi)
            rhi.copy_index = loader.copyf.get(node).get_copy_index()
            
        # Fragment
        if loader.fragmentf.get_is(node):
            rhi = copy.copy(rhi)
            f = loader.fragmentf.get(node)
            resinds = f.get_residue_indexes()
            if resinds:
                rhi.res_num = resinds[len(resinds) // 2]
            rhi.res_type = 'UNK'
            
        # Residue
        if loader.residuef.get_is(node):
            rhi = copy.copy(rhi)
            r = loader.residuef.get(node)
            rhi.res_num = r.get_residue_index()
            rhi.res_type = r.get_residue_type()
            
        return rhi

class _RmfLoader:
    def __init__(self):
        self.particle_nodes: List[RMF.NodeConstHandle] = []
        self.rmf_index_to_particle_idx: Dict[int, int] = {}
        #: Per particle, the resolution of the representation it belongs to, and
        #: whether that representation is the tree's own (as opposed to an
        #: alternative hung off it). Both stay parallel to ``particle_nodes``.
        self.particle_resolutions: List[float] = []
        self.particle_is_default: List[bool] = []
        #: Per particle, the chain it belongs to and the residue it stands for,
        #: as the hierarchy states them. These are what turn particles into
        #: *bead rows*: without a residue identity the trace collapses to one
        #: point, and without a chain no selection can name part of the model.
        self.particle_chains: List[str] = []
        self.particle_res_nums: List[int] = []
        #: ``{node index: resolution}`` for every subtree that is an *alternative*
        #: representation. Such a subtree is reached through the node that owns
        #: it, never as an ordinary child, or its particles would be collected
        #: twice and drawn on top of themselves.
        self.alternative_roots: Dict[int, float] = {}

    def load(self, path: Path) -> Dict[str, Any]:
        if RMF is None:
            raise RmfNotAvailableError("RMF loading requires 'RMF' package.")
            
        r = RMF.open_rmf_file_read_only(str(path))
        
        # Initialize factories
        self.particlef = RMF.ParticleConstFactory(r)
        self.chainf = RMF.ChainConstFactory(r)
        self.fragmentf = RMF.FragmentConstFactory(r)
        self.residuef = RMF.ResidueConstFactory(r)
        self.copyf = RMF.CopyConstFactory(r)
        self.statef = RMF.StateConstFactory(r)
        self.bondf = RMF.BondConstFactory(r)
        self.represf = RMF.RepresentationConstFactory(r)
        self.atomf = RMF.AtomConstFactory(r)
        self.segmentf = RMF.SegmentConstFactory(r)
        self.coloredf = RMF.ColoredConstFactory(r)
        # Built once. These two are consulted at *every* node of the walk, and a
        # factory constructed per node is a quarter of a million constructions
        # on a model the size of the nuclear pore.
        try:
            self.resolutionf = RMF.ExplicitResolutionConstFactory(r)
        except Exception:  # pragma: no cover - very old RMF
            self.resolutionf = None
        try:
            self.alternativesf = RMF.AlternativesConstFactory(r)
        except Exception:  # pragma: no cover - very old RMF
            self.alternativesf = None
        
        try:
            self.softwaref = RMF.SoftwareProvenanceConstFactory(r)
        except AttributeError:
            try:
                self.softwaref = RMF.SoftwareConstFactory(r)
            except AttributeError:
                self.softwaref = None

        r.set_current_frame(RMF.FrameID(0))

        # 0. Find the alternative representations before walking anything, so
        #    the walk knows which subtrees are alternatives rather than more
        #    matter in the same model.
        self._find_alternatives(r)

        # 1. First pass: Collect all particle nodes and build hierarchy
        rhi = _RmfHierarchyInfo()
        root_node = self._handle_node(r.get_root_node(), rhi)

        # 2. Extract coordinates for all frames
        num_frames = r.get_number_of_frames()
        num_particles = len(self.particle_nodes)
        
        if num_particles == 0:
            raise RuntimeError(f"No particles/coordinates found in {path}")
            
        rmf_frame_series: Dict[str, list[float]] = {}
        rmf_frame_metadata: Dict[str, list[Any]] = {}
        stat_keys = self._extract_stat_keys(r)
        for _key, name in stat_keys:
            rmf_frame_series[name] = []
            rmf_frame_metadata[name] = []
            
        frames_arr = np.zeros((num_frames, num_particles, 3), dtype=np.float32)
        coord_buffer = np.zeros((num_particles, 3), dtype=np.float64)
        # ``get_all_global_coordinates`` fills the buffer in RMF's own order and
        # is the only reader that applies ancestors' reference frames, so it is
        # worth keeping -- but this loader no longer walks the tree in that
        # order, because an alternative representation is visited through the
        # node that owns it. Reorder rather than assume the two agree: getting
        # this wrong scrambles every coordinate against its radius and hierarchy
        # entry, which looks like a broken file rather than a broken reader.
        permutation = self._global_order_permutation(r)

        # A radius and a colour belong to a *frame*, not to the file. RMF stores
        # both that way and chimol read neither: radii came from whichever frame
        # the walk happened to leave current, and the colour factory was built
        # and never asked. A simulation whose beads grow, appear or change state
        # says so through exactly these two, so they are read per frame and
        # collapsed to one array only when they turn out not to vary.
        colored_nodes = [
            index
            for index, node in enumerate(self.particle_nodes)
            if self.coloredf.get_is(node)
        ]
        radii_frames = np.zeros((num_frames, num_particles), dtype=np.float32)
        colors_frames = (
            np.ones((num_frames, num_particles, 3), dtype=np.float32)
            if colored_nodes
            else None
        )

        for f in range(num_frames):
            r.set_current_frame(RMF.FrameID(f))
            try:
                RMF.get_all_global_coordinates(r, r.get_root_node(), coord_buffer)
                frame_coords = coord_buffer[permutation]
            except Exception:
                for i, node in enumerate(self.particle_nodes):
                    xyz = self.particlef.get(node).get_coordinates()
                    coord_buffer[i, 0] = xyz[0]
                    coord_buffer[i, 1] = xyz[1]
                    coord_buffer[i, 2] = xyz[2]
                frame_coords = coord_buffer
            frames_arr[f] = frame_coords.astype(np.float32)
            for i, node in enumerate(self.particle_nodes):
                radii_frames[f, i] = self.particlef.get(node).get_radius()
            if colors_frames is not None:
                for i in colored_nodes:
                    # Subscripted three times rather than converted: numpy and
                    # ``list`` both fall back to the iteration protocol on an
                    # RMF ``Vector3``, which costs 20 us against 1.4 us for
                    # three plain lookups. Over a trajectory that is the whole
                    # load time -- it was 17 s of this file's 19.7 s.
                    color = self.coloredf.get(self.particle_nodes[i]).get_rgb_color()
                    colors_frames[f, i, 0] = color[0]
                    colors_frames[f, i, 1] = color[1]
                    colors_frames[f, i, 2] = color[2]
            self._extract_stat_values(
                r.get_root_node(),
                stat_keys,
                rmf_frame_series,
                rmf_frame_metadata,
            )

        # 3. Radii and colours: one array when they hold still, a frame series
        #    when they do not. Deciding here rather than at the render seam is
        #    what lets every consumer that does not care about time keep asking
        #    for one array.
        radii_arr = radii_frames[0]
        frame_radii = radii_frames if _varies(radii_frames) else None
        colors_arr = colors_frames[0] if colors_frames is not None else None
        frame_colors = (
            colors_frames
            if colors_frames is not None and _varies(colors_frames)
            else None
        )

        # 4. Extract metadata (restraints, states, PROVENANCE, BONDS, stat)
        restraints = []
        rmf_provenance = []
        states = []
        bond_pairs = []
        
        self._extract_metadata(r.get_root_node(), restraints, rmf_provenance, states, bond_pairs)

        # A file with no alternatives has no resolution dimension at all, and
        # says so with None rather than with an array of one repeated value:
        # every consumer then skips the work, and the chooser knows to stay
        # hidden instead of offering a choice of one.
        has_alternatives = bool(self.alternative_roots)
        resolutions_arr = (
            np.asarray(self.particle_resolutions, dtype=np.float32)
            if has_alternatives
            else None
        )
        default_mask = (
            np.asarray(self.particle_is_default, dtype=bool)
            if has_alternatives
            else None
        )

        chains_arr = np.asarray(self.particle_chains, dtype=str)
        res_ids_arr = _residue_numbers(self.particle_res_nums, self.particle_chains)
        atoms_arr = make_bead_rows(
            frames_arr[0], chain_ids=chains_arr, res_ids=res_ids_arr
        )
        # One trace point per bead, deliberately not deduplicated by
        # ``(chain, res_id)``. Two copies of a molecule share residue numbers,
        # and a coarse bead covers residues a fine one also covers, so merging
        # by residue identity would drop rows -- and it is the *identity* of the
        # trace points with the rows that lets per-residue colours be applied
        # per bead without a lookup over hundreds of thousands of them.
        res_names_arr = np.full(len(chains_arr), BEAD_RES_NAME, dtype=object)

        return {
            "hierarchy": root_node,
            "frames": frames_arr,
            "radii": radii_arr,
            "frame_radii": frame_radii,
            "colors": colors_arr,
            "frame_colors": frame_colors,
            "atoms": atoms_arr,
            "chain_ids": chains_arr,
            "res_ids": res_ids_arr,
            "res_names": res_names_arr,
            "states": states,
            "restraints": restraints,
            "rmf_provenance": rmf_provenance,
            "resolutions": resolutions_arr,
            "resolution_default_mask": default_mask,
            "rmf_resolutions": (
                sorted({float(v) for v in self.particle_resolutions})
                if has_alternatives
                else []
            ),
            "bond_pairs": np.array(bond_pairs, dtype=np.int32) if bond_pairs else None,
            "rmf_frame_series": {
                name: np.asarray(values, dtype=float)
                for name, values in rmf_frame_series.items()
            },
            "rmf_frame_metadata": rmf_frame_metadata,
        }
        
    def _find_alternatives(self, handle: Any) -> None:
        """Record every subtree that is an *alternative* representation.

        IMP stores a molecule's coarser depictions as ``Alternatives`` hung off
        the node they replace, and the roots of those subtrees sit in the file
        as ordinary nodes -- routinely as children of the file root. A plain
        walk therefore collects a model's fine *and* coarse particles and draws
        them on top of each other, which is what this reader did: 40 fine beads
        and 8 coarse ones came back as one 48-particle model.

        The first entry of ``get_alternatives`` is the node itself -- the
        representation that lives in the tree -- so everything after it is an
        alternative, and is reached through its owner rather than where it
        happens to sit.

        Parameters
        ----------
        handle : RMF file handle
            The open file.
        """
        if self.alternativesf is None:
            return

        def walk(node):
            yield node
            for child in node.get_children():
                yield from walk(child)

        for node in walk(handle.get_root_node()):
            if not self.alternativesf.get_is(node):
                continue
            try:
                alternatives = self.alternativesf.get(node).get_alternatives(
                    RMF.PARTICLE
                )
            except Exception:
                continue
            for alternative in list(alternatives)[1:]:
                self.alternative_roots[alternative.get_id().get_index()] = (
                    self._resolution_of(alternative)
                )

    def _explicit_resolution(self, node: Any) -> float:
        """The resolution ``node`` states for itself, or NaN.

        Parameters
        ----------
        node : RMF.NodeConstHandle
            Node to ask.

        Returns
        -------
        float
            The stated resolution, or NaN when the node does not state one. NaN
            rather than 0: it is not a resolution anyone chose, so it compares
            unequal to every real one instead of colliding with a real value.
        """
        if self.resolutionf is None:
            return float("nan")
        try:
            if self.resolutionf.get_is(node):
                return float(self.resolutionf.get(node).get_explicit_resolution())
        except Exception:
            pass
        return float("nan")

    def _resolution_of(self, node: Any) -> float:
        """The resolution of the representation rooted at ``node``.

        Prefers what the node states; falls back to the value RMF derives from
        the subtree, which is an average and meaningful only where there are
        particles beneath.

        Parameters
        ----------
        node : RMF.NodeConstHandle
            Root of a representation.

        Returns
        -------
        float
            The resolution, or NaN when the file does not say.
        """
        stated = self._explicit_resolution(node)
        if stated == stated:  # not NaN
            return stated
        try:
            return float(RMF.get_resolution(node))
        except Exception:
            return float("nan")

    def _global_order_permutation(self, handle: Any) -> np.ndarray:
        """Map RMF's own particle order onto this loader's.

        ``get_all_global_coordinates`` writes one row per particle in the order
        a plain depth-first walk meets them. This loader deliberately walks in a
        different order -- an alternative representation is visited through the
        node that owns it, not where it sits in the file -- so the buffer has to
        be permuted before it means anything.

        Returns
        -------
        numpy.ndarray
            Index array such that ``buffer[permutation]`` is in loader order.
            The identity when the two orders happen to agree, and when anything
            about the mapping is incomplete (a particle this loader collected
            that the plain walk did not reach), because a partial permutation
            would silently mix rows.
        """
        order: Dict[int, int] = {}

        def walk(node):
            if self.particlef.get_is(node):
                order.setdefault(node.get_id().get_index(), len(order))
            for child in node.get_children():
                walk(child)

        walk(handle.get_root_node())

        try:
            permutation = np.asarray(
                [order[node.get_id().get_index()] for node in self.particle_nodes],
                dtype=int,
            )
        except KeyError:
            return np.arange(len(self.particle_nodes), dtype=int)
        if permutation.shape[0] != len(order):
            return np.arange(len(self.particle_nodes), dtype=int)
        return permutation

    def _handle_node(
        self,
        node: RMF.NodeConstHandle,
        parent_rhi: _RmfHierarchyInfo,
        resolution: float = float("nan"),
        is_default: bool = True,
    ) -> RmfHierarchyNode:
        rhi = parent_rhi.handle_node(node, self)

        # A node may state its own resolution; otherwise it inherits the one of
        # the representation it is part of. Only an *explicit* statement counts
        # here: a resolution derived from whatever happens to sit below a node is
        # an average, and would overwrite the representation's own answer.
        own_resolution = self._explicit_resolution(node)
        if own_resolution == own_resolution:  # not NaN
            resolution = own_resolution

        ntype = "NODE"
        if self.statef.get_is(node): ntype = "STATE"
        elif self.chainf.get_is(node): ntype = "CHAIN"
        elif self.residuef.get_is(node): ntype = "RESIDUE"
        elif self.atomf.get_is(node): ntype = "ATOM"
        elif self.particlef.get_is(node): ntype = "PARTICLE"
        
        ridx = node.get_id().get_index()
        h_node = RmfHierarchyNode(
            name=node.get_name(),
            rmf_index=ridx,
            node_type=ntype,
            chain_id=rhi.chain_id,
            res_num=rhi.res_num,
            res_type=rhi.res_type,
            copy_index=rhi.copy_index
        )
        
        # We only collect particles that have Coordinate trait
        # ParticleConstFactory usually checks for mass/radius, but we also need XYZ.
        # Actually in RMF all Particles should have coords.
        if self.particlef.get_is(node):
            p_idx = len(self.particle_nodes)
            self.particle_nodes.append(node)
            self.rmf_index_to_particle_idx[ridx] = p_idx
            self.particle_resolutions.append(resolution)
            self.particle_is_default.append(is_default)
            self.particle_chains.append(str(rhi.chain_id or ""))
            self.particle_res_nums.append(
                int(rhi.res_num) if rhi.res_num is not None else -1
            )
            h_node.atom_indices = [p_idx]
            h_node.radius = self.particlef.get(node).get_radius()

        def attach(child_h: RmfHierarchyNode) -> None:
            child_h.parent = h_node
            child_h.parent_index = ridx
            h_node.children.append(child_h)
            h_node.atom_indices.extend(child_h.atom_indices)

        for child in node.get_children():
            # Skip Representation and Provenance nodes in the main hierarchy tree
            if self.represf.get_is(child): continue
            if child.get_type() == RMF.PROVENANCE: continue
            # An alternative representation is reached through the node it is an
            # alternative *to*, below, not from wherever it sits in the file.
            if child.get_id().get_index() in self.alternative_roots: continue

            attach(self._handle_node(child, rhi, resolution, is_default))

        # The coarser depictions of this same node. They hang underneath it, so
        # that hiding a molecule in the hierarchy panel hides it at every
        # resolution -- it is one molecule, however finely it is drawn.
        for alternative, alt_resolution in self._alternatives_of(node):
            alt_h = self._handle_node(alternative, rhi, alt_resolution, False)
            alt_h.name = f"{alt_h.name} [resolution {alt_resolution:g}]"
            attach(alt_h)

        return h_node

    def _alternatives_of(self, node: RMF.NodeConstHandle) -> List[Tuple[Any, float]]:
        """The alternative representations of ``node``, with their resolutions.

        Parameters
        ----------
        node : RMF.NodeConstHandle
            The node that may own alternatives.

        Returns
        -------
        list of (node, float)
            Empty for the overwhelmingly common case of a file that states one
            representation.
        """
        if not self.alternative_roots or self.alternativesf is None:
            return []
        try:
            if not self.alternativesf.get_is(node):
                return []
            alternatives = list(
                self.alternativesf.get(node).get_alternatives(RMF.PARTICLE)
            )[1:]
        except Exception:
            return []
        return [
            (
                alternative,
                self.alternative_roots.get(
                    alternative.get_id().get_index(), float("nan")
                ),
            )
            for alternative in alternatives
        ]

    def _extract_stat_keys(self, rmf_handle: Any) -> list[tuple[Any, str]]:
        """Return RMF stat keys that can be read as frame metadata."""
        try:
            category = rmf_handle.get_category("stat")
            keys = rmf_handle.get_keys(category)
            return [(key, rmf_handle.get_name(key)) for key in keys]
        except Exception:
            return []

    def _extract_stat_values(
        self,
        root_node: RMF.NodeConstHandle,
        stat_keys: list[tuple[Any, str]],
        series: Dict[str, list[float]],
        metadata: Dict[str, list[Any]],
    ) -> None:
        """Append current-frame RMF stat values to series containers."""
        for key, name in stat_keys:
            try:
                value = root_node.get_value(key)
                numeric = _as_numeric_stat_value(value)
                metadata[name].append(value)
                series[name].append(numeric)
            except Exception:
                metadata[name].append(None)
                series[name].append(float("nan"))

    def _extract_metadata(self, node: RMF.NodeConstHandle, restraints: list, provenance: list, states: list, bond_pairs: list):
        # Software
        if self.softwaref and self.softwaref.get_is(node):
            sw = self.softwaref.get(node)
            get_type = getattr(sw, "get_type", None)
            type_text = ""
            if get_type is not None:
                try:
                    type_text = f" ({get_type()})"
                except Exception:
                    type_text = ""
            provenance.append({"name": sw.get_name(), "value": f"{sw.get_version()}{type_text}"})
            
        # Explicit Bonds
        if self.bondf.get_is(node):
            b = self.bondf.get(node)
            nodes = [b.get_bonded_0(), b.get_bonded_1()]
            indices = []
            for n in nodes:
                idx = n.get_id().get_index()
                if idx in self.rmf_index_to_particle_idx:
                    indices.append(self.rmf_index_to_particle_idx[idx])
            if len(indices) == 2:
                bond_pairs.append((indices[0], indices[1]))

        # Restraints (Representation nodes)
        if self.represf.get_is(node):
            rep = self.represf.get(node)
            targets = rep.get_representation() # Returns handles
            indices = [self.rmf_index_to_particle_idx[t.get_id().get_index()] 
                       for t in targets if t.get_id().get_index() in self.rmf_index_to_particle_idx]
            
            # CRITICAL: Only add as distance restraints if exactly 2 particles.
            # Otherwise it's just a grouping representation and we should NOT draw it as spaghetti.
            if len(indices) == 2:
                restraints.append({"indices": (indices[0], indices[1]), "name": node.get_name()})
        
        # States
        if self.statef.get_is(node):
            states.append(node.get_id().get_index())
            
        for child in node.get_children():
            self._extract_metadata(child, restraints, provenance, states, bond_pairs)

def _as_numeric_stat_value(value: Any) -> float:
    """Convert RMF stat values to floats for Chimol plotting."""
    if isinstance(value, (bool, np.bool_)):
        return float(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        numeric = float(value)
    else:
        try:
            numeric = float(value)
        except Exception:
            return float("nan")
    if not np.isfinite(numeric):
        return float("nan")
    return numeric


def load_rmf_full(path: Path) -> Dict[str, Any]:
    loader = _RmfLoader()
    return loader.load(path)

__all__ = ["load_rmf_full", "RmfNotAvailableError", "RmfHierarchyNode"]

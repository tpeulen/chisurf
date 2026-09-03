"""Accessible volumes — computed by ``IMP.bff``, presented in ChiSurf's shape.

**This package no longer implements accessible volumes.** The AV computation, the
dye-diffusion field model and the distance metrics all live in ``IMP.bff``; what
is left here is the ChiSurf-facing shape — classes built from a
:class:`chisurf.core.structure.Structure` and a labelling site, exposing the
attribute names the rest of ChiSurf reads.

What went, and why none of it is a loss:

``static.py``
    ``calculate_1_radius`` / ``calculate_3_radius`` were thin **LabelLib**
    wrappers — their native paths had been commented out — so ``IMP.bff``'s C++
    ``AV``/``PathMap`` supersedes them outright.
``functions.py``
    ``density2points``, ``random_distances``, ``split_av_acv``, ``RDAMean``,
    ``RDAMeanE``, ``dRmp``, ``widthRDA`` and ``histogram_rda`` all exist
    upstream. The grid/diffusion half (``assign_diffusion_to_grid*``,
    ``create_quenching_map``, ``create_fret_rate_map``, ``DiffusionIterator``)
    moved to ``IMP.bff.quenching`` with **three defects fixed**: the solver
    swapped its ping-pong buffers only on odd steps and so threw away half the
    evolution (⟨x²⟩/2Dt measured 0.503, now 0.9991); the map builders looped
    ``range(-npm, npm)`` and never wrote the outer slab, which in
    ``assign_diffusion_to_grid_1`` meant **uninitialised memory** read back as a
    diffusion coefficient; and the stencil's outer shell kept population from
    two steps ago, never decaying, in every sum.
``dynamic.py``
    ``simulate_trajectory`` raised ``ImportError`` — its ``fps_.pyx`` had not
    existed for a long time — and ``_quenching_rate_per_frame`` had no caller
    but its own test. The working model is ``IMP.bff.DynamicAccessibleVolume``.
``utils.py``
    ``atoms_in_reach`` served only the LabelLib AV that is gone.

One backend, deliberately. ``IMP.bff`` and LabelLib never agreed — 136 707
points against 151 869 on the same site — so which one ran silently decided
every distance downstream.
"""

from __future__ import annotations

import json
import os

import numpy as np

import chisurf as cs
import chisurf.core.fio as io
import chisurf.core.fio.structure
import chisurf.core.fio.structure.coordinates
import chisurf.core.settings
import chisurf.core.support.common

package_directory = os.path.dirname(__file__)
dye_file = os.path.join(
    chisurf.core.settings.package_directory, 'dye_definition.json'
)

try:
    dye_definition = json.load(open(dye_file))
except IOError:
    dye_definition = dict()
    dye_definition['a'] = 0

dye_names = dye_definition.keys()

__all__ = ["BasicAV", "ACV", "DynamicAV", "dye_definition", "dye_names"]


def _compute_av():
    """``IMP.bff.compute_av``, imported on first use.

    Lazy on purpose: importing ``IMP`` pulls a large native stack in, and
    ``import chisurf.core.structure`` must stay cheap. The upstream imp.bff
    build moved the builder from the ``IMP.bff.av`` Python subpackage into the
    ``IMP.bff`` C++ surface, which takes one ``(N, 4)`` xyz+radius array.
    """
    from IMP.bff import compute_av

    return compute_av


class BasicAV:
    """The accessible volume of a dye at one labelling site.

    Computed by ``IMP.bff``; this class resolves the attachment atom, hands over
    plain arrays, and presents the result under the names ChiSurf reads
    (``density``, ``bounds``, ``points``, ``x0``, ``dg``, ``ng``).

    Examples
    --------
    >>> import chisurf.core.structure
    >>> structure = chisurf.core.structure.Structure('./test/data/atomic_coordinates/pdb_files/hGBP1_closed.pdb')
    >>> av = chisurf.core.structure.av.BasicAV(structure, residue_seq_number=18, atom_name='CB')
    """

    def __init__(
            self,
            structure,
            simulation_grid_resolution: float = None,
            allowed_sphere_radius: float = None,
            radius1: float = 1.5,
            radius2: float = 4.5,
            radius3: float = 3.5,
            linker_width: float = 1.5,
            linker_length: float = 20.5,
            simulation_type: str = "AV1",
            chain_identifier: str = None,
            residue_name: str = None,
            residue_seq_number: int = None,
            atom_name: str = None,
            position_name: str = None,
            verbose: bool = False,
            **kwargs
    ):
        if simulation_grid_resolution is None:
            simulation_grid_resolution = chisurf.core.settings.fps[
                'simulation_grid_resolution']
        self.dg = simulation_grid_resolution
        # ``None`` means the caller did not choose: hand upstream the sentinel
        # and let it derive the FPS mapping ``max(1.5, linker_width / 2 +
        # grid / 2)``. The search inflates obstacles by half the linker width,
        # so an explicit radius below that walls the source in and the volume
        # comes back empty (upstream AV.h: the flat value was the fps.json
        # door's bug, now unified into this derivation).
        self.allowed_sphere_radius = (
            -1.0 if allowed_sphere_radius is None
            else float(allowed_sphere_radius)
        )

        self.verbose = verbose
        self.position_name = position_name
        self.residue_name = residue_name
        self.attachment_residue = residue_seq_number
        self.attachment_atom = atom_name

        self.radius1 = radius1
        self.radius2 = radius2
        self.radius3 = radius3
        self.linker_width = linker_width
        self.linker_length = linker_length
        self.simulation_type = simulation_type
        self.structure = structure

        attachment_atom_index = kwargs.get(
            'attachment_atom_index',
            chisurf.core.fio.structure.coordinates.get_atom_index(
                self.atoms,
                chain_identifier,
                self.attachment_residue,
                self.attachment_atom,
                self.residue_name
            )
        )

        # AV1 is one sphere, AV3 uses all three radii. Upstream reads the model
        # off the radii rather than off a string, so the string maps here.
        dye_radii = (
            (radius1, radius2, radius3) if self.simulation_type == 'AV3'
            else (radius1, 0.0, 0.0)
        )

        # The attachment residue's own side chain obstructs the site it
        # anchors. Upstream's PDB door strips that residue to its backbone
        # plus the attachment atom (``default_strip_mask``), which is what
        # lets FPS-calibrated linker widths compute a real cloud; the array
        # door has no strip, so the caller applies the same keep-set here.
        # Without it, a CB site walled in by its own side chain plus the
        # half-linker-width inflation returns an empty volume.
        atoms = self.atoms
        backbone = ('N', 'CA', 'C', 'O')
        site = (atoms['res_id'] == self.attachment_residue)
        keep = ~site | (atoms['atom_name'] == self.attachment_atom) | np.isin(
            atoms['atom_name'], backbone)
        obstacle_atoms = atoms[keep]

        # The upstream door takes one (N, 4) array of x, y, z, radius, and the
        # three dye radii separately.
        xyz = np.ascontiguousarray(obstacle_atoms['xyz'], dtype=np.float64)
        atoms_xyzr = np.ascontiguousarray(
            np.hstack([xyz, np.asarray(
                obstacle_atoms['radius'], dtype=np.float64)[:, None]])
        )

        result = _compute_av()(
            atoms_xyzr,
            np.ascontiguousarray(xyz[attachment_atom_index], dtype=np.float64),
            linker_length=self.linker_length,
            linker_width=self.linker_width,
            r1=dye_radii[0],
            r2=dye_radii[1],
            r3=dye_radii[2],
            grid_resolution=self.dg,
            allowed_sphere_radius=self.allowed_sphere_radius,
        )

        ng = int(result.get_ng())
        density = np.ascontiguousarray(
            result.get_density(), dtype=np.float64).reshape(ng, ng, ng)
        #: The upstream ``IMP.bff.AccessibleVolume`` this was built from, kept
        #: for the dynamic (quenching/FRET field) model built on first use.
        self._upstream_av = result

        self.x0 = np.asarray(result.attachment_point, dtype=np.float64)
        self._bounds = (density > 0).astype(np.uint8)
        total = density.sum()
        density = density / total if total else density
        #: The unsplit, uniformly-weighted volume. `ACV` re-weights *this* into
        #: `_density`, so re-weighting twice cannot compound.
        self._base_density = density
        self._density = density
        self._points = None

    # -- the grid -----------------------------------------------------------

    @property
    def bounds(self):
        """Binary mask of grid points accessible to the dye (uint8)."""
        return self._bounds

    @property
    def ng(self) -> int:
        """Number of grid points along one edge of the density cube."""
        return self.density.shape[0]

    @property
    def density(self):
        """Normalised density of dye positions on the grid."""
        return self._density

    @property
    def points(self):
        """``(n, 4)`` array of ``(x, y, z, weight)`` sampled from the density."""
        if self._points is None:
            self.update_points()
        return self._points

    @property
    def n_points(self) -> int:
        """Number of points in the cloud."""
        return int(self.points.shape[0])

    @property
    def atoms(self) -> np.ndarray:
        """The atom array of the associated structure."""
        return self.structure.atoms

    def update_points(self) -> None:
        """Recompute the point cloud from the density grid."""
        from IMP.bff import density_to_points

        ng = self.ng
        # `x0` is the grid *anchor*, sitting on the middle voxel; the kernel
        # wants the centre of voxel (0, 0, 0). The offset is the **integer**
        # `(ng - 1) // 2`, which differs from the float corner on every even
        # edge — and even is the normal case, not an edge case.
        origin = self.x0 - ((ng - 1) // 2) * float(self.dg)
        self._points = np.ascontiguousarray(
            density_to_points(
                np.ascontiguousarray(self.density, dtype=np.float64),
                float(self.dg),
                np.ascontiguousarray(origin, dtype=np.float64),
            ),
            dtype=np.float64,
        )

    def update(self):
        """Recalculate the point cloud from the density grid."""
        self.update_points()

    def save(self, filename: str, mode: str = 'xyz', **kwargs):
        """Save the accessible volume as an xyz file or an OpenDX density."""
        if mode == 'dx':
            density = kwargs.get('density', self.density)
            d = density / density.max() * 0.5
            ng, dg = self.ng, self.dg
            offset = (ng - 1) / 2 * dg
            io.structure.density.write_open_dx(
                filename, d, self.x0 - offset, ng, ng, ng, dg, dg, dg
            )
        else:
            p = kwargs.get('points', self.points)
            d = p[:, [3]].flatten()
            d /= max(d) * 50.0
            io.structure.write_points(
                filename=filename + '.' + mode,
                points=p[:, [0, 1, 2]], mode=mode,
                verbose=self.verbose, density=d,
            )

    # -- distances to a second accessible volume ----------------------------
    #
    # `av_pair_statistics` takes a *sample* of pair distances and returns
    # ⟨R_DA⟩, R_mp, ⟨R_DA⟩_E and ⟨E⟩ in one pass, so one sample serves all of
    # them. The seed is fixed on purpose: a reported distance that changes when
    # you ask for it twice is not a reported distance.

    #: Fixed so repeated calls agree. Sampling noise on ⟨R_DA⟩ at this count is
    #: well under 0.1 Å.
    N_DISTANCE_SAMPLES = 50_000
    DISTANCE_SEED = 0

    def _pair_sample(self, av, n_samples: int = None, seed: int = None):
        from IMP.bff import random_distances

        sample = random_distances(
            np.ascontiguousarray(self.points, dtype=np.float64),
            np.ascontiguousarray(av.points, dtype=np.float64),
            int(self.N_DISTANCE_SAMPLES if n_samples is None else n_samples),
            int(self.DISTANCE_SEED if seed is None else seed),
        )
        return sample[:, 0], sample[:, 1]

    def _pair_statistics(self, av, forster_radius: float = 52.0,
                         n_samples: int = None, **kwargs):
        from IMP.bff import av_pair_statistics

        return av_pair_statistics(
            np.ascontiguousarray(self.points, dtype=np.float64),
            np.ascontiguousarray(av.points, dtype=np.float64),
            float(forster_radius),
            int(self.N_DISTANCE_SAMPLES if n_samples is None else n_samples),
        )

    def dRmp(self, av) -> float:
        """Distance between the two mean positions, R_mp.

        **Not** ⟨R_DA⟩. ``|⟨r_D⟩ − ⟨r_A⟩|`` is a property of the two clouds and
        cannot be recovered from a sample of pair distances at all, which is why
        it is computed from the centroids here. Measured on 148l
        E15/E90 the two differ by 8 %: 47.65 Å against 51.53 Å.
        """
        from IMP.bff import mean_position_distance

        # The clouds are (n, 4) — xyz plus weight — and the kernel takes the
        # coordinates and the weights separately.
        return float(mean_position_distance(
            self.points[:, :3], av.points[:, :3],
            self.points[:, 3], av.points[:, 3],
        ))

    def dRDA(self, av, **kwargs) -> float:
        """Mean donor–acceptor distance ⟨R_DA⟩."""
        return float(self._pair_statistics(av, **kwargs)[0])

    def widthRDA(self, av, **kwargs) -> float:
        """Width (weighted standard deviation) of the D–A distance distribution."""
        distances, weights = self._pair_sample(av, **kwargs)
        w_sum = weights.sum()
        if w_sum == 0.0:
            return 0.0
        mean = float(np.dot(distances, weights) / w_sum)
        variance = float(np.dot((distances - mean) ** 2, weights) / w_sum)
        return float(np.sqrt(max(variance, 0.0)))

    def dRDAE(self, av, forster_radius: float = 52.0, **kwargs) -> float:
        """FRET-averaged distance ⟨R_DA⟩_E."""
        return float(self._pair_statistics(av, forster_radius, **kwargs)[2])

    def pRDA(self, av, rda_axis=None, same_size: bool = True, **kwargs):
        """Distance distribution against a second accessible volume.

        Two ChiSurf conventions the upstream kernel does not carry, applied
        here because they are ChiSurf's and not the library's:

        * the default axis is ``chisurf.core.fluorescence.rda_axis``, so every
          distribution in the application shares one distance grid;
        * ``same_size`` pads the histogram with a trailing zero so it is as long
          as the axis. ``np.histogram`` returns ``len(bins) - 1`` counts, and
          ChiSurf plots ``(p, rda_axis)`` as a pair.
        """
        import chisurf.core.fluorescence
        from IMP.bff import histogram_rda

        if rda_axis is None:
            rda_axis = chisurf.core.fluorescence.rda_axis
        rda_axis = np.ascontiguousarray(rda_axis, dtype=np.float64)
        p = histogram_rda(
            np.ascontiguousarray(self.points, dtype=np.float64),
            np.ascontiguousarray(av.points, dtype=np.float64),
            rda_axis,
        )
        axis = rda_axis
        if same_size and len(p) == len(axis) - 1:
            p = np.append(p, [0])
        return p, axis

    @property
    def Rmp(self) -> np.ndarray:
        """Mean position of the accessible volume."""
        weights = self.points[:, 3].copy()
        weights /= weights.sum()
        return np.average(self.points[:, [0, 1, 2]], weights=weights, axis=0)

    def __repr__(self) -> str:
        return "%s(%s, n_points=%d)" % (
            type(self).__name__, self.position_name or "?", len(self.points))


class ACV(BasicAV):
    """An accessible volume split into a free and a *contact* part.

    A dye spends a disproportionate share of its time near the protein surface,
    so a uniform accessible volume over-weights the free region. The contact
    volume — voxels within ``slow_radius`` of a slow centre — is given
    ``contact_volume_trapped_fraction`` of the total weight.

    Examples
    --------
    >>> av = chisurf.core.structure.av.ACV(structure, residue_seq_number=18,
    ...                                    atom_name='CB',
    ...                                    contact_volume_trapped_fraction=0.5)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._slow_centers = None
        self._slow_radius = None
        self._contact_density = None
        self._contact_volume_trapped_fraction = kwargs.get(
            'contact_volume_trapped_fraction', 0.8)
        self.slow_centers = kwargs.get('slow_centers', 'CB')
        self.slow_radius = kwargs.get('slow_radius', 10.0)
        self.update_density()

    @property
    def contact_volume_trapped_fraction(self) -> float:
        """Share of the total weight carried by the contact volume."""
        return self._contact_volume_trapped_fraction

    @contact_volume_trapped_fraction.setter
    def contact_volume_trapped_fraction(self, v: float):
        self._contact_volume_trapped_fraction = float(v)
        self.update_density()

    @property
    def slow_centers(self) -> np.ndarray:
        """Coordinates the contact volume is measured from."""
        return self._slow_centers

    @slow_centers.setter
    def slow_centers(self, v):
        if isinstance(v, str):
            atoms = self.atoms
            selection = (
                np.ones(atoms.shape[0], dtype=bool) if v == 'all'
                else atoms['atom_name'] == v
            )
            v = atoms['xyz'][selection]
        self._slow_centers = np.ascontiguousarray(v, dtype=np.float64)

    @property
    def slow_radius(self) -> np.ndarray:
        """Radius around each slow centre counted as contact."""
        return self._slow_radius

    @slow_radius.setter
    def slow_radius(self, v):
        n = 1 if self._slow_centers is None else self._slow_centers.shape[0]
        if isinstance(v, (int, float)):
            self._slow_radius = np.ones(n, dtype=np.float64) * float(v)
        else:
            self._slow_radius = np.ascontiguousarray(v, dtype=np.float64)

    @property
    def contact_density(self):
        """The contact ("slow") part of the density grid."""
        return self._contact_density

    def update_density(self):
        """Re-split the volume into its free and contact parts."""
        if self._slow_centers is None or self._slow_radius is None:
            return
        from IMP.bff import split_contact_volume_masks

        ng = self.ng
        base = np.ascontiguousarray(self._base_density, dtype=np.float64)
        # Returns two **binary masks** — contact first, free second — not
        # weighted densities, so the base density is what gets partitioned.
        # The kernel wants its radius and centre arrays 2-D.
        contact_mask, free_mask = split_contact_volume_masks(
            base,
            float(self.dg),
            np.ascontiguousarray(self._slow_radius[:, None]),
            np.ascontiguousarray(self._slow_centers),
            np.ascontiguousarray(self.x0[None, :], dtype=np.float64),
        )
        contact = base * contact_mask.reshape(base.shape)
        free = base * free_mask.reshape(base.shape)

        weight = self._contact_volume_trapped_fraction
        contact_sum, free_sum = contact.sum(), free.sum()
        if contact_sum:
            contact = contact / contact_sum * weight
        if free_sum:
            free = free / free_sum * (1.0 - weight)
        self._contact_density = contact.reshape(ng, ng, ng)
        self._density = (free + contact).reshape(ng, ng, ng)
        self._points = None

    def update(self):
        self.update_density()
        self.update_points()


class DynamicAV(BasicAV):
    """An accessible volume carrying mobility, quenching and FRET fields.

    A thin binding of :class:`IMP.bff.DynamicAccessibleVolume` to ChiSurf's
    ``Structure``. The physics — the maps, the explicit solver for
    ``dp/dt = div(D grad p) - k p``, the equilibrium occupancy and the donor
    decay — is upstream's, with the three defects listed in the module
    docstring fixed on the way there.
    """

    def __init__(
            self,
            *args,
            diffusion_coefficient: float = 8.0,
            contact_distance: float = 3.5,
            slow_factor: float = 0.985,
            fluorescence_lifetime: float = 4.0,
            rC_electron_transfer: float = 1.5,
            **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.diffusion_coefficient = diffusion_coefficient
        self.contact_distance = float(contact_distance) + max(
            self.radius1, self.radius2, self.radius3)
        self.slow_factor = slow_factor
        self.fluorescence_lifetime = fluorescence_lifetime
        self.rC_electron_transfer = rC_electron_transfer
        self._dynamic = None

    def _atom_view(self):
        """ChiSurf's atom array as an upstream ``ObstacleAtoms`` value."""
        from IMP.bff import ObstacleAtoms

        atoms = self.atoms
        view = ObstacleAtoms()
        view.chains = [str(c) for c in atoms["chain"]]
        view.res_ids = [int(r) for r in atoms["res_id"]]
        view.res_names = [str(r) for r in atoms["res_name"]]
        view.atom_names = [str(a) for a in atoms["atom_name"]]
        view.coords = [float(v) for v in np.asarray(atoms["xyz"]).ravel()]
        return view

    @property
    def dynamic(self):
        """The upstream model object, built on first use."""
        if self._dynamic is None:
            from IMP.bff import DynamicAccessibleVolume

            self._dynamic = DynamicAccessibleVolume(
                self._upstream_av,
                self._atom_view(),
                tau0=self.fluorescence_lifetime,
                probe_radius=min(self.radius1, self.radius2, self.radius3),
                free_diffusion=self.diffusion_coefficient,
                contact_distance=self.contact_distance,
                slow_factor=self.slow_factor,
            )
        return self._dynamic

    @property
    def diffusion_map(self):
        """Per-voxel diffusion coefficient (Å²/ns)."""
        return self.dynamic.get_diffusion_map()

    @property
    def quenching_rate_map(self):
        """Per-voxel decay rate (1/ns): intrinsic plus exponential PET."""
        return self.dynamic.get_quenching_rate_map()

    @property
    def fret_rate_map(self):
        """Per-voxel effective FRET rate, once an acceptor has been set."""
        return self.dynamic.get_fret_rate_map()

    @property
    def rate_map(self):
        """Total decay rate per voxel: quenching, plus FRET if set."""
        return self.dynamic.get_rate_map()

    @property
    def excited_state_map(self):
        """The equilibrium occupancy of the volume."""
        return self.dynamic.get_occupancy()

    def update_diffusion_map(self, **kwargs):
        return self.dynamic.update_diffusion_map(**kwargs)

    def update_quenching_map(self, quencher=None, **kwargs):
        """Build the PET quenching field against the protein.

        The default table is ChiSurf's ``structure.json`` ``Quencher`` block —
        ``{RESIDUE: {ATOM: [rate_constant (1/ns), contact_distance (Å)]}}``.
        The rate is the residue-specific number (Trp 2.8, His 1.2, …) and the
        shared 2.9 Å is the contact radius, mapped onto upstream's
        ``PETParameters``. Upstream's own curated tables
        (``reference_quenchers``, ``amino_acid_quenching_defaults``) are the
        alternative; a caller may also pass a ready ``PETParametersMap``.
        """
        from IMP.bff import PETParameters, PETParametersMap

        if quencher is None:
            quencher = chisurf.core.support.common.quencher
        if not isinstance(quencher, PETParametersMap):
            table = PETParametersMap()
            for res, atoms in quencher.items():
                for _atom, pair in atoms.items():
                    rate_constant, contact_distance = pair
                    table[str(res)] = PETParameters(
                        comp_id=str(res),
                        rate_constant=float(rate_constant),
                        contact_distance=float(contact_distance),
                    )
            quencher = table
        return self.dynamic.update_quenching_map(
            quencher, rC=self.rC_electron_transfer)

    def update_fret_map(self, acceptor, forster_radius: float = 52.0, **kwargs):
        """Build the FRET field against an acceptor volume.

        The donor's radiative rate comes from ``tau0``. ChiSurf used to read it
        out of the ``foerster_radius`` keyword by a copy-paste slip
        (``kf = kwargs.get('foerster_radius', 1./tau0)``), so passing a Förster
        radius set the radiative rate to it as well.
        """
        return self.dynamic.update_fret_map(
            acceptor.dynamic if isinstance(acceptor, DynamicAV) else acceptor,
            forster_radius=forster_radius, **kwargs)

    def update_equilibrium(self, **kwargs):
        """Relax the density to its equilibrium occupancy.

        This is what turns a uniform accessible volume into an *occupancy*: with
        a position-dependent diffusion coefficient the dye dwells where it moves
        slowly, and the stationary distribution is not flat. Upstream needs the
        diffusion field in place before the relaxation runs, so make sure of it.
        """
        self.update_diffusion_map()
        self.dynamic.update_occupancy()
        occupancy = self.excited_state_map
        self._density = occupancy
        self._points = None
        return occupancy

    def get_donor_only_decay(
            self,
            t_max: float = None,
            t_step: float = 0.004,
            n_out: int = None,
            n_it: int = None,
            **kwargs
    ):
        """Integrate the donor decay on the grid.

        :param t_step: integration step in ns; upstream's default 0.004.
        :param n_it: number of integration steps; ``t_max = n_it * t_step``
            when ``t_max`` is not given (the spell the AV-decay model uses).
        :param n_out: number of reported samples, default enough for ``t_max``.

        :returns: ``(time, fluorescence, density)`` — the time axis in ns, the
            surviving excited-state fraction, and the final density.
        """
        if n_it is not None:
            t_max = n_it * t_step
        if t_max is None:
            t_max = 50.0
        if n_out is None:
            n_out = int(t_max / t_step) + 1
        result = self.dynamic.donor_decay(
            float(t_max), float(t_step), int(n_out))
        return (
            np.asarray(result.get_time()),
            np.asarray(result.get_fluorescence()),
            np.asarray(result.get_density()),
        )

    @property
    def donor_only_fluorescence(self):
        """``(time, fluorescence)`` of the donor-only decay."""
        time, fluorescence, _density = self.get_donor_only_decay()
        return time, fluorescence

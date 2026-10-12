import os.path
import json
import os
import warnings
from collections import OrderedDict

import numpy as np
# Qt-free: the accessible-volume widget that used to live here was unused, and
# it was the only reason this module imported a GUI toolkit.

from chisurf.plugins.quenching_estimator.core.structure import reader as PDB
from chisurf.plugins.quenching_estimator.core.structure import Structure
from chisurf.plugins.quenching_estimator.core.io import write_xyz

# ---------------------------------------------------------------------------
# `IMP.bff` is a hard dependency
#
# It used to be optional, reached through a development path shim
# (`quest.hosts.imp_tricks`) that spliced `~/dev/imp-tricks/src` onto
# `IMP.__path__`, with LabelLib as a fallback backend and a three-way selector
# in front of both. All of that is gone:
#
#   * **the shim was already dead** — `IMP.bff` moved out of imp-tricks to its
#     own checkout on 2026-08-10, so `~/dev/imp-tricks/src/IMP/bff` no longer
#     exists and the splice found nothing;
#   * **the `arm64` environment is the only one** — the two-environment split
#     and the base interpreter that motivated an optional dependency are
#     retired, so there is no interpreter left that has QuEst but not IMP.bff;
#   * **the selector was a fourth copy** of a choice `IMP.bff` already makes
#     internally, and its own OKF had it down as a deletion candidate.
#
# What remains: `import IMP` is still **lazy**, everywhere in this module.
# `import quest.core` must not pull IMP in — not merely for speed, but because
# a child of a process that has already loaded IMP resolves `libimp_kernel`
# against the wrong `libboost_filesystem`
# (okf/references/known-issues.md).
# ---------------------------------------------------------------------------

def av_defaults() -> dict:
    """The accessible-volume defaults, as ``IMP.bff`` declares them.

    One declaration for every consumer (owner, 2026-10-11: "all use same
    defaults"): FPS's first dye preset and the 0.9 A grid FPS and Olga use for an
    AV1, in IMP.bff's ``ProbeAccessibleVolumeDefaults.h``. A generic or
    placeholder value here reads them rather than restating them; a named dye
    with its own geometry (``settings/dye_repository.json``) keeps that.
    Imported lazily, like everything IMP in this module.
    """
    import IMP.bff

    return {
        "linker_length": float(IMP.bff.AV_DEFAULT_LINKER_LENGTH),
        "linker_width": float(IMP.bff.AV_DEFAULT_LINKER_WIDTH),
        "radius1": float(IMP.bff.AV_DEFAULT_RADIUS1),
        "av3_radii": (
            float(IMP.bff.AV_DEFAULT_AV3_RADIUS1),
            float(IMP.bff.AV_DEFAULT_AV3_RADIUS2),
            float(IMP.bff.AV_DEFAULT_AV3_RADIUS3),
        ),
        "simulation_grid_resolution": float(IMP.bff.AV_DEFAULT_SIMULATION_GRID_RESOLUTION),
    }


def av1_parameter() -> dict:
    """A placeholder dye's ``av_parameter`` block: IMP.bff's AV1 defaults."""
    d = av_defaults()
    return {
        "linker_length": d["linker_length"],
        "linker_width": d["linker_width"],
        "radius1": d["radius1"],
    }


def _get_av():
    """``IMP.bff.get_av``, the array door of IMP.bff's accessible volume, imported on first use.

    It takes the obstacles as one ``(N, 4)`` array of x, y, z, radius and the
    attachment point, and returns an ``IMP.bff.ProbeAccessibleVolume``: a cubic
    ``ng**3`` density in C order whose voxel ``i`` sits at
    ``get_grid_origin() + i * grid_step``. Lazy for the same reason as
    :func:`_density2points_kernel`.
    """
    try:
        import IMP.bff
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "QuEst's accessible volume requires `IMP.bff`, which is not "
            f"importable ({exc}). It is a hard dependency."
        ) from exc
    return IMP.bff.get_av

#: Resolved on first use by :func:`_density2points_kernel`, never at import.
_UPSTREAM_DENSITY2POINTS = None


def _density2points_kernel():
    """`IMP.bff.density_to_points`, imported on first use.

    **Deliberately lazy, and two separate tests depend on it.** Importing
    `IMP.bff.av` pulls in `IMP` itself, and `import quest.core` must not do that:
    `test_importing_the_domain_does_not_import_qt` and `test_the_model_needs_no_qt`
    both probe the domain layer in a subprocess, and a module-scope import here
    made both fail. Not with an ImportError either -- with the dylib conflict in
    [references/known-issues.md](../../okf/references/known-issues.md), where a
    child of a process that has already loaded IMP resolves
    `libimp_kernel` against the *base* environment's `libboost_filesystem`. So a
    module-scope import would have taken a documented latent environment fault
    and made it a hard failure of the service layer.

    Deferring costs nothing: this is reached once per accessible volume, and the
    result is cached in a module global.

    Not guarded, once it is actually needed. imp-tricks is a declared dependency
    as of 2026-07-28 ([specs/imp-tricks-dedup.md](../../okf/specs/imp-tricks-dedup.md)),
    and a fallback could only mean keeping the second copy of this kernel that
    the import exists to delete. The message names the cause, because a bare
    ImportError deep inside a simulation names nothing.
    """
    global _UPSTREAM_DENSITY2POINTS
    if _UPSTREAM_DENSITY2POINTS is None:
        try:
            from IMP.bff import density_to_points
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise ImportError(
                "QuEst's accessible volume requires `IMP.bff`, which is not "
                "importable. It is a hard dependency."
            ) from exc
        _UPSTREAM_DENSITY2POINTS = density_to_points
    return _UPSTREAM_DENSITY2POINTS


#: The one accessible-volume backend. LabelLib was dropped when the quenching model moved into IMP.bff.
#:
#: The two never agreed exactly and the difference was never small: on 148l E36
#: they returned 136 707 (IMP.bff) against 151 869 (LabelLib) points — the same
#: place, ~10 % less of it, with centroids within 0.5 A — so contact fractions
#: and quenching rates were never bit-comparable across them. Keeping a second
#: answer reachable by an environment variable meant a number could change
#: without anything in the project saying so.
AV_BACKEND = "imp_bff"

#: Kept as a one-element tuple: the shape of the public constant, one backend.
AV_BACKENDS = (AV_BACKEND,)


def available_av_backends():
    """The accessible-volume backends this interpreter can reach.

    One, always — `IMP.bff` is a hard dependency. Kept so callers and
    the RPC contract that asked this question still get an answer.
    """
    return [AV_BACKEND]


def resolve_av_backend(preference=None):
    """Validate a requested backend name.

    ``None`` and ``"auto"`` mean :data:`AV_BACKEND`. Anything else must name it
    exactly; ``"labellib"`` now raises rather than silently selecting a backend
    that no longer exists.
    """
    choice = str(preference or "auto").strip().lower()
    if choice in ("auto", AV_BACKEND):
        return AV_BACKEND
    raise ValueError(
        f"Unknown accessible-volume backend {choice!r}; `IMP.bff` "
        f"({AV_BACKEND!r}) is the only one. The LabelLib backend was removed "
        "when the quenching model moved into IMP.bff."
    )


#: Radius around the attachment atom inside which obstacles are ignored, so the
#: linker can leave the atom it is tied to.
#:
#: **One project-level value, 2.1 A**, replacing QuEst's 0.5 default and the
#: separate 2.0 clamp IMP's path got. 2.1 A is carbon's CHARMM radius -- the
#: attachment atom is a CB in every default workflow, and the sphere that lets
#: the linker escape it should be the size of that atom. It also sits just above
#: the cliff below which IMP's path search starts nowhere and returns an **empty
#: volume with no error**; imp.bff's own reference test uses 2.0 and expects zero
#: points at 1.0.
#:
#: **Only the IMP.bff backend honours it.** `ll.dyeDensityAV1` has no such
#: parameter; the LabelLib path zeroes the attachment atom's own vdW radius
#: instead. Measured: raising the default from 0.5 to 2.1 moves LabelLib's
#: labelable-site count on 148l chain E by exactly nothing (43/151 before and
#: after), while IMP.bff goes 147 -> 151/151 and quenching sites 60 -> 67.
#:
#: That is also the correction to a claim made when IMP.bff was promoted: the
#: 43-vs-147 gap between the backends is **not** mostly this parameter, it is
#: how each treats the attachment site. LabelLib frees only the attachment atom,
#: so a CB hemmed in by CHARMM-sized neighbours has no way out; IMP ignores every
#: obstacle within the sphere.
DEFAULT_ALLOWED_SPHERE_RADIUS = 2.1

#: Smallest `allowed_sphere_radius` that IMP.bff's path search can start from.
#: Only reachable now by asking for less than the default explicitly; the clamp
#: warns rather than silently substituting, because a quietly changed parameter
#: is how the backends drifted apart in the first place. LabelLib has no such
#: cliff -- it zeroes the attachment atom's radius instead.
MIN_IMP_ALLOWED_SPHERE_RADIUS = 2.0


def _clamped_allowed_sphere_radius(value):
    """Keep IMP's path search above the cliff, and say so when it has to.

    The old code clamped silently. That is how a caller asking for 0.5 got 2.0
    and never learned the number it reasoned about was not the number that ran.
    """
    radius = float(value)
    if radius >= MIN_IMP_ALLOWED_SPHERE_RADIUS:
        return radius
    warnings.warn(
        f"allowed_sphere_radius={radius:g} A is below "
        f"{MIN_IMP_ALLOWED_SPHERE_RADIUS:g} A, where IMP.bff's path search "
        f"starts nowhere and returns an empty volume without reporting one. "
        f"Using {MIN_IMP_ALLOWED_SPHERE_RADIUS:g} A instead; the default is "
        f"{DEFAULT_ALLOWED_SPHERE_RADIUS:g} A.",
        RuntimeWarning,
        stacklevel=3,
    )
    return MIN_IMP_ALLOWED_SPHERE_RADIUS


def _points_from_centred_grid(density, ng, dg, centre):
    """Point cloud of a cubic grid described by its *centre* rather than a corner.

    QuEst's AV carries ``x0`` (the grid anchor, at the middle voxel); LabelLib
    reported a corner. One kernel, two conventions, one shift.

    The offset is the **integer** ``(ng - 1) // 2``, matching every grid stamp
    here. For an odd edge the two agree; for an even one — which is what IMP
    produces — a float ``(ng - 1) / 2`` would place the cloud half a voxel off
    the grid the quenching and stickiness kernels index into.

    Plain Python on purpose: it does arithmetic on three numbers and then calls
    the jitted kernel.
    """
    origin = np.asarray(centre, dtype=np.float64) - ((ng - 1) // 2) * float(dg)
    return density2points(ng, ng, ng, dg, density, origin)


#: Default seed for the AV pair sampling. Fixed on purpose -- see
#: :func:`_sample_pair_distances`.
RDA_SAMPLING_SEED = 0


#: Resolved on first use by :func:`_pair_distance_kernels`, never at import.
_UPSTREAM_PAIR_KERNELS = None


def _pair_distance_kernels():
    """`random_distances` and `av_pair_statistics`, imported on first use.

    Lazy for the same reason as :func:`_density2points_kernel` -- importing
    `IMP.bff` reaches `IMP`, and `import quest.core` must not.
    """
    global _UPSTREAM_PAIR_KERNELS
    if _UPSTREAM_PAIR_KERNELS is None:
        try:
            from IMP.bff import distance_sample_statistics as av_pair_statistics
            from IMP.bff import random_distances
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise ImportError(
                "QuEst's donor-acceptor distances require `IMP.bff`, which "
                "is not importable. It is a hard dependency."


            ) from exc
        _UPSTREAM_PAIR_KERNELS = (random_distances, av_pair_statistics)
    return _UPSTREAM_PAIR_KERNELS


def _sample_pair_distances(av1, av2, n_samples, seed=RDA_SAMPLING_SEED):
    """Sampled distances and weights between two AV point clouds.

    `IMP.bff.random_distances` as of 2026-07-28 (`DUP-03`); QuEst's
    own `_ran_dist` is deleted. Two consequences, both measured rather than
    assumed on 148l E15/E90 (64 969 x 71 873 points, 50 000 samples):

    **The numbers agree and the timing does not.** ⟨R_DA⟩ 55.164 ± 0.037 A
    (QuEst) against 55.171 ± 0.032 (upstream), ⟨R_DA⟩_E 54.467 ± 0.022 against
    54.473 ± 0.029 — inside the sampling noise of either. But upstream costs
    **3.4 ms a call against 0.68 ms**, because QuEst's kernel was
    ``parallel=True`` where upstream's is sequential, and because upstream takes
    ``(N, 4)`` points so the cloud has to be widened with a weight column first
    (0.87 ms of the 3.4). Accepted, not overlooked: this runs **once per
    simulation** as a diagnostic, so a 2.7 ms regression is ~0.4 s across a
    151-site scan. Do not adopt this kernel anywhere it runs per frame.

    **Results are now reproducible, which they were not.** Upstream seeds
    explicitly; QuEst's parallel kernel drew from an unseeded per-thread RNG, so
    two calls on the same clouds gave different answers. A reported distance
    that changes between runs is a defect, so the fixed default stays and the
    seed is a parameter rather than a constant.

    The weight column is all ones: QuEst's density grids are binary, so the
    weighted mean upstream computes reduces to the plain one QuEst took.
    """
    random_distances, _ = _pair_distance_kernels()
    n_samples = int(n_samples)

    def _weighted(points):
        # Upstream's signature is (x, y, z, weight); QuEst's clouds are (x, y, z).
        wide = np.ones((points.shape[0], 4), dtype=np.float64)
        wide[:, :3] = points
        return wide

    sample = random_distances(
        _weighted(av1.points), _weighted(av2.points), n_samples, int(seed)
    )
    # Contiguous copies: `av_pair_statistics` does two `np.dot`s, and a strided
    # column view makes them slower than they need be.
    return (
        np.ascontiguousarray(sample[:, 0]),
        np.ascontiguousarray(sample[:, 1]),
    )


def RDAMeanE(av1, av2, R0: float = 52.0, nSamples: int = 50_000, seed: int = RDA_SAMPLING_SEED):
    """Forster-averaged donor-acceptor distance <R_DA>_E, in Angstrom.

    ``R0`` is in Angstrom, matching the AV point clouds. This is the average a
    FRET-efficiency measurement reports; it is not interchangeable with the
    plain mean distance :func:`RDAMean` or the mean-position distance
    :func:`dRmp`.
    """
    distances, weights = _sample_pair_distances(av1, av2, nSamples, seed)
    _, av_pair_statistics = _pair_distance_kernels()
    # `IMP.bff.distance_sample_statistics`: (mean, R_E, <E>, sd). R_mp is not
    # among them -- see :func:`dRmp`. (The retired `av_pair_statistics` had R_E
    # at index 2 behind a NaN slot 1.)
    return float(av_pair_statistics(distances, weights, float(R0))[1])


#: The isotropic dynamic average of the orientation factor.
#:
#: A published Förster radius is quoted *at* this value, so the transfer rate
#: carries the ratio ``kappa2 / ISOTROPIC_KAPPA2`` -- equivalently the
#: ``1.5 * kappa2`` that appears in the literature -- and passing 2/3 leaves the
#: rate exactly as it was.
ISOTROPIC_KAPPA2 = 2.0 / 3.0

#: kappa2 ranges over [0, 4]: 0 for perpendicular dipoles, 4 for collinear ones.
MAX_KAPPA2 = 4.0


def _kappa2_scale(kappa2) -> float:
    """Convert an orientation factor into a multiplier on ``R0**6``.

    **QuEst does not model kappa2**, and cannot: its dye is a structureless
    point diffusing in a volume, with no transition dipole to orient. What this
    does is make the *assumption* explicit and adjustable instead of silently
    baked into R0 (okf/specs/objectives.md, OBJ-01 item 6).

    Modelling it would need a rotational degree of freedom per dye and a
    correlation time to go with it -- a change to the physics, not a call to a
    library. `IMP.bff.cgdye.rotamer.scoring.kappa2_from_vectors` computes it,
    but it takes the two transition dipole vectors, which is exactly what QuEst
    has not got.
    """
    value = float(ISOTROPIC_KAPPA2 if kappa2 is None else kappa2)
    if not np.isfinite(value) or value < 0.0 or value > MAX_KAPPA2:
        raise ValueError(
            f"kappa2 must be in [0, {MAX_KAPPA2:g}] (0 = perpendicular dipoles, "
            f"4 = collinear); got {value!r}."
        )
    return value / ISOTROPIC_KAPPA2


def RDAMean(av1, av2, nSamples: int = 50_000, seed: int = RDA_SAMPLING_SEED):
    """Mean donor-acceptor distance <R_DA>, in Angstrom."""
    distances, weights = _sample_pair_distances(av1, av2, nSamples, seed)
    _, av_pair_statistics = _pair_distance_kernels()
    return float(av_pair_statistics(distances, weights, 52.0)[0])


def dRmp(av1, av2):
    """Distance between the two clouds' mean positions, in Angstrom.

    **The arrow pointed upstream here, and the migration has now happened.**
    `av_pair_statistics` used to return this as its second value, and it was
    wrong: its own docstring conceded "same as ``r_da_mean`` here", i.e. it
    returned the mean *pair distance* under the name R_mp. R_mp is
    ``|<r_D> - <r_A>|``, which cannot be recovered from a sample of pair
    distances at all -- the sampling destroys exactly the information it needs.
    Measured on 148l E15/E90: 47.65 A against 51.53 A, 8 % apart.

    QuEst's implementation was contributed to imp-tricks as
    `IMP.bff.distance_metrics.mean_position_distance`, and slot 1 of
    `av_pair_statistics` is now **NaN** so that reading it fails loudly rather
    than silently returning a different quantity. This delegates.
    """
    from IMP.bff import mean_position_distance

    return mean_position_distance(
        np.ascontiguousarray(av1.points, dtype=np.float64).ravel(),
        np.ascontiguousarray(av2.points, dtype=np.float64).ravel(),
    )


# ---------------------------------------------------------------------------
# Grid stamps, the Brownian walk, ASA and the FRET rate traces -- IMP.bff's C++
#
# All of it is general fluorescence machinery and lives in IMP.bff's compiled
# core, flat in its namespace (`IMP.bff.slow_factor_grid`, ...). The C++ kernels
# are "flat in, flat out": they take and return 1-D buffers, and the
# `(ng, ng, ng)` reshape and the float64/uint8 dtypes are the caller's, so they
# live here. Imports are lazy -- `IMP.bff` reaches `IMP`, and importing this
# package must not.
# ---------------------------------------------------------------------------


def _flat(values, dtype=np.float64):
    return np.ascontiguousarray(values, dtype=dtype).ravel()


def cxx_seed(random_seed) -> int:
    """A seed as IMP.bff's C++ takes it: a non-negative ``int``, or -1 to draw freely.

    The trajectory seeds are drawn as ``uint32`` (``SeedSequence.generate_state``),
    half of which do not fit a C ``int``; they are folded into 31 bits rather than
    rejected, which keeps every seed distinct from -1 and reproducible.
    """
    return -1 if random_seed is None else int(random_seed) & 0x7FFFFFFF


def grid_center_index(ng):
    """The voxel index that the grid anchor ``x0`` sits on.

    **One convention, everywhere**: the integer ``(ng - 1) // 2``. The float
    corner ``(ng - 1) / 2`` differs on every *even* edge length -- which is the
    normal case here, not an edge case -- and integer voxel indexing cannot
    express it.
    """
    from IMP.bff import grid_center_index as _upstream

    return int(_upstream(int(ng)))


def center_grid_indices(rs, r0, dg, ng, radius):
    """Voxel indices ``(ix, iy, iz)`` and integer radii of sphere centres (``floor``, not truncation)."""
    from IMP.bff import center_grid_indices as _upstream

    ix, iy, iz, ridx = _upstream(_flat(rs), _flat(r0), float(dg), int(ng), _flat(radius))
    return tuple(np.asarray(v, dtype=np.int64) for v in (ix, iy, iz, ridx))


def _cube(values, ng, dtype=np.float64):
    ng = int(ng)
    return np.asarray(values, dtype=dtype).reshape(ng, ng, ng)


def slow_factor_grid(density, ng, dg, slow_radius, rs, r0, slow_fact):
    """Per-voxel diffusion scaling from overlapping sticky spheres (they multiply)."""
    from IMP.bff import slow_factor_grid as _upstream

    return _cube(_upstream(_flat(density), int(ng), float(dg), _flat(slow_radius), _flat(rs),
                           _flat(r0), _flat(slow_fact)), ng)


def additive_factor_grid(density, ng, dg, radius, rs, r0, values):
    """Per-voxel quenching rate from overlapping quencher spheres (they add)."""
    from IMP.bff import quenching_rate_grid as _upstream

    return _cube(_upstream(_flat(density), int(ng), float(dg), _flat(radius), _flat(rs),
                           _flat(r0), _flat(values)), ng)


def subav(density, ng, dg, slow_radius, rs, r0):
    """The contact ("slow") part of a density grid, as a binary ``uint8`` mask of the density's shape."""
    from IMP.bff import av_contact_mask as _upstream

    shape = np.shape(density)
    mask = _upstream(_flat(density), int(ng), float(dg), _flat(slow_radius), _flat(rs), _flat(r0))
    return np.ascontiguousarray(np.asarray(mask).reshape(shape) > 0, dtype=np.uint8)


def simulate_traj(d, ds, dg, t_max, t_step, D, slow_fact, random_seed=None):
    """One Brownian trajectory of the dye centre in its accessible volume.

    Returns ``(xyz, accepted, n_accepted, n_rejected)`` with ``xyz`` of shape
    ``(n_frames, 3)``, relative to the grid anchor. ``slow_fact`` is a scalar
    applied inside ``ds`` or a ``(ng, ng, ng)`` mobility field
    (:func:`IMP.bff.simulate_probe_diffusion` builds the field from either).
    """
    from IMP.bff import simulate_probe_diffusion

    slow = np.asarray(1.0 if slow_fact is None else slow_fact, dtype=np.float64)
    slow_density = [] if ds is None else _flat(ds, np.int32)
    walk = simulate_probe_diffusion(
        _flat(d, np.int32), slow_density, float(dg), float(t_max), float(t_step), float(D),
        slow.ravel(), cxx_seed(random_seed),
    )
    xyz = np.asarray(walk.get_xyz(), dtype=np.float64).reshape(-1, 3)
    accepted = np.asarray(walk.get_accepted())
    return xyz, accepted, int(walk.n_accepted), int(walk.n_rejected)


def spherePoints(nSphere: int):
    """``nSphere`` roughly equidistant points on the unit sphere, ``(n, 3)``."""
    from IMP.bff import sphere_points

    return np.asarray(sphere_points(int(nSphere)), dtype=np.float64).reshape(-1, 3)


def asa(r, vdw, probe_atom_indices, sphere_points, probe=1.0, radius=2.5):
    """Solvent-accessible surface area of the probe atoms."""
    from IMP.bff import solvent_accessible_surface

    points = [] if sphere_points is None else _flat(sphere_points)
    return np.asarray(
        solvent_accessible_surface(
            _flat(r), _flat(vdw), [int(i) for i in np.asarray(probe_atom_indices).ravel()],
            points, float(probe), float(radius),
        ),
        dtype=np.float64,
    )


def _kappa2_or_isotropic(kappa2) -> float:
    return ISOTROPIC_KAPPA2 if kappa2 is None else float(kappa2)


def fret_rate_trace(
    trajectory, acceptor_points, R0: float, tau0: float, r_min: float = 7.0,
    max_acceptor_points: int = 512, kappa2=None,
):
    """Per-frame FRET rate (1/ns) along a donor trajectory, acceptor averaged.

    The fast-acceptor limit: the acceptor is treated as sampling its own volume
    quickly compared with the donor's excited-state lifetime. ``kappa2=None`` is
    the isotropic 2/3.
    """
    from IMP.bff import fret_rate_trace as _upstream

    return np.asarray(_upstream(
        _flat(trajectory), _flat(acceptor_points), float(R0), float(tau0), float(r_min),
        int(max_acceptor_points), _kappa2_or_isotropic(kappa2),
    ))


def fret_rate_pair_trace(
    donor_trajectory, acceptor_trajectory, R0: float, tau0: float,
    r_min: float = 7.0, kappa2=None,
):
    """Per-frame FRET rate (1/ns) from two frame-aligned trajectories."""
    from IMP.bff import fret_rate_pair_trace as _upstream

    return np.asarray(_upstream(
        _flat(donor_trajectory), _flat(acceptor_trajectory), float(R0), float(tau0),
        float(r_min), _kappa2_or_isotropic(kappa2),
    ))


def density2points(nx, ny, nz, dg, density, r0):
    """Occupied voxels of a density grid, as an ``(n, 3)`` cloud in Angstrom.

    *r0* is the centre of voxel ``(0, 0, 0)``.
    """
    grid = np.ascontiguousarray(np.asarray(density, dtype=np.float64).reshape(int(nx), int(ny), int(nz)))
    points = _density2points_kernel()(grid, float(dg), _flat(r0))
    # (n, 4) of x, y, z, density; QuEst's grids are binary, so the weight
    # column carries nothing here.
    return np.ascontiguousarray(np.asarray(points, dtype=np.float64)[:, :3])


class AV(object):

    def __init__(self, structure, residue_seq_number=None, atom_name=None, chain_identifier=None,
                 linker_length=None, linker_width=None, radius1=None,
                 radius2=None, radius3=None, simulation_grid_resolution=None, save_av=False, output_file='out',
                 attachment_atom_index=None, verbose=False,
                 allowed_sphere_radius=DEFAULT_ALLOWED_SPHERE_RADIUS,
                 simulation_type='AV1', position_name=None, residue_name=None,
                 av_backend=None):

        """
        Parameters
        ----------
        :param structure: Structure of str
            either string with path of pdb-file or pdb object
        :param residue_seq_number:
        :param atom_name:
        :param chain_identifier:
        :param linker_length:
        :param linker_width:
        :param radius1:
        :param radius2:
        :param radius3:
        :param simulation_grid_resolution:
        :param save_av:
        :param output_file:
        :param attachment_atom_index:
        :param verbose:
        :param allowed_sphere_radius:
        :param simulation_type:
        :param position_name:
        :param residue_name:
        :raise ValueError:

        Examples
        --------
        Calculating accessible volume using provided pdb-file
        >>>         >>> pdb_filename = '/sample_data/structure/T4L_Topology.pdb'
        >>> residue_number = 18
        >>> atom_name = 'CB'
        >>> attachment_atom = 1
        >>> av = lib.fps.AV(pdb_filename, attachment_atom=1, verbose=True)

        Calculating accessible volume using provided Structure object
        >>>         >>> pdb_filename = '/sample_data/structure/T4L_Topology.pdb'
        >>> structure = lib.Structure(pdb_filename)
        >>> av = lib.fps.AV(structure, attachment_atom=1, verbose=True)
        Calculating accessible volume
        -----------------------------
        Loading PDB
        Calculating initial-AV
        Linker-length  : 20.00
        Linker-width   : 0.50
        Linker-radius  : 5.00
        Attachment-atom: 1
        AV-resolution  : 0.50
        AV: calculate1R
        Number of atoms: 2647
        Attachment atom: [ 33.28   58.678  40.397]
        Points in AV: 111911
        Points in total-AV: 111911

        Using residue_seq_number and atom_name to calculate accessible volume, this also works without
        chain_identifier. However, only if a single-chain is present.
        >>>         >>> pdb_filename = '/sample_data/structure/T4L_Topology.pdb'
        >>> structure = lib.Structure(pdb_filename)
        >>> av = lib.fps.AV(structure, residue_seq_number=11, atom_name='CB', verbose=True)

        If save_av is True the calculated accessible volume is save to disk. The filename of the calculated
        accessible volume is determined by output_file
        >>>         >>> pdb_filename = '/sample_data/structure/T4L_Topology.pdb'
        >>> structure = lib.Structure(pdb_filename)
        >>> av = lib.fps.AV(structure, residue_seq_number=11, atom_name='CB', verbose=True, save_av=True, output_file='test')
        Calculating accessible volume
        -----------------------------
        Loading PDB
        Calculating initial-AV
        Linker-length  : 20.00
        Linker-width   : 0.50
        Linker-radius  : 5.00
        Attachment-atom: 174
        AV-resolution  : 0.50
        AV: calculate1R
        Number of atoms: 2647
        Attachment atom: [ 41.606  44.953  36.625]
        Points in AV: 22212
        Points in total-AV: 22212

        write_xyz
        ---------
        Filename: test.xyz
        -------------------

        """
        # ``None`` is "not chosen": IMP.bff's declared default (was 20/0.5/5.0 at
        # a 0.5 A grid, with AV3 radii 4.5/3.5 -- this class's own guesses).
        if None in (linker_length, linker_width, radius1, radius2, radius3,
                    simulation_grid_resolution):
            _d = av_defaults()
            linker_length = _d["linker_length"] if linker_length is None else linker_length
            linker_width = _d["linker_width"] if linker_width is None else linker_width
            radius1 = _d["radius1"] if radius1 is None else radius1
            radius2 = _d["av3_radii"][1] if radius2 is None else radius2
            radius3 = _d["av3_radii"][2] if radius3 is None else radius3
            if simulation_grid_resolution is None:
                simulation_grid_resolution = _d["simulation_grid_resolution"]
        # Rejected first, before the structure is even read. `simulation_type` is
        # a project field a scan can set, and "AV3" used to reach a `calculate3R`
        # deleted back in 7ecf209 -- so it raised `NameError: name 'calculate3R'
        # is not defined`, from eight frames inside a simulation, naming nothing
        # a caller could act on. Neither backend has ever implemented AV3 here:
        # the IMP.bff path ignores `simulation_type` outright, and `calculate1R`
        # drives `ll.dyeDensityAV1`. Say so, and say it before doing any work.
        if str(simulation_type).upper() != "AV1":
            raise ValueError(
                "simulation_type=%r is not supported; QuEst computes AV1 only. "
                "The three-radius model (AV3) reached a function that no longer "
                "exists and has never worked in this tree." % (simulation_type,)
            )
        self.verbose = verbose
        self.points_slow = None
        self.position_name = position_name
        self.residue_name = residue_name
        if verbose:
            print("")
            print("Calculating accessible volume")
            print("-----------------------------")
        if isinstance(structure, Structure):
            atoms = structure.atoms
        else:
            if verbose:
                print("Loading PDB")
            atoms = PDB.read(structure, verbose=verbose)
        # The split-out x/y/z/vdw columns went with `calculate1R`; `compute_av`
        # takes the coordinate and radius arrays whole.
        self.structure = structure
        self.dg = simulation_grid_resolution
        self.output_file = output_file

        # Determine Labeling position
        if verbose:
            print("Labeling position")
            print("Chain ID: %s" % chain_identifier)
            print("Residue seq. number: %s" % residue_seq_number)
            print("Residue name: %s" % residue_name)
            print("Atom name: %s" % atom_name)

        def _decode(value):
            if isinstance(value, bytes):
                return value.decode().strip()
            if isinstance(value, np.bytes_):
                return value.tobytes().decode().strip()
            if isinstance(value, np.str_):
                return str(value).strip()
            return str(value).strip()

        if attachment_atom_index is None:
            if residue_seq_number is None or atom_name is None:
                raise ValueError("either attachment_atom number or residue and atom_name have to be provided.")
            self.attachment_residue = residue_seq_number
            self.attachment_atom = atom_name
            if chain_identifier is None:
                attachment_atom_index = np.where((atoms['res_id'] == residue_seq_number) &
                                                (atoms['atom_name'] == atom_name))[0]
            else:
                attachment_atom_index = np.where((atoms['res_id'] == residue_seq_number) &
                                                 (atoms['atom_name'] == atom_name) &
                                                 (atoms['chain'] == chain_identifier))[0]
            if len(attachment_atom_index) != 1:
                # Name the selection: a project with two dyes hits this for the
                # acceptor as readily as for the donor, and the bare message
                # gave no way to tell which one was wrong.
                site = "%s%s:%s" % (
                    "" if chain_identifier is None else "%s:" % chain_identifier,
                    residue_seq_number,
                    atom_name,
                )
                if len(attachment_atom_index) == 0:
                    raise ValueError(
                        "No attachment atom %s in the structure." % site
                    )
                raise ValueError(
                    "Attachment atom %s is ambiguous: it matches %d atoms."
                    % (site, len(attachment_atom_index))
                )
            else:
                attachment_atom_index = attachment_atom_index[0]
            if verbose:
                print("Atom index: %s" %attachment_atom_index)
        else:
            if residue_seq_number is None:
                residue_seq_number = int(atoms['res_id'][attachment_atom_index])
            if atom_name is None:
                atom_name = _decode(atoms['atom_name'][attachment_atom_index])
            if chain_identifier is None:
                chain_identifier = _decode(atoms['chain'][attachment_atom_index])
            self.attachment_residue = residue_seq_number
            self.attachment_atom = atom_name

        if verbose:
            print("Calculating initial-AV")
            print("Linker-length  : %.2f" % linker_length)
            print("Linker-width   : %.2f" % linker_width)
            print("Linker-radius  : %.2f" % radius1)
            print("Attachment-atom: %i" % attachment_atom_index)
            print("AV-resolution  : %.2f" % simulation_grid_resolution)
        backend = resolve_av_backend(av_backend)
        self.av_backend = backend
        if verbose:
            print("AV backend    : %s" % backend)
        # `IMP.bff.get_av`, the array door: the obstacles as one (N, 4) x/y/z/radius
        # array (the attachment atom among them -- `allowed_sphere_radius` frees
        # it) and the attachment point.
        coords = np.asarray(atoms["coord"], dtype=np.float64)
        xyzr = np.ascontiguousarray(
            np.hstack([coords, np.asarray(atoms["radius"], dtype=np.float64).reshape(-1, 1)])
        )
        av_result = _get_av()(
            xyzr,
            [float(v) for v in coords[attachment_atom_index]],
            float(linker_length),
            float(linker_width),
            float(radius1),
            0.0,
            0.0,
            float(simulation_grid_resolution),
            float(_clamped_allowed_sphere_radius(allowed_sphere_radius)),
        )

        ng = int(av_result.ng)
        flat_density = np.asarray(av_result.get_density())
        if flat_density.size != ng ** 3:
            raise ValueError(
                "Accessible-volume grid is not cubic (%d values for ng=%d); every grid "
                "kernel here takes a single edge length." % (flat_density.size, ng)
            )
        # QuEst's kernels test `density > 0`: binarise, as the uint8 the in-tree
        # code produced. The flat density is C-ordered.
        density = np.ascontiguousarray(
            (flat_density.reshape(ng, ng, ng) > 0.0).astype(np.uint8)
        )
        grid_origin = np.asarray(av_result.get_grid_origin(), dtype=np.float64).reshape(3)

        # **Both backends anchor the same way, since 2026-07-28.** `x0` is the
        # position of voxel `grid_center_index(ng)` -- the map's own origin
        # advanced by that many voxels -- so voxel `i` sits at
        # `x0 + (i - grid_center_index(ng)) * dg` on either path, which is the
        # map `_center_grid_indices` inverts when it stamps a quenching or
        # stickiness grid.
        #
        # The LabelLib branch used the **attachment atom's coordinate** instead.
        # IMP and LabelLib both size the grid themselves and the atom lands on a
        # voxel node only when the edge length is odd -- it is 86 and 92 on the
        # two reference sites, both even -- so on that path every grid the
        # kernels indexed was registered half a voxel from the density it was
        # built against. `points` is unchanged by this: it is derived from
        # `grid_origin` either way, and `_points_from_centred_grid(…, x0)` is
        # `density2points(…, grid_origin)` by construction.
        npm = grid_center_index(ng)
        x0 = grid_origin + npm * float(simulation_grid_resolution)
        points = _points_from_centred_grid(density, ng, simulation_grid_resolution, x0)

        self.ng = ng
        self.points = points
        if len(points) == 0:
            chain_str = f" on chain '{chain_identifier}'" if chain_identifier else ""
            raise ValueError(
                f"Accessible Volume is empty (0 points). Residue {residue_seq_number} ({atom_name}){chain_str} "
                f"might be buried inside the protein."
            )
        self.points_fast = points.copy()
        self.density_fast = density
        self.density_slow = None
        self.slow_factor_grid = None
        self.k_quench_grid = None
        self.density = density
        self.x0 = x0
        if verbose:
            print("Points in total-AV: %i" % density.sum())
        if save_av:
            write_xyz(output_file + '.xyz', points, verbose=verbose)

    def calc_slow_av(
            self, slow_centers=None, slow_radius=None, save=True, verbose=True, replace_density=False,
            slow_fact=None, quench_radius=None, k_quench=None, quench_centers=None):
        """
        Calculates a subav given the accessible volume determined during class initiation.
        : list/numpy array of points dimension (npoints, 3)


        Parameters
        ----------
        :param slow_centers : array_like
             A list of Cartesian coordinated representing the slow centers. The shape should be (n,3)
             where n is the number of slow centers.
        :param slow_radius : array_like, or float
            A list of radii the shape
        :param slow_fact : array_like, float, or None
            Optional per-center diffusion scaling factors used to build a
            spatial slow-factor grid. Points affected by overlapping centers
            multiply all contributing factors.
        :param quench_centers : array_like, or None
            Optional Cartesian coordinates of the quenching centres, shape
            (n, 3), matching ``k_quench``. Defaults to ``slow_centers``. Passing
            separate centres lets the quenching rate be evaluated at each
            residue's redox-active moiety while stickiness stays on CB.
        :param quench_radius : array_like, float, or None
            Contact radius per quenching centre. Defaults to ``slow_radius``.
        :param k_quench : array_like, float, or None
            Quenching rate contributed by each centre inside its contact
            radius. Contributions of overlapping centres add up.
        :param replace_density : bool
            If replace_density is True the AV-density will be replaced by the density of the slow
            accessible volume
        :param verbose : bool
        :param save : bool
            If save is True the slow-accessible volume is saved to an xyz-file with the suffix '_slow'

        """
        verbose = verbose or self.verbose
        if verbose:
            print("Calculating slow-AV:")
            print(slow_centers)
        if isinstance(slow_radius, (int, float)):
            slow_radii = np.ones(slow_centers.shape[0])*slow_radius
        elif len(slow_radius) != slow_centers.shape[0]:
            raise ValueError("The size of the slow_radius doesnt match the number of slow_centers")
        else:
            slow_radii = np.asarray(slow_radius, dtype=np.float64)

        if slow_fact is None:
            slow_facts = None
        elif isinstance(slow_fact, (int, float)):
            slow_facts = np.ones(slow_centers.shape[0], dtype=np.float64) * float(slow_fact)
        elif len(slow_fact) != slow_centers.shape[0]:
            raise ValueError("The size of the slow_fact doesnt match the number of slow_centers")
        else:
            slow_facts = np.asarray(slow_fact, dtype=np.float64)

        if quench_centers is None:
            quench_points = slow_centers
        else:
            quench_points = np.asarray(quench_centers, dtype=np.float64).reshape((-1, 3))
            if quench_points.shape[0] != slow_centers.shape[0]:
                raise ValueError("The number of quench_centers doesnt match the number of slow_centers")

        if quench_radius is None:
            quench_radii = slow_radii
        elif isinstance(quench_radius, (int, float)):
            quench_radii = np.ones(quench_points.shape[0]) * quench_radius
        elif len(quench_radius) != quench_points.shape[0]:
            raise ValueError("The size of the quench_radius doesnt match the number of quench_centers")
        else:
            quench_radii = np.asarray(quench_radius, dtype=np.float64)

        if k_quench is None:
            k_quench_values = None
        elif isinstance(k_quench, (int, float)):
            k_quench_values = np.ones(quench_points.shape[0], dtype=np.float64) * float(k_quench)
        elif len(k_quench) != quench_points.shape[0]:
            raise ValueError("The size of the k_quench doesnt match the number of quench_centers")
        else:
            k_quench_values = np.asarray(k_quench, dtype=np.float64)

        if verbose or self.verbose:
            print("Calculating slow AV")
            print("slow centers: \n%s" % slow_centers)

        ng = int(self.ng)
        npm = int((ng - 1) // 2)
        density = self.density_fast
        dg = self.dg
        x0 = self.x0
        slow_density = subav(density, ng, dg, slow_radii, slow_centers, x0)
        n = slow_density.sum()
        points = _points_from_centred_grid(slow_density.reshape(ng, ng, ng), ng, dg, x0)
        if slow_facts is None:
            self.slow_factor_grid = None
        else:
            self.slow_factor_grid = slow_factor_grid(density, ng, dg, slow_radii, slow_centers, x0, slow_facts)
        if k_quench_values is None:
            self.k_quench_grid = None
        else:
            self.k_quench_grid = additive_factor_grid(density, ng, dg, quench_radii, quench_points, x0, k_quench_values)
        if verbose or self.verbose:
            print("Points in slow-AV: %i" % n)
        if save:
            write_xyz(self.output_file + '_slow.xyz', points, verbose=verbose)
        self.density_slow = slow_density
        self.points_slow = points
        if replace_density:
            self.density = slow_density

    @property
    def Rmp(self):
        return self.points.mean(axis=0)

    def dRmp(self, av):
        """
        Calculate the distance between the mean positions with respect to the accessible volume `av`

        Parameters
        ----------
        av : accessible volume object

        Example
        -------
        >>>         >>> pdb_filename = '/sample_data/structure/T4L_Topology.pdb'
        >>> structure = lib.Structure(pdb_filename)
        >>> av1 = lib.fps.AV(structure, residue_seq_number=72, atom_name='CB')
        >>> av2 = lib.fps.AV(structure, residue_seq_number=134, atom_name='CB')
        >>> av1.dRmp(av2)
        """
        return dRmp(self, av)

    def dRDA(self, av):
        """
        Calculate the mean distance to the second accessible volume `av`

        Parameters
        ----------
        av : accessible volume object

        Example
        -------
        >>>         >>> pdb_filename = '/sample_data/structure/T4L_Topology.pdb'
        >>> structure = lib.Structure(pdb_filename)
        >>> av1 = lib.fps.AV(structure, residue_seq_number=72, atom_name='CB')
        >>> av2 = lib.fps.AV(structure, residue_seq_number=134, atom_name='CB')
        >>> av1.dRDA(av2)
        """
        return RDAMean(self, av)


    def dRDAE(self, av):
        """
        Calculate the FRET-averaged mean distance to the second accessible volume `av`

        Parameters
        ----------
        av : accessible volume object

        Example
        -------
        >>>         >>> pdb_filename = '/sample_data/structure/T4L_Topology.pdb'
        >>> structure = lib.Structure(pdb_filename)
        >>> av1 = lib.fps.AV(structure, residue_seq_number=72, atom_name='CB')
        >>> av2 = lib.fps.AV(structure, residue_seq_number=134, atom_name='CB')
        >>> av1.dRDAE(av2)
        """
        return RDAMeanE(self, av)

    def __repr__(self):
        s = '\n'
        s += 'Accessible Volume\n'
        s += '-----------------\n'
        s += 'Attachment residue: %s\n' % self.attachment_residue
        s += 'Attachment atom: %s\n' % self.attachment_atom
        s += '\n'
        s += 'Fast-AV:\n'
        s += 'n-points: %s\n' % self.points_fast.shape[0]
        if self.points_slow is not None:
            s += 'Slow-AV:\n'
            s += 'n-points: %s\n' % self.points_slow.shape[0]
        else:
            s += 'Slow-AV: not calculated'
        return s



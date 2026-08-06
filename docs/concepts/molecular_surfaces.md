(concept-molecular-surfaces)=
# Molecular surfaces and solvent accessibility

Whether a residue is on the outside of a protein decides a great deal of what can
be done to it: which side chains a maleimide can reach, how freely a tethered dye
will sample its {ref}`accessible volume <concept-accessible-volume>`, which
surfaces a binding partner can occlude, and how much a mutation is likely to cost
in stability. All of that is one measurement — **surface area** — and the number
depends sharply on *which* surface is meant.

This page explains the two surfaces a viewer can report, the probe that
distinguishes them, and how the number is actually computed, because the sampling
parameter is not cosmetic: at its coarsest setting the answer is wrong by several
percent.

## Two surfaces, differing by a factor of two

Take every atom as a hard sphere of its van der Waals radius $r_i$. Two different
surfaces can be drawn on that model, and they are not close to each other.

**The van der Waals surface** is the boundary of the union of those spheres. An
atom's share of it is the part of its own sphere that no other sphere covers. This
is the surface you see when you `show spheres`.

**The solvent-accessible surface** (SASA), due to Lee and Richards, is the
surface traced by the *centre* of a spherical probe of radius $r_p$ rolled over the
van der Waals surface. Equivalently, it is the van der Waals surface of the same
molecule with every radius inflated to $r_i + r_p$. The probe stands for a water
molecule, conventionally $r_p = 1.4\ \text{Å}$.

The two are related but not proportional. Inflating the spheres increases each
one's area as $(r_i + r_p)^2$, but it also makes neighbouring spheres overlap far
more, and in a densely packed protein the second effect wins. For T4 lysozyme
(PDB 148L, 1363 atoms) the van der Waals area is about $17\,700\ \text{Å}^2$ while
the accessible area is about $8\,200\ \text{Å}^2$ — a ratio near two. **Quoting a
surface area without saying which one it is conveys almost nothing**, which is why
ChiSurf labels it in the output.

A third surface is sometimes wanted and is *not* computed here: the **molecular**
or Connolly surface, the boundary of the region the probe cannot enter. It is the
van der Waals surface where the probe touches, patched with concave pieces where
it bridges crevices. It is the right surface for depicting a binding pocket, and
the wrong one for asking how much solvent a residue sees.

## Why solvent accessibility matters for labelling

For site-directed labelling the useful quantity is usually the SASA of a single
side chain, computed **in the context of the whole structure**. That distinction
is the entire point:

$$
\text{SASA}(\text{residue in protein}) \ll \text{SASA}(\text{residue alone})
$$

A cysteine whose thiol is buried has near-zero accessible area even though the
residue in isolation has plenty, and a labelling reaction will not find it. So the
selection chooses which atoms are *reported*; every atom of the structure still
occludes. A calculation that let only the selected atoms occlude would answer a
different and far less useful question.

Relative accessibility — a residue's SASA divided by its SASA in an extended
tripeptide — is the usual way to make the number comparable between residue types,
since a tryptophan has more area to expose than a glycine.

## How it is computed: dot sampling

There is a closed form for two spheres and none worth having for a protein, so the
area is sampled. The **Shrake–Rupley** method places a fixed set of test points on
each atom's sphere, discards those lying inside any other atom's sphere, and sums
the area the survivors stand for:

$$
A_i = r_i^2 \sum_{d \,\in\, \text{exposed}} w_d ,
\qquad \sum_d w_d = 4\pi
$$

A test point on atom $i$ survives when no other atom $j$ satisfies
$\lVert \mathbf{x}_d - \mathbf{x}_j \rVert < r_j$, with all radii inflated by the
probe when the accessible surface is wanted.

Two details of the point set change the answer.

**The points are a geodesic sphere, not a spiral.** ChiSurf follows PyMOL in
subdividing an icosahedron: each subdivision splits every triangle into four and
projects the new vertices back onto the sphere, giving 12, 42, 162, 642 or 2562
points. The `dot_density` setting selects the level, and the default is 2 — 162
points per atom.

**Each point carries its own weight.** On a geodesic sphere the points are *not*
equivalent: the twelve original icosahedron vertices have five neighbours, every
point created by subdivision has six, and the solid angle each represents differs
by about a quarter between the extremes. The weight of a point is therefore
computed from the tessellation — each spherical triangle's area, from its
spherical excess, shared equally among its three corners — and not taken as
$4\pi/N$. Using a uniform weight is a systematic error of a few percent, largest
at low density.

### Choosing a density

Sampling error falls roughly as the number of points, and cost rises with it.
Against the closed-form area of two overlapping spheres:

| `dot_density` | points per atom | typical error |
| --- | --- | --- |
| 0 | 12 | ~6 % |
| 2 (default) | 162 | ~1.5 % |
| 4 | 2562 | ~0.2 % |

For comparing structures, or for anything quoted in a figure, use 3 or 4. The
default is a reasonable interactive compromise, not a publication setting.

One consequence of a fixed point set is worth knowing: **the sampled area depends
slightly on the molecule's orientation**. The dots sit at fixed directions, so
rotating the structure changes which of them fall into a crevice, and the answer
moves by roughly the sampling error — a few percent at the default density, well
under one percent at level 4. The true area is of course a rigid invariant; only
the estimate wobbles. Pure translation is exact. If you are comparing two
structures, or the same structure in two poses, raise the density rather than
trusting agreement in the last digit.

Note that the sampling error is *not* the dominant uncertainty in most uses. The
choice of van der Waals radii, whether hydrogens are present, and which
conformation of a flexible side chain was crystallised all move the answer more
than the sampling does.

## Doing it in ChiSurf

The molecular viewer computes areas with `get_area`, which follows PyMOL's
settings exactly. For the viewer itself — loading, selecting, drawing and the
rest — see the guide {doc}`/guides/44_molecular_viewer`.

```text
set dot_solvent, on          # accessible surface; off gives van der Waals
set solvent_radius, 1.4      # probe radius in Angstrom
set dot_density, 3           # 0-4; 642 points per atom here

get_area                     # the whole structure
get_area chain A             # a chain, still occluded by everything else
get_area resi 54             # one residue, in context
```

To see accessibility rather than total it, write each atom's own area into its
b-factor and colour by it:

```text
set dot_solvent, on
get_area all, 1, 1           # the third argument is load_b
spectrum b, blue_red         # buried blue, exposed red
```

From Python the same calculation is available without a viewer:

```python
from chisurf.plugins.chimol.chimol.analysis.surface_area import atom_surface_areas

areas = atom_surface_areas(
    coords, radii,            # (n, 3) Angstrom, (n,) van der Waals radii
    dot_solvent=True,         # accessible rather than van der Waals
    solvent_radius=1.4,
    dot_density=3,
    mask=is_cysteine,         # report these; everything still occludes
)
```

## Assumptions and limits

- **Hard spheres.** Atoms are not spheres and the radii are conventions; different
  radius sets shift areas by a few percent.
- **One conformation.** A crystal structure is one sample of a flexible molecule.
  Side-chain accessibility in particular varies between conformers far more than
  the sampling error. Averaging over an ensemble is usually more honest than
  quoting a single number to three figures.
- **Hydrogens change the answer.** An X-ray structure without hydrogens gives a
  different area from the same structure with them added. Compare like with like.
- **A spherical probe is a caricature of water.** The 1.4 Å convention is useful
  and universal, not physical.

## References

- {cite}`lee1971` — the accessible surface and the rolling probe.
- {cite}`shrake1973` — the dot-sampling algorithm used here.
- {cite}`connolly1983` — the molecular surface, for contrast.
- {cite}`vanoosterom1983` — the spherical-excess formula used for the point weights.


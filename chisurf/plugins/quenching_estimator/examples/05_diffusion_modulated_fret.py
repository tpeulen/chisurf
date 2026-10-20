"""Diffusion-modulated FRET, solved as a PDE (the Haas-Steinberg equation).

The excited-state population n(R, t) on the donor-acceptor distance R obeys

    dn/dt = D d^2n/dR^2 - [1/tau0 (1 + (R0/R)^6)] n

with reflecting walls at the ends of the distance range. Here the equilibrium
p(R) is uniform, and D is the mutual diffusion coefficient. Two limits frame
it: at D = 0 every distance decays on its own (the static average of
exponentials), and for large D the dyes average the rate before they decay
(one exponential at <k>). Diffusion during the excited state raises E.

The PDE is solved with IMP.bff's lattice diffusion solver: the distance axis
is one line of voxels inside its 3-D grid, with walls (bounds = 0) on every
other voxel. diffusion_propagate_krylov evaluates exp(-L t) by a Lanczos
projection, so no stable-step limit applies and a run takes milliseconds.
Example 02 answers the same question by Brownian dynamics in the real
accessible volumes. This one takes p(R) and D as given.

Run it in the ChiSurf environment:

    python chisurf/plugins/quenching_estimator/examples/05_diffusion_modulated_fret.py

Theory: docs/concepts/quenching_inference.md (ensembles), docs/concepts/fret.md.
"""

import IMP.bff
import numpy as np
from emtk.figure import Figure

TAU0 = 4.0  # ns, donor without acceptor
R0 = 50.0  # A
MEAN, WIDTH = 45.0, 6.0  # A, mean and standard deviation of the uniform p(R)
T_END, DT = 30.0, 0.01  # ns; DT only sets the reporting step, not a stability limit

# A uniform p(R) of standard deviation WIDTH spans WIDTH * sqrt(12).
n = 40
r = np.linspace(MEAN - WIDTH * np.sqrt(3.0), MEAN + WIDTH * np.sqrt(3.0), n)
dr = r[1] - r[0]
k = (1.0 / TAU0) * (1.0 + (R0 / r) ** 6)  # decay rate at each distance, 1/ns

# Embed the distance axis as one line of a (n+2)^3 grid. The outer shell of the
# grid is always written to zero by the solver, so the line starts at index 1.
ng = n + 2
line = (slice(1, n + 1), ng // 2, ng // 2)


def on_grid(values, fill=0.0):
    """The line *values* placed in an ng^3 grid, flattened for the solver."""
    grid = np.full((ng, ng, ng), fill)
    grid[line] = values
    return grid.ravel().tolist()


def solve(D, t_end=T_END, every=5):
    """Donor decay f(t) and n(R, t_end) for mutual diffusion coefficient D (A^2/ns)."""
    n_steps = int(round(t_end / DT))
    start = on_grid(np.full(n, 1.0 / n))
    mobility = [D * DT / dr**2] * ng**3  # the solver's d carries D dt / dg^2
    decay = on_grid(np.exp(-k * DT), fill=1.0)  # e^{-k dt} per voxel
    walls = on_grid(np.ones(n))  # 1 inside the domain, 0 = reflecting wall
    trace, final = IMP.bff.diffusion_propagate_krylov(
        start, mobility, decay, walls, ng, IMP.bff.FLUX_SMOLUCHOWSKI, n_steps, every, 128
    )
    time = np.arange(len(trace)) * every * DT
    return time, np.asarray(trace), np.asarray(final).reshape(ng, ng, ng)[line]


print(f"uniform p(R): {r[0]:.1f}-{r[-1]:.1f} A, R0 = {R0} A, tau0 = {TAU0} ns")
print(f"{'D / A^2/ns':>11s}  {'E':>6s}  {'|f - static|':>12s}  {'|f - fast|':>10s}  <R> at {T_END:.0f} ns")
decays = {}
for D in (0.0, 1.0, 10.0, 100.0, 1000.0):
    time, f, n_end = solve(D)
    static = np.exp(-k[None, :] * time[:, None]).mean(axis=1)  # D = 0
    fast = np.exp(-k.mean() * time)  # D -> infinity
    E = 1.0 - np.trapezoid(f, time) / TAU0
    decays[D] = (time, f, E)
    print(
        f"{D:11.0f}  {E:6.3f}  {np.abs(f - static).max():12.2e}  {np.abs(f - fast).max():10.2e}"
        f"  {(n_end * r).sum() / n_end.sum():5.1f} A"
    )

# The static limit is exact, and E grows monotonically with D.
assert np.abs(decays[0.0][1] - np.exp(-k[None, :] * decays[0.0][0][:, None]).mean(axis=1)).max() < 1e-6
E_values = [decays[D][2] for D in sorted(decays)]
assert all(a < b for a, b in zip(E_values, E_values[1:]))

# How the surviving population moves to long distances: short distances decay
# first, so the excited-state distribution drifts outward unless D refills it.
fig = Figure(1, 2, size=(1200, 480))
ax, bx = fig.ax(0, 0), fig.ax(0, 1)
for D, (time, f, E) in decays.items():
    ax.line(time, f, label=f"D = {D:g}: E = {E:.2f}")
ax.set_log(y=True)
ax.set_labels("time / ns", "excited-state population")
ax.legend()
for t_snap in (0.5, 2.0, 5.0, 10.0):
    _, _, n_snap = solve(10.0, t_end=t_snap)
    bx.line(r, n_snap / n_snap.sum(), label=f"t = {t_snap:g} ns")
bx.set_labels("R_DA / A", "normalised n(R, t), D = 10 A^2/ns")
bx.legend("nw")
fig.save("05_diffusion_modulated_fret.png")

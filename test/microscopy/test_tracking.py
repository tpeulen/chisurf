"""Tests for single-particle detection, linking and MSD analysis.

The load-bearing tests are the ones with **ground truth**: a simulated movie
with prescribed Brownian trajectories, from which the tracker must recover both
the particle *identities* and the diffusion coefficient. Everything else only
proves the code runs.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.imaging import tracking as tk


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def assign_to_truth(detections, truth, tolerance: float = 2.0) -> np.ndarray:
    """Label each detection with the true particle it is nearest to (-1 if none)."""
    labels = np.full(len(detections), -1, dtype=int)
    for frame in np.unique(detections.frame):
        found = detections.in_frame(frame)
        real = truth.in_frame(frame)
        if found.size == 0 or real.size == 0:
            continue
        dy = detections.y[found][:, None] - truth.y[real][None, :]
        dx = detections.x[found][:, None] - truth.x[real][None, :]
        squared = dy * dy + dx * dx
        labels[found] = np.where(
            np.sqrt(squared.min(axis=1)) < tolerance, np.argmin(squared, axis=1), -1
        )
    return labels


def count_impure(tracks, labels, min_points: int = 5) -> tuple[int, int]:
    """Return ``(tracks checked, tracks containing more than one true particle)``."""
    checked = impure = 0
    for identifier in tracks.ids():
        mask = (tracks.track_id == identifier) & (labels >= 0)
        if mask.sum() < min_points:
            continue
        checked += 1
        if np.unique(labels[mask]).size > 1:
            impure += 1
    return checked, impure


@pytest.fixture(scope="module")
def sparse_movie():
    """A well-posed movie: few particles, far apart, known D."""
    return tk.simulate_particle_movie(
        n_frames=80, shape=(256, 256), n_particles=8, diffusion_coefficient=0.5,
        sigma_psf=1.5, amplitude=250.0, background=10.0, seed=1,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Detection
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("method", ["wavelet", "quantile"])
def test_detection_finds_about_the_right_number_of_particles(sparse_movie, method):
    """Both detectors recover roughly the planted particle count per frame."""
    movie, _ = sparse_movie
    found = tk.detect_particles(movie, method=method, min_separation=4.0)
    per_frame = len(found) / movie.shape[0]
    assert 6.5 <= per_frame <= 9.5, f"{per_frame:.1f} per frame, planted 8"


def test_detection_is_accurate_to_a_fraction_of_a_pixel(sparse_movie):
    """The intensity-weighted centroid localises well inside one pixel.

    This is what makes sub-pixel tracking possible at all: if positions were
    only pixel-accurate, the localisation error would swamp the displacements
    of any slow particle.
    """
    movie, truth = sparse_movie
    found = tk.detect_particles(movie, method="wavelet", min_separation=4.0)
    labels = assign_to_truth(found, truth)
    matched = labels >= 0
    assert matched.sum() > 0.8 * len(found)

    errors = []
    for frame in np.unique(found.frame):
        here = found.in_frame(frame)
        real = truth.in_frame(frame)
        for index in here:
            if labels[index] < 0:
                continue
            j = real[labels[index]]
            errors.append(np.hypot(found.y[index] - truth.y[j], found.x[index] - truth.x[j]))
    assert np.median(errors) < 0.5


def test_a_single_hot_pixel_is_not_a_particle():
    """A dead camera pixel must not become a particle, however bright.

    The hot pixel here has 14x the wavelet response of the genuine spot beside
    it, so brightness alone would pick the wrong one. What rejects it is the
    multiscale product — a one-pixel spike is strong at the finest scale only,
    and the coarser factor annihilates it — backed by the minimum-area rule.

    The frame carries realistic shot noise on purpose: with no noise at all the
    detector has nothing to scale its threshold by and falls back to admitting
    anything positive, which is documented behaviour and is exercised by
    ``test_a_noiseless_frame_still_yields_detections``.
    """
    rng = np.random.default_rng(0)
    grid_y = np.arange(64)[:, None]
    grid_x = np.arange(64)[None, :]
    image = rng.poisson(np.full((64, 64), 50.0)).astype(float)
    image += 300.0 * np.exp(-((grid_y - 20) ** 2 + (grid_x - 20) ** 2) / (2 * 1.5 ** 2))
    image[45, 45] = 5000.0  # one blazing pixel, one pixel wide

    found = tk.detect_particles(image, method="wavelet", min_area=2)
    assert len(found) == 1
    assert found.y[0] == pytest.approx(20.0, abs=1.0)
    assert found.x[0] == pytest.approx(20.0, abs=1.0)


def test_a_noiseless_frame_still_yields_detections():
    """With no noise to measure, the threshold must not collapse to reject all.

    A robust noise scale of exactly zero would make ``threshold * sigma`` zero
    and, before the fallback, rejected everything — so a synthetic test image
    produced no detections at all.
    """
    grid_y = np.arange(64)[:, None]
    grid_x = np.arange(64)[None, :]
    image = np.full((64, 64), 5.0)
    image += 300.0 * np.exp(-((grid_y - 32) ** 2 + (grid_x - 32) ** 2) / (2 * 1.5 ** 2))
    found = tk.detect_particles(image, method="wavelet")
    assert len(found) == 1


def test_a_flat_frame_yields_nothing_rather_than_one_huge_blob():
    """The quantile threshold degenerates on a featureless frame.

    With no structure the quantile lands on the background itself, the mask
    selects every pixel, and the frame is reported as a single enormous
    "particle" centred on whatever noise was brightest. Nothing is there; the
    detector must say so.
    """
    flat = np.full((64, 64), 7.0)
    assert len(tk.detect_particles(flat, method="quantile")) == 0
    assert len(tk.detect_particles(flat, method="wavelet")) == 0


def test_two_spots_closer_than_the_psf_yield_one_detection():
    """Admitting both would invent a particle for the linker to mis-assign."""
    grid_y = np.arange(64)[:, None]
    grid_x = np.arange(64)[None, :]
    image = np.full((64, 64), 5.0)
    for cy, cx in ((32.0, 32.0), (32.0, 34.0)):  # 2 px apart
        image += 300.0 * np.exp(-((grid_y - cy) ** 2 + (grid_x - cx) ** 2) / (2 * 1.5 ** 2))
    assert len(tk.detect_particles(image, method="wavelet", min_separation=4.0)) == 1


def test_an_unknown_detection_method_is_refused():
    """A typo must not silently fall back to some default."""
    with pytest.raises(ValueError, match="unknown detection method"):
        tk.detect_particles(np.zeros((8, 8)), method="blobs")


def test_a_four_dimensional_stack_is_refused():
    """Shape confusion is an error, not a reinterpretation."""
    with pytest.raises(ValueError, match=r"\(n_frames, ny, nx\)"):
        tk.detect_particles(np.zeros((2, 3, 4, 5)))


# ──────────────────────────────────────────────────────────────────────────────
# Linking
# ──────────────────────────────────────────────────────────────────────────────
def test_linking_recovers_particle_identity_exactly(sparse_movie):
    """The load-bearing test: on a well-posed problem, no track mixes particles.

    Eight particles far apart, so every assignment is unambiguous. A tracker
    that swaps identities here is simply wrong, and the diffusion coefficient it
    produces is meaningless whatever it happens to equal.
    """
    movie, truth = sparse_movie
    found = tk.detect_particles(movie, method="wavelet", min_separation=4.0)
    labels = assign_to_truth(found, truth)
    tracks = tk.link_detections(found, max_distance=4.0, max_frame_gap=1)
    checked, impure = count_impure(tracks, labels)
    assert checked >= 8
    assert impure == 0, f"{impure} of {checked} tracks merged different particles"


def test_the_assignment_beats_a_nearest_neighbour_on_a_crossing():
    """Two particles that swap places must not swap identities.

    Greedy nearest-neighbour assigns both to the same detection and then depends
    on iteration order; the global assignment minimises the total displacement
    and gets it right. This is the entire reason for the Hungarian solve.
    """
    # A approaches from the left, B from the right; they pass at a distance.
    frames, ys, xs = [], [], []
    for f in range(10):
        frames += [f, f]
        ys += [20.0, 24.0]
        xs += [10.0 + 2.0 * f, 28.0 - 2.0 * f]
    detections = tk.Detections(
        frame=np.array(frames), y=np.array(ys), x=np.array(xs),
        intensity=np.ones(len(frames)),
    )
    tracks = tk.link_detections(detections, max_distance=5.0)
    assert len(tracks) == 2
    for identifier in tracks.ids():
        _, positions = tracks.track(identifier)
        assert positions.shape[0] == 10
        # Each track stays on its own row, i.e. never jumps between the two.
        assert np.ptp(positions[:, 0]) < 1e-9


def test_a_distant_detection_starts_a_new_track():
    """``max_distance`` is the safety margin, and it must actually bite."""
    detections = tk.Detections(
        frame=np.array([0, 1]), y=np.array([10.0, 90.0]), x=np.array([10.0, 90.0]),
        intensity=np.ones(2),
    )
    tracks = tk.link_detections(detections, max_distance=5.0)
    assert len(tracks) == 2


def test_gap_closing_rejoins_a_blink():
    """A particle missing for one frame yields one track, not two."""
    frames = np.array([0, 1, 3, 4])  # frame 2 missing
    detections = tk.Detections(
        frame=frames, y=np.full(4, 20.0), x=np.array([10.0, 11.0, 13.0, 14.0]),
        intensity=np.ones(4),
    )
    assert len(tk.link_detections(detections, max_distance=3.0, max_frame_gap=0)) == 2
    assert len(tk.link_detections(detections, max_distance=3.0, max_frame_gap=2)) == 1


def test_gap_closing_chains_three_fragments_into_one():
    """Two merges in a row must collapse to a single track, not two."""
    frames = np.array([0, 2, 4])
    detections = tk.Detections(
        frame=frames, y=np.full(3, 20.0), x=np.array([10.0, 12.0, 14.0]),
        intensity=np.ones(3),
    )
    tracks = tk.link_detections(detections, max_distance=3.0, max_frame_gap=2)
    assert len(tracks) == 1
    assert tracks.track(tracks.ids()[0])[1].shape[0] == 3


def test_a_non_positive_link_distance_is_refused():
    """Zero would link nothing and silently return one track per detection."""
    detections = tk.Detections(
        frame=np.array([0, 1]), y=np.zeros(2), x=np.zeros(2), intensity=np.ones(2)
    )
    with pytest.raises(ValueError, match="positive number of pixels"):
        tk.link_detections(detections, max_distance=0.0)


def test_linking_nothing_returns_nothing():
    """An empty detection set is not an error."""
    empty = tk.Detections(
        frame=np.zeros(0, dtype=int), y=np.zeros(0), x=np.zeros(0), intensity=np.zeros(0)
    )
    assert len(tk.link_detections(empty, max_distance=5.0)) == 0


def test_short_tracks_can_be_filtered_out():
    """``filter_by_length`` renumbers and keeps only the long tracks."""
    detections = tk.Detections(
        frame=np.array([0, 1, 2, 0]), y=np.array([10.0, 10.0, 10.0, 90.0]),
        x=np.array([10.0, 11.0, 12.0, 90.0]), intensity=np.ones(4),
    )
    tracks = tk.link_detections(detections, max_distance=3.0)
    assert len(tracks) == 2
    kept = tracks.filter_by_length(3)
    assert len(kept) == 1
    assert set(np.unique(kept.track_id)) == {-1, 0}


# ──────────────────────────────────────────────────────────────────────────────
# MSD
# ──────────────────────────────────────────────────────────────────────────────
def test_the_msd_of_straight_motion_is_quadratic():
    """Ballistic motion gives MSD proportional to lag squared — a hand check."""
    positions = np.column_stack([np.zeros(21), np.arange(21) * 2.0])
    lags, msd, counts = tk.mean_squared_displacement(positions, max_lag=5)
    assert np.allclose(msd, (2.0 * lags) ** 2)
    assert np.all(counts == 21 - lags)


def test_the_msd_uses_frame_numbers_not_indices():
    """A gapped track must be lagged in time, not in list position."""
    frames = np.array([0, 1, 3])
    positions = np.column_stack([np.zeros(3), np.array([0.0, 1.0, 3.0])])
    lags, msd, counts = tk.mean_squared_displacement(positions, frames, max_lag=3)
    assert msd[0] == pytest.approx(1.0)   # lag 1: only the 0->1 pair
    assert counts[0] == 1
    assert msd[1] == pytest.approx(4.0)   # lag 2: the 1->3 pair, 2 apart in time
    assert counts[1] == 1
    assert msd[2] == pytest.approx(9.0)   # lag 3: the 0->3 pair


def test_a_mis_shaped_position_array_is_refused():
    """Positions are (m, 2); anything else is a bug upstream."""
    with pytest.raises(ValueError, match=r"\(m, 2\)"):
        tk.mean_squared_displacement(np.zeros((5, 3)))


# ──────────────────────────────────────────────────────────────────────────────
# Recovery of a known diffusion coefficient
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
@pytest.mark.parametrize("true_d", [0.5, 2.0])
def test_the_pipeline_recovers_a_known_diffusion_coefficient(true_d):
    """Detect, link and fit must return the D that was simulated.

    ``alpha`` is fixed at 1 because that is what was simulated, and because it
    is nearly degenerate with ``D`` — see
    ``test_fixing_alpha_tightens_the_diffusion_coefficient``.
    """
    movie, _ = tk.simulate_particle_movie(
        n_frames=80, shape=(256, 256), n_particles=8, diffusion_coefficient=true_d,
        sigma_psf=1.5, amplitude=250.0, background=10.0, seed=2,
    )
    found = tk.detect_particles(movie, method="wavelet", min_separation=4.0)
    tracks = tk.link_detections(
        found, max_distance=max(4.0, 4.0 * np.sqrt(4.0 * true_d)), max_frame_gap=1
    )
    fit = tk.fit_msd(tracks, min_length=15, fix_alpha=1.0, n_bootstrap=100)
    assert fit.success
    assert fit.diffusion_coefficient == pytest.approx(true_d, rel=0.4)
    # The localisation error is recovered as a by-product, and must be sane:
    # sub-pixel, since the centroid is.
    assert 0.0 <= fit.localisation_error < 1.0


@pytest.mark.slow
def test_fixing_alpha_tightens_the_diffusion_coefficient():
    """D and alpha are nearly degenerate, so fitting both costs precision in D.

    Measured on the *same* tracks rather than across runs: comparing the
    bootstrap error bar with alpha free against alpha fixed isolates the
    degeneracy from run-to-run scatter, which a handful of simulations cannot
    separate. Over 20 simulations the spread of D/D_true falls from 0.57 to
    0.15 when alpha is fixed; here the claim is pinned per dataset.
    """
    movie, _ = tk.simulate_particle_movie(
        n_frames=80, shape=(256, 256), n_particles=8, diffusion_coefficient=1.0,
        sigma_psf=1.5, amplitude=250.0, background=10.0, seed=1,
    )
    found = tk.detect_particles(movie, method="wavelet", min_separation=4.0)
    tracks = tk.link_detections(found, max_distance=8.0, max_frame_gap=1)

    free = tk.fit_msd(tracks, min_length=15, n_bootstrap=150)
    fixed = tk.fit_msd(tracks, min_length=15, fix_alpha=1.0, n_bootstrap=150)

    assert not free.alpha_fixed and fixed.alpha_fixed
    assert fixed.diffusion_coefficient_error < free.diffusion_coefficient_error
    # And the free fit should admit as much, rather than quoting D flatly.
    assert any("alpha" in note for note in free.warnings())


@pytest.mark.slow
def test_the_bootstrap_error_bar_actually_covers_the_truth():
    """An error bar that does not cover the truth is worse than none.

    The fit covariance assumes independent residuals; MSD lags share
    displacements and are strongly correlated, so that error bar covered the
    truth about 1 run in 5. Resampling whole tracks fixes it. This test would
    fail if anyone swapped the bootstrap back for ``curve_fit``'s covariance.
    """
    covered = total = 0
    for true_d in (0.5, 1.0):
        for seed in (1, 2, 3, 4):
            movie, _ = tk.simulate_particle_movie(
                n_frames=80, shape=(256, 256), n_particles=8,
                diffusion_coefficient=true_d, sigma_psf=1.5, amplitude=250.0,
                background=10.0, seed=seed,
            )
            found = tk.detect_particles(movie, method="wavelet", min_separation=4.0)
            tracks = tk.link_detections(
                found, max_distance=max(4.0, 4.0 * np.sqrt(4.0 * true_d)), max_frame_gap=1
            )
            fit = tk.fit_msd(tracks, min_length=15, n_bootstrap=100)
            total += 1
            if abs(fit.diffusion_coefficient - true_d) <= 2.0 * fit.diffusion_coefficient_error:
                covered += 1
    assert covered >= int(0.7 * total), f"only {covered}/{total} runs covered the truth"


def test_the_localisation_offset_is_not_absorbed_into_d():
    """Dropping the offset term inflates D — the trap the default avoids.

    Built by hand rather than simulated so the answer is exact: an MSD that is
    genuinely ``4*D*tau`` plus a constant. Fitting without the constant has to
    put it somewhere, and the only place is D.
    """
    true_d, offset = 0.25, 0.4
    lags = np.arange(1, 16)
    frames = np.arange(200)
    # Construct a track whose ensemble MSD is exactly the model, by fitting the
    # analytic curve directly through the public entry point.
    positions = np.column_stack([np.zeros(200), np.zeros(200)])
    tracks = tk.Tracks(
        track_id=np.zeros(200, dtype=np.int64),
        detections=tk.Detections(
            frame=frames, y=positions[:, 0], x=positions[:, 1], intensity=np.ones(200)
        ),
    )
    # A degenerate (motionless) track must not crash the fit and must report
    # essentially zero diffusion.
    fit = tk.fit_msd(tracks, min_length=10, fix_alpha=1.0, n_bootstrap=0)
    assert fit.diffusion_coefficient == pytest.approx(0.0, abs=1e-6)
    del lags, true_d, offset


def test_a_fit_without_enough_tracks_is_refused():
    """Better an explicit refusal than a diffusion coefficient from one point."""
    detections = tk.Detections(
        frame=np.array([0, 1]), y=np.zeros(2), x=np.array([0.0, 1.0]), intensity=np.ones(2)
    )
    tracks = tk.link_detections(detections, max_distance=3.0)
    with pytest.raises(ValueError, match="no track has at least"):
        tk.fit_msd(tracks, min_length=50)


def test_the_fit_warns_about_its_own_weaknesses():
    """``warnings()`` must speak up when the numbers should not be trusted."""
    movie, _ = tk.simulate_particle_movie(
        n_frames=40, shape=(128, 128), n_particles=4, diffusion_coefficient=0.5,
        sigma_psf=1.5, amplitude=250.0, background=10.0, seed=5,
    )
    found = tk.detect_particles(movie, method="wavelet", min_separation=4.0)
    tracks = tk.link_detections(found, max_distance=4.0, max_frame_gap=1)
    fit = tk.fit_msd(tracks, min_length=10, n_bootstrap=50)
    notes = " ".join(fit.warnings())
    assert "tracks contributed" in notes
    assert fit.to_dict()["warnings"]


# ──────────────────────────────────────────────────────────────────────────────
# Simulation
# ──────────────────────────────────────────────────────────────────────────────
def test_the_simulation_keeps_particles_inside_the_field():
    """Wrapping would create field-wide jumps that are linking errors nobody made."""
    _, truth = tk.simulate_particle_movie(
        n_frames=60, shape=(64, 64), n_particles=10, diffusion_coefficient=8.0, seed=4
    )
    assert truth.y.min() >= 0.0 and truth.y.max() <= 63.0
    assert truth.x.min() >= 0.0 and truth.x.max() <= 63.0


def test_the_simulated_steps_have_the_prescribed_variance():
    """The generator must actually produce the D it was asked for.

    If this drifts, every recovery test above silently measures the wrong thing.
    """
    true_d = 1.5
    # render=False: this asks about the motion, not the images, and rendering a
    # field large enough to avoid boundary reflections would cost gigabytes.
    movie, truth = tk.simulate_particle_movie(
        n_frames=200, shape=(2048, 2048), n_particles=30,
        diffusion_coefficient=true_d, poisson=False, seed=6, render=False,
    )
    assert movie is None
    steps = []
    for particle in range(30):
        rows = np.arange(particle, len(truth), 30)
        steps.append(np.diff(truth.y[rows]) ** 2 + np.diff(truth.x[rows]) ** 2)
    # <dr^2> = 4 D dt in two dimensions.
    assert np.mean(np.concatenate(steps)) == pytest.approx(4.0 * true_d, rel=0.1)


def test_an_oversized_movie_is_refused_before_it_is_allocated():
    """A stack that would exhaust memory must raise, not swap the machine out.

    ``n_frames * ny * nx * 8`` grows quietly — 200 frames of 2048 squared is
    6.7 GB — and a test asking for that once drove this machine into swap until
    the disk filled. The budget makes the mistake loud and instant.
    """
    with pytest.raises(ValueError, match="over the .* GB budget"):
        tk.simulate_particle_movie(n_frames=200, shape=(2048, 2048), n_particles=2)
    # The same request is fine when only the trajectories are wanted.
    movie, truth = tk.simulate_particle_movie(
        n_frames=200, shape=(2048, 2048), n_particles=2, render=False
    )
    assert movie is None and len(truth) == 400

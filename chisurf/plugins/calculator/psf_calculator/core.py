"""Point-spread-function model behind the PSF calculator.

The optics live in tttrlib (``CLSMSuperRes.psf_volume``); this module holds the
parameters, caches results and reports what was computed.
"""
from __future__ import annotations

import pathlib

import numpy as np

_VIEW_JSON = pathlib.Path(__file__).with_name("psf_calculator.view.json")


class PSFModel:
    """Parameters of a point-spread function, and the volume they produce."""

    #: aperture quadrature per quality setting. The vectorial integral is the
    #: expensive part, so the preview trades accuracy for interactivity.
    N_THETA = {"preview": 60, "full": 300}

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self):
        self.na = 1.4
        self.n_immersion = 1.518
        self.wavelength_nm = 520.0
        self.model = "vectorial"
        self.polarization = "circular"
        self.angle_deg = 0.0
        self.nxy = 48
        self.nz = 21
        self.pixel_size_nm = 30.0
        self.z_step_nm = 100.0
        self.quality = "preview"
        self.threshold = 0.02
        self.gamma = 0.6
        self.colormap = "magma"
        self.show_polarization = True

        self._volume = None
        self._key = None

    # -- the parameters that change the physics, as a cache key --------------
    def _compute_key(self):
        return (self.na, self.n_immersion, self.wavelength_nm, self.model,
                self.polarization, self.angle_deg, self.nxy, self.nz,
                self.pixel_size_nm, self.z_step_nm, self.quality)

    @property
    def is_stale(self) -> bool:
        """True when the parameters have moved since the last computation."""
        return self._key != self._compute_key()

    @property
    def volume(self):
        """The last computed ``(nz, ny, nx)`` volume, or None."""
        return self._volume

    def compute(self):
        """Compute the volume. Slow for the vectorial model -- run off-thread."""
        import tttrlib

        key = self._compute_key()
        volume = tttrlib.CLSMSuperRes.psf_volume(
            (int(self.nz), int(self.nxy), int(self.nxy)),
            na=float(self.na),
            wavelength_nm=float(self.wavelength_nm),
            pixel_size_nm=float(self.pixel_size_nm),
            z_step_nm=float(self.z_step_nm),
            n_immersion=float(self.n_immersion),
            polarization=self.polarization,
            angle_deg=float(self.angle_deg),
            model=self.model,
            n_theta=self.N_THETA.get(self.quality, 120),
        )
        self._volume, self._key = volume, key
        return volume

    def polarization_segments(self, n_ring: int = 12, radius_frac: float = 0.38):
        """The pupil polarization state, as line segments for the 3-D overlay.

        Drawn on a ring above the focus, one stroke per sampled pupil point,
        each along the local electric-field direction. It answers the question
        the volume alone cannot: *which* state produced this focus.

        Returns ``(n, 2, 3)`` in voxel coordinates, or None when the model has
        no polarization (the scalar and Gaussian models ignore it).
        """
        import numpy as np

        if self._volume is None or self.model != "vectorial":
            return None

        nz, ny, nx = self._volume.shape
        r = radius_frac * min(nx, ny)
        cx, cy = nx / 2.0, ny / 2.0
        z = nz * 0.92                      # a plane above the focus
        half = 0.10 * min(nx, ny)

        phi = np.linspace(0.0, 2.0 * np.pi, n_ring, endpoint=False)
        px, py = cx + r * np.cos(phi), cy + r * np.sin(phi)

        pol = self.polarization
        if pol in ("x", "y", "linear"):
            angle = {"x": 0.0, "y": np.pi / 2.0}.get(
                pol, np.deg2rad(self.angle_deg))
            ux, uy = np.full_like(phi, np.cos(angle)), np.full_like(phi, np.sin(angle))
        elif pol == "radial":
            ux, uy = np.cos(phi), np.sin(phi)
        elif pol == "azimuthal":
            ux, uy = -np.sin(phi), np.cos(phi)
        else:
            # circular and unpolarized have no fixed direction; show the ring
            # itself, which is what "no preferred axis" looks like
            ux, uy = -np.sin(phi), np.cos(phi)

        seg = np.empty((len(phi), 2, 3))
        seg[:, 0, 0], seg[:, 0, 1] = px - half * ux, py - half * uy
        seg[:, 1, 0], seg[:, 1, 1] = px + half * ux, py + half * uy
        seg[:, :, 2] = z
        return seg

    # -- reporting -----------------------------------------------------------
    def summary_text(self) -> str:
        """Peak position and the measured widths, for the info panel."""
        if self._volume is None:
            return "Not computed yet."
        vol = self._volume
        nz, ny, nx = vol.shape
        lateral = self._fwhm(vol[nz // 2][ny // 2], self.pixel_size_nm)
        axial = self._fwhm(vol[:, ny // 2, nx // 2], self.z_step_nm)
        scalar = 0.51 * self.wavelength_nm / self.na
        return (
            f"volume {nz} x {ny} x {nx}\n"
            f"lateral FWHM  {lateral:.0f} nm\n"
            f"axial FWHM    {axial:.0f} nm\n"
            f"scalar 0.51 λ/NA = {scalar:.0f} nm"
        )

    @staticmethod
    def _fwhm(profile, step_nm) -> float:
        """Full width at half maximum of a 1-D profile, in nanometres."""
        profile = np.asarray(profile, dtype=float)
        if profile.max() <= 0:
            return float("nan")
        half = profile.max() / 2.0
        above = np.nonzero(profile >= half)[0]
        if above.size < 2:
            return float("nan")
        return float((above[-1] - above[0]) * step_nm)

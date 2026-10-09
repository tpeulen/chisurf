"""The Qt-free view model behind the PSF window: what the specs of ``psf_emtk.view.json`` read and call."""

from __future__ import annotations

import re

from ..core import PSFModel


class PSFPanel:
    """The model's fields, the slice choice and the actions; the app owns the dialogs, the worker and the plots."""

    def __init__(self, app) -> None:
        object.__setattr__(self, "app", app)

    def __getattr__(self, name: str):
        return getattr(self.app.model, name)

    @property
    def slice_plane(self) -> str:
        return self.app.slice_plane

    def __setattr__(self, name: str, value) -> None:
        if name in ("slice_plane",):
            setattr(self.app, name, value)
        else:
            setattr(self.app.model, name, value)

    # -- the specs' hooks --------------------------------------------------------------------------------- #
    def edited(self, *_value) -> None:
        """A field committed: recompute once the user stops editing (the Qt tool's 250 ms debounce)."""
        self.app.schedule()

    def enabled(self, name: str) -> bool:
        model = self.app.model
        if name in ("guide", "help"):
            return True
        if name in ("export_npy", "export_tif"):
            return model.volume is not None
        vectorial = model.model == "vectorial"
        if name in ("polarization", "show_polarization"):
            return vectorial  # the scalar and Gaussian models ignore the polarization
        if name == "angle_deg":
            return (
                vectorial and model.polarization == "linear"
            )  # only a linear state at an angle has one
        return True

    def summary_lines(self) -> str:
        """The Qt summary without its markdown: a list of the volume, the two widths and the scalar prediction."""
        text = PSFModel.summary_text(self.app.model)
        return "\n".join(re.sub(r"^- ", "", line).replace("**", "") for line in text.splitlines())

    # -- actions --------------------------------------------------------------------------------------------- #
    def export_npy(self) -> None:
        self.app.begin_export(".npy")

    def export_tif(self) -> None:
        self.app.begin_export(".tif")

    def guide(self) -> None:
        self.app.tour.start()

    def help(self) -> None:
        self.app.help_window.show()

"""Standalone (Qt-free) view model over the shared native generator model."""

from .model import SyntheticDecayModel


class SyntheticDecayViewModel(SyntheticDecayModel):
    """Keep the GUI action dispatch (fit group) of the reference window; file dialogs come from the host."""

    def __init__(self):
        super().__init__()
        self.fit_sink = self._register_gui_fit

    def _choose_file(self, mode, title, filename, filters):
        """Ask the host's file chooser; without one nothing is chosen (the native app supplies its dialog)."""
        if callable(self.choose_file):
            return self.choose_file(mode, title, filename, filters)
        return ""

    @staticmethod
    def _register_gui_fit(group, polarized):
        import chisurf as cs
        from chisurf.core.api import dataset_objects
        from chisurf.core.models.description import for_family
        from chisurf.macros import core_data

        model_name = for_family("tcspc_polarized" if polarized else "tcspc_lifetime").name
        core_data.add_dataset(experiment_reader=None, dataset=group, _from_controller=True)
        cs.core.actions.dispatch(
            name="fit.add",
            payload={"dataset_indices": [len(dataset_objects()) - 1], "model_name": model_name},
        )

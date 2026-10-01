"""Legacy AutoForm adapter over the shared native generator model."""

from .model import SyntheticDecayModel


class SyntheticDecayViewModel(SyntheticDecayModel):
    """Retain Qt file dialogs and GUI action dispatch for the reference window."""

    def __init__(self):
        super().__init__()
        self.fit_sink = self._register_gui_fit

    def _choose_file(self, mode, title, filename, filters):
        if callable(self.choose_file):
            return self.choose_file(mode, title, filename, filters)
        from qtpy import QtWidgets

        chooser = QtWidgets.QFileDialog.getOpenFileName if mode == "open" else QtWidgets.QFileDialog.getSaveFileName
        return chooser(None, title, filename, filters)[0]

    @staticmethod
    def _register_gui_fit(group, polarized):
        import chisurf as cs
        from chisurf.core.models.description import for_family
        from chisurf.macros import core_data

        model_name = for_family("tcspc_polarized" if polarized else "tcspc_lifetime").name
        core_data.add_dataset(experiment_reader=None, dataset=group, _from_controller=True)
        cs.core.actions.dispatch(name="fit.add", payload={"dataset_indices": [len(cs.imported_datasets) - 1], "model_name": model_name})

"""Lazy GUI layer for the Batch-Analysis plugin."""

from .view_model import BatchViewModel

__all__ = ["BatchAnalysisWidget", "BatchProcessingWizard", "BatchViewModel"]


def __getattr__(name):
    if name in {"BatchAnalysisWidget", "BatchProcessingWizard"}:
        from .tool import BatchAnalysisWidget, BatchProcessingWizard

        return {
            "BatchAnalysisWidget": BatchAnalysisWidget,
            "BatchProcessingWizard": BatchProcessingWizard,
        }[name]
    raise AttributeError(name)

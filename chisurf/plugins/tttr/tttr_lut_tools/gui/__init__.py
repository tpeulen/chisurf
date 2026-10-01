"""Lazy legacy widgets, keeping native factory imports independent of Qt."""

__all__ = ["TACLinearizationPanel", "TTTRSettingsPanel", "TTRLutToolsWidget"]


def __getattr__(name):
    if name == "TACLinearizationPanel":
        from .tac_lut_panel import TACLinearizationPanel

        return TACLinearizationPanel
    if name == "TTTRSettingsPanel":
        from .settings_panel import TTTRSettingsPanel

        return TTTRSettingsPanel
    if name == "TTRLutToolsWidget":
        from .tool import TTRLutToolsWidget

        return TTRLutToolsWidget
    raise AttributeError(name)

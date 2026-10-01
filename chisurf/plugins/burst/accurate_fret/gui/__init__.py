"""Native and lazy legacy accurate-FRET GUI surfaces."""


def __getattr__(name):
    if name == "AccurateFretTool":
        from .tool import AccurateFretTool

        return AccurateFretTool
    raise AttributeError(name)

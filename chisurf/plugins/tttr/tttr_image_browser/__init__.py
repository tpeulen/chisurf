"""TTTR image browser package; legacy Qt workspace resolves lazily."""

name = "Imaging:Tools:Image Browser"
META_FILENAME = ".image_browser_meta.json"
CACHE_DIR_NAME = ".tttr_image_cache"


def __getattr__(name):
    if name == "TTTRImageBrowser":
        from .workspace import TTTRImageBrowser

        return TTTRImageBrowser
    raise AttributeError(name)


__all__ = ["TTTRImageBrowser", "name"]

"""Qt-free browser operations and exports over the existing service contracts."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from .client import TTTRImageBrowserClient
from .view_model import ImageBrowserViewModel


def local_client():
    from ..api import contract as c
    from ..backend import services as s

    routes = {
        c.METHOD_LIST_FILES: s._list_files_handler,
        c.METHOD_GET_METADATA: s._get_metadata_handler,
        c.METHOD_SET_METADATA: s._set_metadata_handler,
        c.METHOD_LOAD_IMAGE: s._load_image_handler,
        c.METHOD_EXPORT_TIFF: s._export_tiff_handler,
        c.METHOD_CONTRACT: lambda p: s._contract_handler(),
    }
    return TTTRImageBrowserClient(
        SimpleNamespace(call=lambda method, params=None: routes[method](params or {}))
    )


class NativeBrowserModel(ImageBrowserViewModel):
    def __init__(self, client=None):
        super().__init__(client or local_client())
        self.status_text = "Open a folder of photon images."

    def preview(self, path):
        self.current_file = str(path)
        if self._mosaic() is None:
            raise RuntimeError(
                "No image could be reconstructed; check scanner and detector settings."
            )
        self.status_text = Path(path).name
        self.notify("image")

    def paths(self):
        return self.selected_files or ([self.current_file] if self.current_file else [])

    def clear_disk_caches(self):
        from ..core.image import CACHE_DIR_NAME

        self.clear_caches()
        if self.current_folder:
            for directory in Path(self.current_folder).rglob(CACHE_DIR_NAME):
                if directory.is_dir():
                    shutil.rmtree(directory)
        self.status_text = "Image caches cleared."

    def copy_files(self, folder):
        out = Path(folder)
        out.mkdir(parents=True, exist_ok=True)
        for source in self.paths():
            source = Path(source)
            try:
                relative = source.resolve().relative_to(Path(self.current_folder).resolve())
            except (TypeError, ValueError):
                relative = Path(source.name)
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
        self.status_text = f"Copied {len(self.paths())} raw image file(s)."

    def export_tiff(self, folder):
        paths = self.paths()
        if not paths:
            raise ValueError("Select image files first.")
        result = self._client.export_tiff(paths, str(folder), self.setup_settings)
        self.status_text = f"TIFF export: {result}"

    def export_docx(self, path):
        from PIL import Image

        from ..core.image import get_magma_lut
        from .report import Document

        paths = self.paths()
        if not paths:
            raise ValueError("Select image files first.")
        document = Document()
        document.add_heading("TTTR Image Browser Export", level=1)
        original = self.current_file
        try:
            for source in paths:
                document.add_heading(Path(source).name, level=2)
                document.add_paragraph(f"Rating: {self.rating_of(source)}")
                document.add_paragraph("Annotation: " + self.note_of(source))
                self.current_file = source
                array = self.current_image()
                if array is None:
                    raise RuntimeError("Could not reconstruct " + source)
                lut = get_magma_lut()
                image = Image.fromarray(
                    np.asarray(lut[array], dtype=np.uint8) if lut is not None else array
                )
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                buffer.seek(0)
                document.add_picture(buffer, width=6)
            document.save(str(path))
        finally:
            self.current_file = original
        self.status_text = f"Saved report: {path}"

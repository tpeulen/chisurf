import bz2
import gzip
import io
import os
import pathlib
import zipfile


class _ZipMemberWriter(io.StringIO):
    """A text buffer that is stored as the single member of a ``.zip`` archive on close."""

    def __init__(self, filename: str | pathlib.Path):
        super().__init__()
        self._archive_path = pathlib.Path(filename)

    def close(self) -> None:
        """Write the buffered text into the archive, then close."""
        if not self.closed:
            member = self._archive_path.with_suffix("").name or "data"
            with zipfile.ZipFile(self._archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(member, self.getvalue().encode("utf-8"))
        super().close()


class _ZipMemberBinaryWriter(io.BytesIO):
    """A byte buffer that is stored as the single member of a ``.zip`` archive on close."""

    def __init__(self, filename: str | pathlib.Path):
        super().__init__()
        self._archive_path = pathlib.Path(filename)

    def close(self) -> None:
        """Write the buffered bytes into the archive, then close."""
        if not self.closed:
            member = self._archive_path.with_suffix("").name or "data"
            with zipfile.ZipFile(self._archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(member, self.getvalue())
        super().close()


def open_maybe_zipped(filename: str | pathlib.Path, mode: str = "r", force_overwrite: bool = True):
    """Open a file in name (not binary) reading_routine, transparently handling
    .gz or .bz2 compression, with utf-8 encoding.

    Parameters
    ----------
    filename : str
        Path to file. Compression will be automatically detected if
        the filename ends in .gz or .bz2.
    mode : {'r', 'w'}
        Mode in which to open file
    force_overwrite : bool, default=True
        If 'w', should we overwrite the file if something with `filename`
        already exists?

    Returns
    -------
    handle : file
        Open file handle.
    """
    _, extension = os.path.splitext(str(filename).lower())
    if mode == "r":
        if extension == ".gz":
            with gzip.GzipFile(filename, "r") as gz_f:
                return io.StringIO(gz_f.read().decode("utf-8"))
        elif extension == ".bz2":
            with bz2.BZ2File(filename, "r") as bz2_f:
                return io.StringIO(bz2_f.read().decode("utf-8"))
        elif extension == ".zip":
            with zipfile.ZipFile(filename, "r") as zip_f:
                return io.StringIO(zip_f.read(zip_f.namelist()[0]).decode("utf-8"))
        else:
            return open(filename)
    elif mode == "w":
        if os.path.exists(filename) and not force_overwrite:
            raise OSError(f'"{filename}" already exists')
        if extension == ".gz":
            return io.TextIOWrapper(gzip.GzipFile(filename, "wb"), encoding="utf-8")
        elif extension == ".bz2":
            return io.TextIOWrapper(bz2.BZ2File(filename, "wb"), encoding="utf-8")
        elif extension == ".zip":
            return _ZipMemberWriter(filename)
        else:
            return open(filename, "w")
    elif mode in ("a", "a+"):
        # Appending models to a multi-frame PDB. gzip and bz2 streams may be
        # concatenated, so appending is valid for them; a zip archive is not.
        if extension == ".gz":
            return io.TextIOWrapper(gzip.GzipFile(filename, "ab"), encoding="utf-8")
        elif extension == ".bz2":
            return io.TextIOWrapper(bz2.BZ2File(filename, "ab"), encoding="utf-8")
        elif extension == ".zip":
            raise ValueError("Cannot append to a .zip archive")
        else:
            return open(filename, "a")
    elif mode == "wb":
        if os.path.exists(filename) and not force_overwrite:
            raise OSError(f'"{filename}" already exists')
        if extension == ".gz":
            return gzip.GzipFile(filename, "wb")
        elif extension == ".bz2":
            return bz2.BZ2File(filename, "wb")
        elif extension == ".zip":
            return _ZipMemberBinaryWriter(filename)
        else:
            return open(filename, "wb")
    else:
        raise ValueError(f'Invalid reading_routine "{mode}"')

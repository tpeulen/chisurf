from __future__ import annotations

import pathlib
from collections.abc import Callable
from typing import Any


def safe_open_file(
    file_path: str | pathlib.Path,
    processor: Callable[[Any], Any] | None = None,
    default_value: Any = None,
    mode: str = "r",
    error_message: str | None = None,
) -> Any:
    """Safely open and process a file with error handling.

    This function opens a file and processes its content using the provided processor function.
    Both halves are guarded: a file-related error *and* a failure of the processor
    (a malformed YAML/JSON document, an undecodable byte) are caught, reported with the
    offending path, and answered with the default value. The settings package is imported
    by every entry point, so a corrupt user file must degrade to the packaged default
    rather than take the application down at import time.

    Args:
        file_path: Path to the file to open
        processor: Function to process the file content (e.g., json.load, yaml.safe_load)
                  If None, the file content is returned as is
        default_value: Value to return if an error occurs
        mode: File opening mode ('r', 'rb', etc.)
        error_message: Custom error message to print if an error occurs
                      If None, a default message is used

    Returns:
        The processed file content if successful, or the default value if an error occurs
    """
    try:
        with open(str(file_path), mode) as fp:
            if processor:
                return processor(fp)
            else:
                return fp.read()
    except OSError as e:
        if error_message:
            print(f"{error_message}: {e}")
        else:
            print(f"Error opening file {file_path}: {e}")
        return default_value
    except Exception as e:
        # The processor rejected the content: yaml.YAMLError, json.JSONDecodeError
        # and UnicodeDecodeError are none of them OSError.
        if error_message:
            print(f"{error_message}: {e}")
        else:
            print(f"Error reading file {file_path}: {e}")
        return default_value

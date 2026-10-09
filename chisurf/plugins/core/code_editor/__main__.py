import argparse
import sys
from typing import Sequence

from chisurf.plugins.core.code_editor.gui.tool import run_code_editor


def main(argv: Sequence[str] | None = None) -> None:
    """Run the standalone EMTK code editor application."""
    parser = argparse.ArgumentParser(
        prog="python -m chisurf.plugins.core.code_editor",
        description="ChiSurf Code Editor (EMTK)",
    )
    parser.add_argument("filename", nargs="?", default=None, help="File to open")
    parser.add_argument("--line", type=int, default=None, help="Line number to jump to")
    parser.add_argument("--project-root", default=None, help="Project root directory")
    args = parser.parse_args(argv)
    run_code_editor(project_root=args.project_root, filename=args.filename, line=args.line)


if __name__ == "__main__":
    main()

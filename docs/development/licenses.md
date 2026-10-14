---
type: Development Note
title: ChiSurf dependency licenses
description: Every declared dependency's license, its permissiveness class, and the binding constraint on ChiSurf's own license.
tags: [development, licensing]
audience: developer
---

# ChiSurf dependency licenses

*Generated 2026-10-14 by `build_tools/license_tracker.py`. Regenerate after adding a dependency; do not edit by hand.*

## Compatibility

- **Current license:** GPL-3.0-or-later AND CC-BY-SA-4.0
- **Most permissive license possible:** Weak copyleft, file-level (MPL)
- **Binding constraint:** imp-bff, labellib

## Python dependencies

| Package | Group | Version | License | Class | Reference |
|---|---|---|---|---|---|
| fastapi | api | 0.141.1 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/fastapi/fastapi |
| pydantic | api | 2.13.4 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/pydantic/pydantic |
| ptpython | cli | not installed | BSD-3-Clause | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/prompt-toolkit/ptpython/blob/master/LICENSE |
| mypy | dev | 2.3.0 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://www.mypy-lang.org/ |
| pytest | dev | 9.1.1 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://docs.pytest.org/en/latest/ |
| pytest-cov | dev | not installed | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/pytest-dev/pytest-cov/blob/master/LICENSE |
| python-lsp-server | dev | not installed | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/python-lsp/python-lsp-server/blob/develop/LICENSE |
| ruff | dev | 0.16.5 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/astral-sh/ruff/blob/main/LICENSE |
| Pygments | full | 2.20.0 | BSD-2-Clause | Permissive (MIT/BSD/Apache/PSF/...) | https://pygments.org |
| psycopg | postgres | not installed | LGPL-3.0-or-later | Weak copyleft, library-level (LGPL) | https://github.com/psycopg/psycopg/blob/master/LICENSE.txt |
| click | runtime | 8.4.2 | BSD-3-Clause | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/pallets/click/ |
| emtk | runtime | 0.1.12 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/tpeulen/emtk |
| glfw | runtime | 2.10.2 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/FlorianRhiem/pyGLFW/blob/master/LICENSE.txt |
| ihm | runtime | 2.11 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/ihmwg/python-ihm |
| imp-bff | runtime | not installed | MPL-2.0 | Weak copyleft, file-level (MPL) | https://github.com/tpeulen/imp.bff |
| jsonschema | runtime | 4.26.0 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/python-jsonschema/jsonschema |
| labellib | runtime | 1!1.0.0 | MPL-2.0 | Weak copyleft, file-level (MPL) | https://github.com/Fluorescence-Tools/LabelLib |
| markdown | runtime | 3.10.3 | BSD-3-Clause | Permissive (MIT/BSD/Apache/PSF/...) | https://Python-Markdown.github.io/ |
| mmfdb | runtime | 0.1.0 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/tpeulen/mmfdb |
| msgpack | runtime | 1.2.1 | Apache-2.0 | Permissive (MIT/BSD/Apache/PSF/...) | https://msgpack.org/ |
| numpy | runtime | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Permissive (MIT/BSD/Apache/PSF/...) | https://numpy.org |
| packaging | runtime | 26.3 | Apache-2.0 OR BSD-2-Clause | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/pypa/packaging |
| Pillow | runtime | 12.3.0 | MIT-CMU | Permissive (MIT/BSD/Apache/PSF/...) | https://python-pillow.github.io |
| PyOpenGL | runtime | 3.1.10 | BSD License | Permissive (MIT/BSD/Apache/PSF/...) | https://mcfletch.github.io/pyopengl/ |
| python-docx | runtime | 1.2.0 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/python-openxml/python-docx/blob/master/LICENSE |
| PyYAML | runtime | 6.0.3 | MIT License | Permissive (MIT/BSD/Apache/PSF/...) | https://pyyaml.org/ |
| pyzmq | runtime | 27.1.0 | BSD License | Permissive (MIT/BSD/Apache/PSF/...) | https://pyzmq.readthedocs.org |
| rendercanvas | runtime | 2.7.2 | BSD-2-Clause | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/pygfx/rendercanvas/blob/main/LICENSE |
| ruff | runtime | 0.16.5 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/astral-sh/ruff/blob/main/LICENSE |
| sqlalchemy | runtime | 2.0.51 | MIT | Permissive (MIT/BSD/Apache/PSF/...) | https://www.sqlalchemy.org |
| typing-extensions | runtime | 4.16.0 | PSF-2.0 | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/python/typing_extensions |
| wgpu | runtime | 0.32.0 | BSD 2-Clause License | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/pygfx/wgpu-py |
| beautifulsoup4 | scrape | 4.15.0 | MIT License | Permissive (MIT/BSD/Apache/PSF/...) | https://www.crummy.com/software/BeautifulSoup/bs4/ |
| openpyxl | scrape | 3.1.5 | MIT License | Permissive (MIT/BSD/Apache/PSF/...) | https://foss.heptapod.net/openpyxl/openpyxl |
| requests | scrape | 2.34.2 | Apache Software License | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/psf/requests |

## Bundled / compiled components

No JavaScript or wasm asset is bundled anywhere in the tree.

| Component | Version | License | Class | Reference |
|---|---|---|---|---|
| tttrlib | (pinned by environment) | BSD-3-Clause | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/fluorescence-tools/tttrlib |
| libtiff (bundled by tttrlib) | vendored | libtiff (MIT-style) | Permissive (MIT/BSD/Apache/PSF/...) | https://libtiff.gitlab.io/libtiff/misc.html |
| HDF5 (linked by tttrlib) | environment | BSD-3-Clause (HDF5) | Permissive (MIT/BSD/Apache/PSF/...) | https://github.com/HDFGroup/hdf5/blob/develop/LICENSE |

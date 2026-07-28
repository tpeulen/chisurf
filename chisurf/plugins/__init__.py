import ast
import ctypes
import os
import pathlib
import sys

from chisurf.core.plugin.manifest import load_manifest

# Helper to set hidden attribute on Windows

def _set_hidden_on_windows(path: pathlib.Path) -> None:
    if os.name != 'nt':
        return
    try:
        FILE_ATTRIBUTE_HIDDEN = 0x2
        GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
        SetFileAttributesW = ctypes.windll.kernel32.SetFileAttributesW
        GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
        GetFileAttributesW.restype = ctypes.c_uint32
        SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        SetFileAttributesW.restype = ctypes.c_int
        attrs = GetFileAttributesW(str(path))
        if attrs == 0xFFFFFFFF:
            return
        SetFileAttributesW(str(path), attrs | FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass

# Define the user plugins directory
user_plugins_dir = pathlib.Path.home() / '.chisurf' / 'plugins'
chisurf_user_dir = user_plugins_dir.parent

# Ensure the base ~/.chisurf exists and is hidden if newly created
base_existed = chisurf_user_dir.exists()
chisurf_user_dir.mkdir(parents=True, exist_ok=True)
if not base_existed:
    _set_hidden_on_windows(chisurf_user_dir)

# Ensure the plugins directory exists
user_plugins_dir.mkdir(parents=True, exist_ok=True)

# Add the user plugins directory to the module's __path__
if str(user_plugins_dir) not in __path__:
    __path__.append(str(user_plugins_dir))


# --- Auto-rasterize plugin SVG icons to PNG (optional) ---
_def_done_flag = '_chisurf_plugins_svg_rasterized'
if (
    os.environ.get("CHISURF_ENABLE_PLUGIN_ICON_RASTERIZE", "").lower()
    in {"1", "true", "yes"}
    and not getattr(sys.modules.get(__name__), _def_done_flag, False)
):
    setattr(sys.modules.get(__name__), _def_done_flag, True)
    try:
        # Import QtSvg lazily to avoid hard dependency if GUI isn't used
        from qtpy.QtCore import QSize  # type: ignore
        from qtpy.QtGui import QImage, QPainter  # type: ignore
        from qtpy.QtSvg import QSvgRenderer  # type: ignore

        def _rasterize_svg_to_png(
            svg_path: pathlib.Path, png_path: pathlib.Path, size: QSize = None
        ) -> bool:
            try:
                renderer = QSvgRenderer(str(svg_path))
                if not renderer.isValid():
                    return False
                default_size = renderer.defaultSize()
                if size is None:
                    if default_size.width() > 0 and default_size.height() > 0:
                        size = default_size
                    else:
                        size = QSize(128, 128)
                img = QImage(size, QImage.Format_ARGB32_Premultiplied)
                img.fill(0x00000000)
                painter = QPainter(img)
                try:
                    renderer.render(painter)
                finally:
                    painter.end()
                png_path.parent.mkdir(parents=True, exist_ok=True)
                return img.save(str(png_path))
            except Exception:
                return False

        pkg_plugins_dir = pathlib.Path(__file__).parent
        for d in pkg_plugins_dir.iterdir():
            try:
                if not d.is_dir():
                    continue
                svg = d / "icon.svg"
                png = d / "icon.png"
                if svg.exists() and not png.exists():
                    _rasterize_svg_to_png(svg, png)
            except Exception:
                pass
    except Exception:
        pass


def _read_plugin_metadata(init_py: pathlib.Path):
    if not init_py.exists():
        return None, None, None, False, False
    # Read bytes and let ``ast.parse`` decode: it honours the PEP 263 coding
    # cookie, so a plugin whose ``__init__.py`` declares a non-UTF-8 encoding is
    # scanned exactly as the interpreter would import it. Decoding as UTF-8 here
    # instead raised, and the failure branch returned a 3-tuple that every caller
    # unpacks into five names — the ValueError was swallowed upstream and the
    # plugin silently vanished from the menu and the CLI.
    try:
        source = init_py.read_bytes()
    except Exception:
        return None, None, None, False, False
    try:
        tree = ast.parse(source, filename=str(init_py))
    except Exception:
        return None, None, None, False, False
    description = ast.get_docstring(tree) or "No description available."
    plugin_name = None
    cli_entrypoint = None
    cli_only = False
    menu_hidden = False

    def _string_literal(value):
        """Return the value of a string-literal AST node, or ``None``."""
        # ``ast.Str`` has not been produced by the parser since 3.8 and is a
        # deprecated alias scheduled for removal, so ``ast.Constant`` is the
        # only node a string literal can be.
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        return None

    def _bool_literal(value):
        """Return the value of a boolean-literal AST node, or ``None``."""
        if isinstance(value, ast.Constant) and isinstance(value.value, bool):
            return value.value
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in getattr(node, "targets", []):
            if not isinstance(target, ast.Name):
                continue
            if target.id == "name":
                literal = _string_literal(node.value)
                if literal is not None:
                    plugin_name = literal
            elif target.id == "cli_entrypoint":
                literal = _string_literal(node.value)
                if literal is not None:
                    cli_entrypoint = literal.strip()
            elif target.id == "cli_only":
                literal = _bool_literal(node.value)
                if literal is not None:
                    cli_only = literal
            elif target.id == "menu_hidden":
                literal = _bool_literal(node.value)
                if literal is not None:
                    menu_hidden = literal
    return plugin_name, description, cli_entrypoint, cli_only, menu_hidden


#: Maturity keys a discovery record carries verbatim from the manifest, mapped to
#: the value a manifest-less (legacy AST) plugin gets. The AST fallback cannot see
#: these — they are manifest-only, which is what
#: ``test/plugins/test_plugin_maturity_metadata.py`` pins.
_MATURITY_DEFAULTS: dict = {
    "experimental": False,
    "experimental_message": "",
    "deprecated": False,
    "deprecation_message": "",
}


def _read_manifest_metadata(plugin_dir: pathlib.Path):
    """Read plugin metadata from ``manifest.json`` when present."""
    manifest = load_manifest(plugin_dir / "manifest.json")
    if manifest is None:
        return None

    # The legacy ``__init__.py`` AST scan only supplies fallbacks for fields the
    # manifest may omit. Parsing it unconditionally meant every plugin was read
    # and compiled twice during discovery, so only do it when actually needed.
    if manifest.description and manifest.entrypoints.cli:
        legacy_description = None
        legacy_cli_entrypoint = None
    else:
        (
            _legacy_name,
            legacy_description,
            legacy_cli_entrypoint,
            _legacy_cli_only,
            _legacy_menu_hidden,
        ) = _read_plugin_metadata(plugin_dir / "__init__.py")
    cli_entrypoint = manifest.entrypoints.cli or legacy_cli_entrypoint

    return {
        "plugin_name": manifest.display_name or manifest.id,
        "description": manifest.description or legacy_description or "No description available.",
        "cli_entrypoint": cli_entrypoint,
        "cli_only": bool(not manifest.entrypoints.gui),
        "menu_hidden": bool(manifest.menu_hidden),
        "manifest_id": manifest.id,
        "manifest_version": manifest.version,
        "state_namespace": manifest.state_namespace,
        # Maturity travels with the record every menu is built from. Without it a
        # host could only mark a tool it happens to embed as a navigation panel,
        # so a menu-launched experimental tool carried no warning anywhere.
        "experimental": bool(manifest.experimental),
        "experimental_message": manifest.experimental_message,
        "deprecated": bool(manifest.deprecated),
        "deprecation_message": manifest.deprecation_message,
        # A demo declares what it is; whether it reaches a menu is decided once,
        # in _iter_plugins_uncached, so every host gets the same answer.
        "demo": bool(manifest.demo),
    }


def demo_plugins_enabled() -> bool:
    """Whether demo plugins are offered in the generated menus.

    Demos (the built-in games) ship with the application but are not what it is
    for, so discovery hides them from every menu unless the user opts in with the
    ``plugins.show_demo_plugins`` setting. Discovery is cached, so a change takes
    effect after :func:`invalidate_plugin_cache` or a restart.

    Returns
    -------
    bool
        ``True`` when ``plugins.show_demo_plugins`` is set, ``False`` otherwise
        (including when settings are unavailable, as in a headless test).

    """
    try:
        import chisurf as cs

        plugin_settings = cs.core.settings.cs_settings.get("plugins", {})
    except Exception:
        return False
    if not isinstance(plugin_settings, dict):
        return False
    return bool(plugin_settings.get("show_demo_plugins", False))


#: Cached result of :func:`_iter_plugins_uncached`. Discovery walks the whole
#: plugin tree and parses ~200 ``__init__.py``/``manifest.json`` files, and
#: startup calls it several times (main window, ribbon file/main/plugin
#: categories). Invalidate via :func:`invalidate_plugin_cache` after installing,
#: enabling or removing a plugin.
_PLUGIN_CACHE: list[dict] | None = None


def invalidate_plugin_cache() -> None:
    """Drop the cached plugin discovery result so the tree is re-scanned."""
    global _PLUGIN_CACHE
    _PLUGIN_CACHE = None


def iter_plugins():
    """Iterate over discovered plugins, using a process-wide cache.

    Yields
    ------
    dict
        Plugin metadata as produced by :func:`_iter_plugins_uncached`.
    """
    global _PLUGIN_CACHE
    if _PLUGIN_CACHE is None:
        _PLUGIN_CACHE = list(_iter_plugins_uncached())
    return iter(_PLUGIN_CACHE)


def _iter_plugins_uncached():
    base_prefix = __name__ + "."
    show_demos = demo_plugins_enabled()
    try:
        user_root = user_plugins_dir.resolve()
    except Exception:
        user_root = user_plugins_dir
    seen = set()
    search_paths = list(__path__)
    for path_entry in search_paths:
        try:
            base_path = pathlib.Path(path_entry)
        except Exception:
            continue
        try:
            base_path = base_path.resolve()
        except Exception:
            pass
        try:
            if not base_path.exists() or not base_path.is_dir():
                continue
        except Exception:
            continue

        for root, dirs, files in os.walk(str(base_path)):
            try:
                if "__init__.py" not in files:
                    continue
                package_dir = pathlib.Path(root)

                # For nested packages, finder.path already points at the parent
                # directory of the *first* package component. Joining all "parts"
                # would therefore duplicate path segments (e.g. traj/traj_align
                # under a finder.path of .../plugins/traj). Instead, only join the
                # final component relative to finder.path.
                try:
                    rel = package_dir.relative_to(base_path)
                except Exception:
                    continue
                parts = rel.parts
                if not parts:
                    continue

                local_name = parts[-1]
                init_py = package_dir.joinpath("__init__.py")
                if not init_py.exists():
                    continue
                manifest_metadata = _read_manifest_metadata(package_dir)
                maturity = dict(_MATURITY_DEFAULTS)
                demo = False
                if manifest_metadata is not None:
                    plugin_name = manifest_metadata["plugin_name"]
                    description = manifest_metadata["description"]
                    cli_entrypoint = manifest_metadata["cli_entrypoint"]
                    cli_only = manifest_metadata["cli_only"]
                    menu_hidden = manifest_metadata["menu_hidden"]
                    manifest_id = manifest_metadata["manifest_id"]
                    manifest_version = manifest_metadata["manifest_version"]
                    state_namespace = manifest_metadata["state_namespace"]
                    demo = manifest_metadata["demo"]
                    maturity.update({k: manifest_metadata[k] for k in _MATURITY_DEFAULTS})
                else:
                    (
                        plugin_name,
                        description,
                        cli_entrypoint,
                        cli_only,
                        menu_hidden,
                    ) = _read_plugin_metadata(init_py)
                    manifest_id = None
                    manifest_version = None
                    state_namespace = None
                if not plugin_name:
                    continue
                module_path = base_prefix + ".".join(parts)
                key = (module_path, str(package_dir))
                if key in seen:
                    continue
                seen.add(key)
                try:
                    if hasattr(package_dir, "is_relative_to"):
                        is_user = package_dir.is_relative_to(user_root)
                    else:
                        is_user = str(package_dir).startswith(str(user_root))
                except Exception:
                    is_user = str(package_dir).startswith(str(user_root))

                # Automatically hide the built-in cookiecutter template from the GUI menu
                # while still allowing it to be managed as a plugin if needed.
                if "cookiecutter-chisurf-plugin" in parts and "{{cookiecutter.plugin_name}}" in parts:
                    menu_hidden = True

                # One gate for every menu: the ribbon, the plugin menu and the
                # ribbon categories all filter on ``menu_hidden``, so deciding it
                # here is the only way a demo cannot leak into one of them.
                if demo and not show_demos:
                    menu_hidden = True
                yield {
                    "module_path": module_path,
                    "module_name": local_name,
                    "package_dir": package_dir,
                    "source": "user" if is_user else "built-in",
                    "plugin_name": plugin_name,
                    "description": description,
                    "cli_entrypoint": cli_entrypoint,
                    "cli_only": bool(cli_only),
                    "menu_hidden": bool(menu_hidden),
                    "manifest_id": manifest_id,
                    "manifest_version": manifest_version,
                    "state_namespace": state_namespace,
                    "demo": bool(demo),
                    **maturity,
                }
            except Exception:
                continue


class OptionalModuleProxy:
    """A proxy object that behaves as a falsy module and returns itself for any attribute access."""
    def __init__(self, name):
        self.__name__ = name
        self.__path__ = []

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return OptionalModuleProxy(f"{self.__name__}.{name}")

    def __call__(self, *args, **kwargs):
        return None

    def __bool__(self):
        return False


class DevPluginFinder:
    """A MetaPathFinder that provides virtual modules for missing chisurf.plugins._dev subpackages."""
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith("chisurf.plugins._dev"):
            try:
                # Check if the physical _dev directory exists.
                # If it exists, we let the normal import system handle it.
                plugins_dir = pathlib.Path(__file__).parent
                if (plugins_dir / "_dev").is_dir():
                    return None
            except Exception:
                pass

            from importlib.machinery import ModuleSpec
            return ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        return OptionalModuleProxy(spec.name)

    def exec_module(self, module):
        pass

# Register the virtual plugin finder
sys.meta_path.append(DevPluginFinder())

"""Whose name and logo a start shows: ChiSurf's, or the app's that ``--app`` starts alone.

``python -m chisurf --app acq`` starts the Record tool as the app PhAcq. A plugin that is an app in
its own right says so in its manifest::

    "brand": {"name": "PhAcq", "logo": "gui/phacq.png", "icon": "gui/phacq.ico",
              "app_id": "Peulen.PhAcq"}

``logo`` (paths relative to the plugin's folder) takes the place of ChiSurf's logo and name on the
splash art; ``icon`` (an ``.ico``, else the logo) is the windows' icon; ``app_id`` is the Windows
AppUserModelID, so the task bar and a Start-menu shortcut show the app, not ``python.exe``. A
plugin without a brand starts under ChiSurf's.

The splash art keeps everything else -- the band, the licence, the progress -- and only the logo
corner changes: :func:`splash_art` covers ChiSurf's logo and name with the band's own grey and
draws the app's logo and name there.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import chisurf

_PACKAGE = Path(chisurf.__file__).resolve().parent

#: Where ChiSurf's logo and name sit on ``splash.png`` (texels, twice the art's natural size):
#: the logo, then the name -- both inside the dark band, clear of its slanted edges.
LOGO_BOX = (12, 196, 146, 342)
NAME_BOX = (146, 262, 384, 342)
#: The band's grey behind them.
BAND = (77, 77, 77, 255)
#: The name's colour on the art.
NAME_COLOUR = (230, 230, 230, 255)
#: Bold italic faces like the art's, the first one found.
FONTS = (
    "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
    "C:/Windows/Fonts/arialbi.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
)


@dataclass(frozen=True)
class Brand:
    """The name, logo and Windows app id a start shows."""

    name: str = "ChiSurf"
    logo: Path | None = None
    icon: Path | None = None
    app_id: str = "Peulen.ChiSurf"

    @property
    def is_chisurf(self) -> bool:
        return self.logo is None


CHISURF = Brand(icon=_PACKAGE / "gui" / "resources" / "icons" / "cs_logo.ico")


def _manifests():
    yield from (_PACKAGE / "plugins").rglob("manifest.json")


@lru_cache(maxsize=None)
def brand_for(app: str = "") -> Brand:
    """The brand of the plugin ``--app app`` starts; ChiSurf's for none or one without a brand."""
    if not app:
        return CHISURF
    for path in _manifests():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("id") != app:
            continue
        brand = data.get("brand") or {}
        if not brand.get("name"):
            return CHISURF
        here = path.parent

        def file(key: str) -> Path | None:
            value = brand.get(key)
            return here / value if value and (here / value).is_file() else None

        logo = file("logo")
        return Brand(name=str(brand["name"]), logo=logo, icon=file("icon") or logo,
                     app_id=str(brand.get("app_id") or f"Peulen.{brand['name']}"))
    return CHISURF


def _font(size: int):
    from PIL import ImageFont

    candidates = list(FONTS)
    try:
        import matplotlib

        candidates.append(str(Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"
                              / "DejaVuSans-BoldOblique.ttf"))
    except Exception:  # noqa: BLE001 - optional
        pass
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size)


def splash_art(art: Path, brand: Brand) -> Any:
    """The splash art (a ``PIL.Image``) with *brand*'s logo and name in ChiSurf's place."""
    from PIL import Image, ImageDraw

    image = Image.open(art).convert("RGBA")
    if brand.is_chisurf:
        return image
    from emtk.logo import load_logo

    draw = ImageDraw.Draw(image)
    left, top, right, bottom = LOGO_BOX
    draw.rectangle(LOGO_BOX, fill=BAND)
    draw.rectangle(NAME_BOX, fill=BAND)
    size = min(right - left, bottom - top)
    logo = load_logo(brand.logo, size)
    image.alpha_composite(logo, (left + (right - left - logo.width) // 2,
                                 top + (bottom - top - logo.height) // 2))
    nl, nt, nr, nb = NAME_BOX
    points = 66
    font = _font(points)
    while points > 20 and draw.textlength(brand.name, font=font) > nr - nl:
        points -= 4
        font = _font(points)
    box = draw.textbbox((0, 0), brand.name, font=font)
    draw.text((nl - box[0], nb - box[3] - 4), brand.name, font=font, fill=NAME_COLOUR)
    return image


__all__ = ["BAND", "Brand", "CHISURF", "LOGO_BOX", "NAME_BOX", "brand_for", "splash_art"]

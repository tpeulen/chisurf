"""Complete six-language detector calibration labels and tooltips."""

import json
from pathlib import Path

from emtk.i18n import add_translations


def install_translations():
    catalog = json.loads(Path(__file__).with_name("translations.json").read_text())
    for locale, messages in catalog.items():
        add_translations(locale, messages, context="ImgCalibration")

"""
Settings module for lltf.

This module provides functions for loading and managing settings.
"""

from importlib import resources

import yaml

PACKAGE_NAME = "chisurf.plugins.fluorescence_decay.lltf.core"
SETTINGS_RESOURCE = "settings/lifetime_settings.yml"


def get_default_settings():
    """
    Get the default settings for lltf.

    Returns
    -------
    dict
        Default settings
    """
    settings_file = resources.files(PACKAGE_NAME).joinpath(SETTINGS_RESOURCE)
    with settings_file.open("r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)

    return settings


def load_settings(filename):
    """
    Load settings from a file.

    Parameters
    ----------
    filename : str
        Path to the settings file

    Returns
    -------
    dict
        Settings
    """
    # Load the settings
    with open(filename, encoding="utf-8") as f:
        settings = yaml.safe_load(f)

    return settings


def save_settings(settings, filename):
    """
    Save settings to a file.

    Parameters
    ----------
    settings : dict
        Settings to save
    filename : str
        Path to the settings file
    """
    # Save the settings
    with open(filename, "w", encoding="utf-8") as f:
        yaml.dump(settings, f, default_flow_style=False)

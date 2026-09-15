import pytest



def test_init_chisurf_onboarding_wizard_import():
    """
    Ensure the onboarding wizard plugin can be imported without errors.
    """
    try:
        from chisurf.plugins._dev.init_chisurf import wizard as _wizard  # noqa: F401
    except ImportError as e:
        pytest.fail(f"Could not import onboarding wizard: {e}")

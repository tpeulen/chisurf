import os
import re
import tempfile

import yaml


def float_representer(dumper, value):
    """
    Custom representer for float values to preserve scientific notation.

    Parameters
    ----------
    dumper : yaml.Dumper
        The YAML dumper instance.
    value : float
        The float value to represent.

    Returns
    -------
    yaml.ScalarNode
        The YAML scalar node with the appropriate representation.
    """
    # Use scientific notation for very small or very large numbers
    if abs(value) < 0.0001 or abs(value) > 1000000:
        # Format with scientific notation, preserving precision
        text = f"{value:.10e}"
        # Remove trailing zeros in the exponent part
        text = re.sub(r"e(\+|-)0*(\d+)", r"e\1\2", text)
        # Remove trailing zeros in the mantissa part
        text = re.sub(r"\.(\d*?)0+e", r".\1e", text)
        # If mantissa ends with a decimal point, remove it
        text = re.sub(r"\.e", r"e", text)
        return dumper.represent_scalar("tag:yaml.org,2002:float", text)
    else:
        # Use default representation for regular floats
        return dumper.represent_scalar("tag:yaml.org,2002:float", str(value))


class ScientificDumper(yaml.Dumper):
    """A dumper that writes floats the way the settings editor does.

    The representer is registered on **this subclass**, not on ``yaml.Dumper``.
    ``yaml.add_representer(float, ...)`` mutates the base dumper for the whole
    process, and at import time it did so before any test had run: every later
    ``yaml.dump`` in the same session — a curve saved to YAML, a project file —
    silently lost precision, because the representer keeps only ten decimal
    digits where a double needs seventeen. That is how this module used to turn
    ``test/core/test_curve.py::Tests::test_reading`` red whenever the two suites
    were collected together, and green when either ran alone.
    """


ScientificDumper.add_representer(float, float_representer)


def test_the_global_dumper_is_not_mutated():
    """Registering the representer must not leak into ``yaml.Dumper``."""
    assert yaml.Dumper.yaml_representers[float] is not float_representer
    text = yaml.dump({"tiny": 2.4492935982947064e-16})
    assert yaml.safe_load(text)["tiny"] == 2.4492935982947064e-16


def test_scientific_notation_preservation():
    """Test that scientific notation is preserved when saving and loading settings."""
    # Create a temporary file for testing
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_filename = temp_file.name

    try:
        # Create a test settings dictionary with scientific notation values
        test_settings = {
            "small_value": 1.23e-6,
            "large_value": 4.56e8,
            "regular_float": 3.14,
            "nested": {"nested_small": 7.89e-10, "nested_large": 9.87e12},
        }

        # Save the test settings to the temporary file
        with open(temp_filename, "w") as f:
            yaml.dump(test_settings, f, Dumper=ScientificDumper)

        # Read the raw YAML file to check if scientific notation is preserved in the file
        with open(temp_filename) as f:
            yaml_content = f.read()

        print("YAML file content:")
        print(yaml_content)

        # Check if scientific notation is present in the YAML file
        has_scientific_small = bool(re.search(r"1\.23e-0*6", yaml_content))
        has_scientific_large = bool(
            re.search(r"4\.56e\+0*8", yaml_content) or "456000000" in yaml_content
        )

        print(
            f"Scientific notation preserved in file: small={has_scientific_small}, large={has_scientific_large}"
        )

        # Load the settings from the file and check if values are preserved
        with open(temp_filename) as f:
            loaded_settings = yaml.safe_load(f)

        # Check that all values have the correct types and values
        print(
            f"small_value: {type(loaded_settings['small_value']).__name__} = {loaded_settings['small_value']}"
        )
        print(
            f"large_value: {type(loaded_settings['large_value']).__name__} = {loaded_settings['large_value']}"
        )
        print(
            f"regular_float: {type(loaded_settings['regular_float']).__name__} = {loaded_settings['regular_float']}"
        )
        print(
            f"nested_small: {type(loaded_settings['nested']['nested_small']).__name__} = {loaded_settings['nested']['nested_small']}"
        )
        print(
            f"nested_large: {type(loaded_settings['nested']['nested_large']).__name__} = {loaded_settings['nested']['nested_large']}"
        )

        # Verify that all values are still floats
        assert isinstance(loaded_settings["small_value"], float)
        assert isinstance(loaded_settings["large_value"], float)
        assert isinstance(loaded_settings["regular_float"], float)
        assert isinstance(loaded_settings["nested"]["nested_small"], float)
        assert isinstance(loaded_settings["nested"]["nested_large"], float)

        # Verify that the values are preserved
        assert abs(loaded_settings["small_value"] - 1.23e-6) < 1e-12
        assert abs(loaded_settings["large_value"] - 4.56e8) < 1
        assert abs(loaded_settings["regular_float"] - 3.14) < 1e-6
        assert abs(loaded_settings["nested"]["nested_small"] - 7.89e-10) < 1e-15
        assert abs(loaded_settings["nested"]["nested_large"] - 9.87e12) < 1e6

        print("All scientific notation values are correctly preserved!")

    finally:
        # Clean up the temporary file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)


if __name__ == "__main__":
    test_scientific_notation_preservation()

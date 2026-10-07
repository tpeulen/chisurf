"""
Simplified test script for the VV/VH G-Factor Calculator plugin.

This script creates a synthetic VV/VH data file that can be used to test the plugin
within the ChiSurf application.
"""

import os

import numpy as np

from chisurf.core.fio import write_vv_vh


# Create synthetic VV/VH data for testing
def create_synthetic_vv_vh_data(filename, n_points=1000):
    """Create a synthetic VV/VH file for testing."""
    # Time axis
    time = np.linspace(0, 10, n_points)

    # Create exponential decays
    decay = np.exp(-time / 2.0)

    # Add some noise
    np.random.seed(42)  # For reproducibility
    noise_level = 0.05
    parallel = decay + noise_level * np.random.randn(n_points)
    perpendicular = 0.6 * decay + noise_level * np.random.randn(n_points)  # Ideal signal ratio.

    # Ensure positive values
    parallel = np.maximum(parallel, 0.001)
    perpendicular = np.maximum(perpendicular, 0.001)

    # Combine into VV/VH format (parallel followed by perpendicular)
    vv_vh_data = np.concatenate([parallel, perpendicular])

    # Save to file using central VV/VH writer
    write_vv_vh(filename=filename, data=vv_vh_data, fmt="%.6f")

    print(f"Created synthetic VV/VH data file: {filename}")
    print("Ideal noise-free signal ratio: ~1.67; noisy tail ratios need not match it.")
    print("This reader fixture is not an instrument calibration reference.")

    return filename


if __name__ == "__main__":
    # Create a test file in the current directory
    test_file = os.path.join(os.path.dirname(__file__), "test_vv_vh_data.dat")
    create_synthetic_vv_vh_data(test_file)

    print("\nTest Instructions:")
    print("1. Launch ChiSurf")
    print("2. Open the VV/VH G-factor tool in the Decay Analysis workflow")
    print("3. Click 'Fast reference...' and select the test file at:", test_file)
    print("4. Set the tail bounds (yellow lines); use Guide for the control sequence")
    print("5. Observe the g-factor and standard deviation values update")
    print("6. Treat the noisy fitted G as a reader/calculation diagnostic, not calibration truth")

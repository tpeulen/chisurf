# BVA module -- the shot-noise reference line only; the analysis itself is
# tttrlib.BVA, driven from the burst_bva plugin one batched call per measurement.
from chisurf.core.fluorescence.burst.bva import compute_static_bva_line

# BOCPD module — thin wrapper around tttrlib C++ engine
from chisurf.core.fluorescence.burst.bocpd import (
    bocpd_filter,
    bocpd_burst_detection,
    bocpd_burst_detection_multi,
    convert_bursts_to_start_stop as bocpd_convert_bursts_to_start_stop,
)
import chisurf.core.fluorescence.burst.bocpd

# Kalman module -- kalman_filter/kalman_burst_search forward to the tttrlib
# engine; the names below them are the Python fallback that module keeps.
from chisurf.core.fluorescence.burst.kalman import (
    kalman_filter,
    kalman_burst_search,
    Burst,
    KalmanBurstResult,
    KalmanBurstDetector,
    bin_photons as kalman_bin_photons,
    bin_photons_multi as kalman_bin_photons_multi,
    kalman_burst_detection,
    kalman_burst_detection_multi
)
# Import with module prefix to avoid name conflict
import chisurf.core.fluorescence.burst.kalman

# Utils module
from chisurf.core.fluorescence.burst.utils import create_array_with_ones

# Count rate module
from chisurf.core.fluorescence.burst.count_rate import count_rate_filter

# Burst module
from chisurf.core.fluorescence.burst.burst import burst_filter

# CUSUM module
from chisurf.core.fluorescence.burst.cusum import cusum_filter

# Background estimation module
from chisurf.core.fluorescence.burst.background import (
    BackgroundDiagnostics,
    background_diagnostics_from_bursts,
    estimate_background_from_bursts,
    estimate_background_from_interphoton_times,
    interphoton_time_diagnostics,
)

# IRF + background from non-burst photons
from chisurf.core.fluorescence.burst.irf_bg import (
    DetectorIrfBackground,
    non_burst_mask,
    extract_irf_background,
    extract_mle_irf_background,
)

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

# Kalman module — forwards to the tttrlib C++ engine; the Python fallback
# was dead code and has been deleted.
from chisurf.core.fluorescence.burst.kalman import (
    kalman_filter,
    kalman_burst_search,
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

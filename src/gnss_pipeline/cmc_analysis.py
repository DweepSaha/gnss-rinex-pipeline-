"""
Code-Minus-Carrier (CMC) Multipath Detection — Phase 3 Milestone 2

The CMC observable isolates pseudorange multipath by subtracting
the carrier phase measurement from the pseudorange.

For GPS L1:
    CMC = C1C - L1C * wavelength

Because the carrier phase ambiguity is constant over a tracking arc,
variations in CMC directly measure pseudorange multipath.

A CMC standard deviation above 0.5 m indicates significant multipath.
"""
import numpy as np
from scipy.signal import savgol_filter

# GPS L1 frequency and wavelength
L1_FREQUENCY  = 1575.42e6        # Hz
SPEED_OF_LIGHT = 299_792_458.0   # m/s
L1_WAVELENGTH  = SPEED_OF_LIGHT / L1_FREQUENCY  # ~0.1903 m

# Detection thresholds
CMC_STD_CLEAN     = 0.3   # metres — below this: clean
CMC_STD_SUSPECT   = 0.5   # metres — below this: suspect, above: multipath
CMC_JUMP_THRESHOLD = 1.0  # metres — sudden jump indicates cycle slip

# Quality flags — same as SNR analysis for consistency
QUALITY_CLEAN     = "clean"
QUALITY_SUSPECT   = "suspect"
QUALITY_MULTIPATH = "multipath"


def extract_cmc(obs, sat: str) -> tuple:
    """
    Extract code-minus-carrier time series for one satellite.

    Requires both C1C (pseudorange) and L1C (carrier phase) observations.
    Carrier phase is in cycles — multiply by wavelength to get metres.

    Returns (epochs, cmc_metres) with NaN epochs removed.
    """
    try:
        pseudorange   = obs.sel(sv=sat)["C1C"].values.astype(float)
        carrier_cycles = obs.sel(sv=sat)["L1C"].values.astype(float)
        epochs        = obs.time.values

        # Convert carrier phase from cycles to metres
        carrier_metres = carrier_cycles * L1_WAVELENGTH

        # Compute CMC
        cmc = pseudorange - carrier_metres

        # Keep only epochs where both observations are valid
        valid = ~(np.isnan(pseudorange) | np.isnan(carrier_cycles))
        return epochs[valid], cmc[valid]

    except Exception as e:
        return np.array([]), np.array([])


def detect_cycle_slips(cmc: np.ndarray) -> np.ndarray:
    """
    Detect cycle slips — sudden large jumps in the CMC time series.

    A cycle slip happens when the receiver loses lock on the carrier phase
    and restarts counting cycles from a new ambiguity. This produces an
    instantaneous jump of many metres in the CMC.

    Returns a boolean array — True where a cycle slip occurred.
    """
    if len(cmc) < 2:
        return np.zeros(len(cmc), dtype=bool)

    diffs      = np.abs(np.diff(cmc))
    slip_mask  = np.concatenate([[False], diffs > CMC_JUMP_THRESHOLD])
    return slip_mask


def remove_ambiguity_and_trend(cmc: np.ndarray, slip_mask: np.ndarray) -> np.ndarray:
    """
    Remove the carrier phase integer ambiguity AND ionospheric drift from CMC.

    The raw CMC contains:
      1. A large constant offset (integer ambiguity) — removed by subtracting arc mean
      2. A slow smooth drift (ionospheric divergence) — removed by high-pass filtering
      3. Rapid variations (actual multipath) — what we want to keep

    We use a Savitzky-Golay filter to estimate the slow trend,
    then subtract it to isolate the high-frequency multipath signal.
    """
    cmc_detrended = np.full_like(cmc, np.nan)

    # Find arc boundaries from cycle slips
    arc_starts = [0] + list(np.where(slip_mask)[0])
    arc_ends   = list(np.where(slip_mask)[0]) + [len(cmc)]

    for start, end in zip(arc_starts, arc_ends):
        arc = cmc[start:end]
        if len(arc) < 5:
            continue

        # Step 1: remove integer ambiguity (subtract mean)
        arc_zero = arc - np.mean(arc)

        # Step 2: remove slow ionospheric drift using Savitzky-Golay
        # Window must be odd and <= arc length
        window = min(len(arc_zero) - 1, 21)
        if window % 2 == 0:
            window -= 1
        if window < 5:
            cmc_detrended[start:end] = arc_zero
            continue

        try:
            from scipy.signal import savgol_filter
            trend = savgol_filter(arc_zero, window_length=window, polyorder=2)
            # High-pass: subtract the slow trend, keep rapid variations
            cmc_detrended[start:end] = arc_zero - trend
        except Exception:
            cmc_detrended[start:end] = arc_zero

    return cmc_detrended


def classify_satellite_cmc(cmc_detrended: np.ndarray) -> dict:
    """
    Classify multipath severity from the detrended CMC time series.

    Returns a dict with:
        flag:      quality classification
        std:       standard deviation of CMC in metres
        rms:       RMS of CMC in metres
        max_abs:   maximum absolute CMC deviation in metres
        n_epochs:  number of valid epochs used
    """
    valid = cmc_detrended[~np.isnan(cmc_detrended)]

    if len(valid) < 4:
        return {
            "flag":     QUALITY_SUSPECT,
            "std":      np.nan,
            "rms":      np.nan,
            "max_abs":  np.nan,
            "n_epochs": len(valid),
        }

    std     = float(np.std(valid))
    rms     = float(np.sqrt(np.mean(valid**2)))
    max_abs = float(np.max(np.abs(valid)))

    if std < CMC_STD_CLEAN:
        flag = QUALITY_CLEAN
    elif std < CMC_STD_SUSPECT:
        flag = QUALITY_SUSPECT
    else:
        flag = QUALITY_MULTIPATH

    return {
        "flag":     flag,
        "std":      round(std, 4),
        "rms":      round(rms, 4),
        "max_abs":  round(max_abs, 3),
        "n_epochs": len(valid),
    }


def analyse_session_cmc(obs) -> dict:
    """
    Run CMC multipath analysis for all GPS satellites in a session.

    Returns a dict keyed by satellite ID, each containing:
        epochs:       time array
        cmc_raw:      raw CMC in metres (with ambiguity)
        cmc_detrended: CMC with ambiguity removed
        slip_mask:    boolean array of cycle slip locations
        result:       output of classify_satellite_cmc
    """
    gps_sats = [str(s) for s in obs.sv.values if str(s).startswith("G")]
    session_results = {}

    for sat in gps_sats:
        epochs, cmc_raw = extract_cmc(obs, sat)

        if len(cmc_raw) < 4:
            continue

        slip_mask    = detect_cycle_slips(cmc_raw)
        cmc_detrended = remove_ambiguity_and_trend(cmc_raw, slip_mask)
        result       = classify_satellite_cmc(cmc_detrended)

        session_results[sat] = {
            "epochs":        epochs,
            "cmc_raw":       cmc_raw,
            "cmc_detrended": cmc_detrended,
            "slip_mask":     slip_mask,
            "result":        result,
        }

    return session_results


def combine_snr_cmc_flags(snr_results: dict, cmc_results: dict) -> dict:
    """
    Combine SNR and CMC quality flags into a single per-satellite flag.

    If either method flags a satellite as multipath, it is multipath.
    If either method flags suspect, it is suspect.
    Otherwise clean.

    This is the final quality flag used by the weighted SPP solver.

    Returns dict {sat_id: combined_flag}
    """
    all_sats = set(list(snr_results.keys()) + list(cmc_results.keys()))
    combined = {}

    priority = {
        QUALITY_MULTIPATH: 2,
        QUALITY_SUSPECT:   1,
        QUALITY_CLEAN:     0,
    }
    reverse  = {2: QUALITY_MULTIPATH, 1: QUALITY_SUSPECT, 0: QUALITY_CLEAN}

    for sat in all_sats:
        snr_flag = snr_results.get(sat, {}).get("result", {}).get("flag", QUALITY_SUSPECT)
        cmc_flag = cmc_results.get(sat, {}).get("result", {}).get("flag", QUALITY_SUSPECT)

        worst = max(priority[snr_flag], priority[cmc_flag])
        combined[sat] = reverse[worst]

    return combined
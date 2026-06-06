"""
SNR Analysis Module — Phase 3 Milestone 1

Extracts Signal-to-Noise Ratio observations from RINEX files,
detects multipath contamination through SNR deviation analysis,
and assigns per-satellite quality flags.
"""
import numpy as np
from scipy.signal import savgol_filter


# Quality flag constants — used throughout Phase 3
QUALITY_CLEAN    = "clean"
QUALITY_SUSPECT  = "suspect"
QUALITY_MULTIPATH = "multipath"

# SNR thresholds in dB-Hz
SNR_MINIMUM          = 25.0   # below this → always multipath/blocked
SNR_DEVIATION_CLEAN  = 3.0    # deviation below this → clean
SNR_DEVIATION_SUSPECT = 6.0   # deviation below this → suspect, above → multipath


def extract_snr(obs, sat: str, snr_field: str = "S1C") -> tuple:
    """
    Extract SNR time series for one satellite from a georinex Dataset.

    Returns (epochs, snr_values) where both are numpy arrays.
    Epochs where SNR is NaN are removed.
    """
    try:
        snr_raw = obs.sel(sv=sat)[snr_field].values
        epochs  = obs.time.values

        # Keep only non-NaN epochs
        valid_mask = ~np.isnan(snr_raw)
        return epochs[valid_mask], snr_raw[valid_mask]

    except Exception:
        return np.array([]), np.array([])


def compute_snr_deviation(snr_values: np.ndarray, window: int = 11) -> np.ndarray:
    """
    Compute the deviation of SNR from its smoothed trend.

    Uses a Savitzky-Golay filter to estimate the smooth baseline,
    then returns the absolute deviation at each epoch.

    A large deviation means the SNR is oscillating — the multipath signature.

    snr_values: array of SNR in dB-Hz
    window:     number of epochs to use for smoothing (must be odd)
                At 30-second sampling, window=11 covers 5.5 minutes

    Returns array of absolute deviations in dB-Hz.
    """
    if len(snr_values) < window:
        # Not enough data for Savitzky-Golay — use simple mean deviation
        return np.abs(snr_values - np.mean(snr_values))

    # Savitzky-Golay gives a smooth polynomial fit through the data
    # polyorder=2 means it fits a parabola through each window
    smoothed  = savgol_filter(snr_values, window_length=window, polyorder=2)
    deviation = np.abs(snr_values - smoothed)
    return deviation


def classify_satellite_snr(snr_values: np.ndarray) -> dict:
    """
    Classify a satellite's signal quality based on its full SNR time series.

    Returns a dict with:
        flag:           overall quality flag (clean/suspect/multipath)
        mean_snr:       mean SNR in dB-Hz
        mean_deviation: mean SNR deviation in dB-Hz
        pct_low:        percentage of epochs with SNR below minimum threshold
        deviations:     per-epoch deviation array
    """
    if len(snr_values) == 0:
        return {
            "flag": QUALITY_SUSPECT,
            "mean_snr": 0.0,
            "mean_deviation": 0.0,
            "pct_low": 100.0,
            "deviations": np.array([]),
        }

    deviations   = compute_snr_deviation(snr_values)
    mean_snr     = float(np.mean(snr_values))
    mean_dev     = float(np.mean(deviations))
    pct_low      = float(np.sum(snr_values < SNR_MINIMUM) / len(snr_values) * 100)

    # Classification logic
    if mean_snr < SNR_MINIMUM or pct_low > 20.0:
        flag = QUALITY_MULTIPATH
    elif mean_dev > SNR_DEVIATION_SUSPECT:
        flag = QUALITY_MULTIPATH
    elif mean_dev > SNR_DEVIATION_CLEAN or mean_snr < 35.0:
        flag = QUALITY_SUSPECT
    else:
        flag = QUALITY_CLEAN

    return {
        "flag":           flag,
        "mean_snr":       round(mean_snr, 2),
        "mean_deviation": round(mean_dev, 3),
        "pct_low":        round(pct_low, 1),
        "deviations":     deviations,
    }


def analyse_session_snr(obs, snr_field: str = "S1C") -> dict:
    """
    Run SNR analysis for all GPS satellites in a session.

    Returns a dict keyed by satellite ID, each containing:
        epochs:     time array
        snr:        SNR value array
        result:     output of classify_satellite_snr
    """
    gps_sats = [str(s) for s in obs.sv.values if str(s).startswith("G")]
    session_results = {}

    for sat in gps_sats:
        epochs, snr_values = extract_snr(obs, sat, snr_field)

        if len(snr_values) < 4:
            continue

        result = classify_satellite_snr(snr_values)

        session_results[sat] = {
            "epochs": epochs,
            "snr":    snr_values,
            "result": result,
        }

    return session_results


def get_epoch_weights(
    combined_flags: dict,
) -> dict:
    """
    Convert combined quality flags into numerical weights for the SPP solver.

    clean     → 1.0  (full trust)
    suspect   → 0.3  (reduced trust)
    multipath → 0.05 (near-excluded)

    combined_flags: dict {sat_id: flag_string}
    Returns dict {sat_id: weight}
    """
    weight_map = {
        QUALITY_CLEAN:     1.0,
        QUALITY_SUSPECT:   0.3,
        QUALITY_MULTIPATH: 0.05,
    }

    return {
        sat: weight_map.get(flag, 0.3)
        for sat, flag in combined_flags.items()
    }
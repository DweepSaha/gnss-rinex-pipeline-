import numpy as np
import json


def load_reference_coords(json_path: str) -> dict:
    """Load NRCan reference coordinates from JSON file."""
    with open(json_path) as f:
        return json.load(f)


def compute_position_error(
    computed_lat: float, computed_lon: float, computed_height: float,
    ref_lat: float,      ref_lon: float,      ref_height: float,
) -> dict:
    """
    Compute position error between computed and reference positions.
    Returns horizontal error, vertical error, and 3D error in metres.
    """
    lat_r = np.radians(ref_lat)

    # Radius of curvature
    A_EARTH = 6_378_137.0
    E2      = 0.00669437999014
    N = A_EARTH / np.sqrt(1 - E2 * np.sin(lat_r)**2)
    M = A_EARTH * (1 - E2) / (1 - E2 * np.sin(lat_r)**2)**1.5

    # Convert degree differences to metres
    delta_lat_m = np.radians(computed_lat - ref_lat) * M
    delta_lon_m = np.radians(computed_lon - ref_lon) * N * np.cos(lat_r)
    delta_h_m   = computed_height - ref_height

    horizontal = np.sqrt(delta_lat_m**2 + delta_lon_m**2)
    vertical   = abs(delta_h_m)
    error_3d   = np.sqrt(horizontal**2 + vertical**2)

    return {
        "horizontal_m": horizontal,
        "vertical_m":   vertical,
        "error_3d_m":   error_3d,
        "north_m":      delta_lat_m,
        "east_m":       delta_lon_m,
    }


def compute_accuracy_statistics(
    errors_horizontal: list,
    errors_vertical:   list,
) -> dict:
    """
    Compute standard GNSS accuracy statistics.

    CEP50:  median horizontal error (50th percentile)
    CEP95:  95th percentile horizontal error
    RMSE_H: RMS horizontal error
    RMSE_V: RMS vertical error
    2DRMS:  twice the RMS horizontal error
    """
    eh = np.array(errors_horizontal)
    ev = np.array(errors_vertical)

    eh = eh[~np.isnan(eh)]
    ev = ev[~np.isnan(ev)]

    if len(eh) == 0:
        return {}

    return {
        "CEP50":    round(float(np.percentile(eh, 50)), 3),
        "CEP95":    round(float(np.percentile(eh, 95)), 3),
        "RMSE_H":   round(float(np.sqrt(np.mean(eh**2))), 3),
        "RMSE_V":   round(float(np.sqrt(np.mean(ev**2))), 3),
        "2DRMS":    round(float(2 * np.sqrt(np.mean(eh**2))), 3),
        "mean_H":   round(float(np.mean(eh)), 3),
        "std_H":    round(float(np.std(eh)), 3),
        "n_epochs": len(eh),
    }
import numpy as np
from typing import Optional
from src.gnss_pipeline.corrections import (
    satellite_clock_correction,
    relativistic_correction,
    klobuchar_iono_correction,
    tropospheric_delay,
    SPEED_OF_LIGHT,
)
from src.gnss_pipeline.ephemeris import compute_satellite_position

try:
    import pymap3d as pm
except ImportError:
    pm = None


# WGS84 constants
A_EARTH = 6_378_137.0
F_EARTH = 1 / 298.257223563
E2      = 2 * F_EARTH - F_EARTH**2


def ecef_to_geodetic(x: float, y: float, z: float):
    """Convert ECEF XYZ to geodetic (lat_deg, lon_deg, height_m)."""
    lon = np.degrees(np.arctan2(y, x))
    p   = np.sqrt(x**2 + y**2)
    lat = np.arctan2(z, p * (1 - E2))

    for _ in range(10):
        N       = A_EARTH / np.sqrt(1 - E2 * np.sin(lat)**2)
        lat_new = np.arctan2(z + E2 * N * np.sin(lat), p)
        if abs(lat_new - lat) < 1e-12:
            break
        lat = lat_new

    lat = lat_new
    N   = A_EARTH / np.sqrt(1 - E2 * np.sin(lat)**2)
    h   = (
        p / np.cos(lat) - N
        if abs(np.cos(lat)) > 1e-10
        else abs(z) / np.sin(lat) - N * (1 - E2)
    )

    return np.degrees(lat), lon, h


def geodetic_to_ecef(lat_deg: float, lon_deg: float, h_m: float):
    """Convert geodetic (lat_deg, lon_deg, h_m) to ECEF XYZ."""
    lat = np.radians(lat_deg)
    lon = np.radians(lon_deg)
    N   = A_EARTH / np.sqrt(1 - E2 * np.sin(lat)**2)
    x   = (N + h_m) * np.cos(lat) * np.cos(lon)
    y   = (N + h_m) * np.cos(lat) * np.sin(lon)
    z   = (N * (1 - E2) + h_m) * np.sin(lat)
    return x, y, z


def solve_spp_epoch(
    pseudoranges:             dict,
    sat_positions:            dict,
    sat_ephemerides:          dict,
    sat_eccentric_anomalies:  dict,
    elevations:               dict,
    azimuths:                 dict,
    nav_header:               dict,
    gps_time:                 float,
    x0:                       Optional[np.ndarray] = None,
    elevation_mask_deg:       float = 10.0,
    max_iterations:           int   = 20,
    convergence_threshold:    float = 0.001,
    weights:                  dict  = None,
) -> dict:
    """
    Single Point Positioning solver using iterative weighted least squares.

    Pseudorange observation model:
        rho_corrected = rho_measured + c*dts + c*dtr - iono - tropo
        rho_corrected = geometric_range + c*dtr_receiver

    weights: optional dict {sat_id: float} where 1.0 = full trust,
             0.3 = suspect, 0.05 = multipath contaminated.
             If None, all satellites receive equal weight of 1.0.

    Sign convention for clock correction:
        dts is typically negative (satellite clock running slow).
        Adding c*dts to pseudorange reduces it toward the geometric range.
    """

    # Filter satellites below elevation mask
    valid_sats = [
        s for s in pseudoranges
        if s in sat_positions
        and s in elevations
        and elevations[s] >= np.radians(elevation_mask_deg)
    ]

    if len(valid_sats) < 4:
        return {"converged": False, "n_sats_used": len(valid_sats)}

    # Initial state: [X, Y, Z, c*dt_receiver] in metres
    if x0 is None:
        x0 = np.array([0.0, 0.0, 6_371_000.0, 0.0])
    state = x0.copy().astype(float)

    converged    = False
    sat_ids_used = []
    H            = None
    dRho         = None

    for iteration in range(max_iterations):
        X_r, Y_r, Z_r = state[0], state[1], state[2]
        c_dtr          = state[3]

        rows_H       = []
        delta_rho    = []
        sat_ids_used = []

        # Receiver geodetic position for ionospheric model
        lat_r_rad, lon_r_rad, _ = ecef_to_geodetic(X_r, Y_r, Z_r)
        lat_r_rad = np.radians(lat_r_rad)
        lon_r_rad = np.radians(lon_r_rad)

        for sat in valid_sats:
            Xs, Ys, Zs   = sat_positions[sat]
            rho_measured = pseudoranges[sat]

            # Geometric range from current state estimate
            dx = Xs - X_r
            dy = Ys - Y_r
            dz = Zs - Z_r
            r0 = np.sqrt(dx**2 + dy**2 + dz**2)

            if r0 < 1e3:
                continue

            eph = sat_ephemerides.get(sat, {})

            # 1. Satellite clock correction (seconds → metres)
            #    dts is typically negative → adding c*dts reduces pseudorange
            dts          = satellite_clock_correction(eph, gps_time) if eph else 0.0
            clock_corr_m = dts * SPEED_OF_LIGHT

            # 2. Relativistic correction (seconds → metres)
            Ek        = sat_eccentric_anomalies.get(sat, 0.0)
            dtr       = relativistic_correction(eph, Ek) if eph else 0.0
            relativ_m = dtr * SPEED_OF_LIGHT

            # 3. Ionospheric delay (metres, positive — slows signal)
            iono_m = klobuchar_iono_correction(
                nav_header,
                elevations[sat],
                azimuths[sat],
                lat_r_rad,
                lon_r_rad,
                gps_time,
            )

            # 4. Tropospheric delay (metres, positive — slows signal)
            tropo_m = tropospheric_delay(elevations[sat])

            # Corrected pseudorange
            # + clock corrections (dts negative → reduces pseudorange)
            # - atmospheric delays (positive → inflated pseudorange)
            rho_corrected = (
                rho_measured
                + clock_corr_m
                + relativ_m
                - iono_m
                - tropo_m
            )

            # Linearised residual
            delta_rho_i = rho_corrected - r0 - c_dtr

            # Design matrix row: [-lx, -ly, -lz, 1]
            rows_H.append([-dx/r0, -dy/r0, -dz/r0, 1.0])
            delta_rho.append(delta_rho_i)
            sat_ids_used.append(sat)

        if len(rows_H) < 4:
            return {"converged": False, "n_sats_used": len(rows_H)}

        H    = np.array(rows_H)
        dRho = np.array(delta_rho)

        # Build weight vector — one entry per satellite used
        w_vec = np.ones(len(sat_ids_used))
        if weights is not None:
            for i, sat in enumerate(sat_ids_used):
                w_vec[i] = float(weights.get(sat, 1.0))

        # Weighted least squares: dx = (H'WH)^-1 H'W dRho
        # W is diagonal so we scale rows directly — avoids building N×N matrix
        try:
            Hw    = H    * w_vec[:, np.newaxis]   # scale each H row by weight
            dRhow = dRho * w_vec                  # scale each residual by weight
            HtWH  = Hw.T @ H                      # = H' W H
            HtWdr = Hw.T @ dRho                   # = H' W dRho
            dx_vec = np.linalg.solve(HtWH, HtWdr)
        except np.linalg.LinAlgError:
            return {"converged": False, "n_sats_used": len(rows_H)}

        state += dx_vec

        if np.linalg.norm(dx_vec[:3]) < convergence_threshold:
            converged = True
            break

    # Final post-fit residuals
    X_r, Y_r, Z_r = state[0], state[1], state[2]
    c_dtr          = state[3]
    residuals      = {}
    for sat in sat_ids_used:
        Xs, Ys, Zs = sat_positions[sat]
        r_final    = np.sqrt((Xs-X_r)**2 + (Ys-Y_r)**2 + (Zs-Z_r)**2)
        residuals[sat] = pseudoranges[sat] - r_final - c_dtr

    lat, lon, height = ecef_to_geodetic(state[0], state[1], state[2])

    return {
        "converged":     converged,
        "position_ecef": state[:3],
        "clock_bias_m":  state[3],
        "lat":           lat,
        "lon":           lon,
        "height":        height,
        "residuals":     residuals,
        "H":             H,
        "n_sats_used":   len(sat_ids_used),
        "sat_ids_used":  sat_ids_used,
    }
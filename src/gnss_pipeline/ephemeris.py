import math
import warnings
from pathlib import Path

import georinex as gr

warnings.filterwarnings("ignore", category=FutureWarning)

MU = 3.986005e14
OMEGA_E_DOT = 7.2921151467e-5


def solve_kepler(mean_anomaly, eccentricity, tolerance=1e-12, max_iterations=20):
    eccentric_anomaly = mean_anomaly

    for _ in range(max_iterations):
        correction = (
            eccentric_anomaly
            - eccentricity * math.sin(eccentric_anomaly)
            - mean_anomaly
        ) / (1 - eccentricity * math.cos(eccentric_anomaly))

        eccentric_anomaly -= correction

        if abs(correction) < tolerance:
            break

    return eccentric_anomaly


def get_first_valid_ephemeris(nav, sat, gps_time_of_week: float = None):
    """
    Get the best ephemeris record for a satellite at a given GPS time.

    If gps_time_of_week is provided, selects the ephemeris record whose
    Toe is closest to the observation time — this is critical for sessions
    far from midnight when multiple ephemeris records exist per satellite.

    If gps_time_of_week is None, falls back to the first valid record
    (original Phase 2 behaviour — safe for midnight sessions).
    """
    sat_data = nav.sel(sv=sat)

    required_vars = [
        "sqrtA", "Eccentricity", "M0", "DeltaN",
        "Omega0", "omega", "Io", "Toe",
        "Cuc", "Cus", "Crc", "Crs", "Cic", "Cis", "IDOT",
    ]

    clock_vars = [
        "SVclockBias", "SVclockDrift", "SVclockDriftRate",
        "TGD", "GPSWeek",
    ]

    # Collect all valid ephemeris records
    valid_records = []
    for i, epoch in enumerate(sat_data.time.values):
        try:
            values = {var: float(sat_data[var].values[i]) for var in required_vars}
        except Exception:
            continue

        if not all(v == v for v in values.values()):
            continue

        for cvar in clock_vars:
            try:
                values[cvar] = float(sat_data[cvar].values[i])
            except Exception:
                values[cvar] = 0.0

        valid_records.append((epoch, values))

    if not valid_records:
        raise ValueError(f"No valid ephemeris found for {sat}")

    # If no GPS time provided, return first valid record (Phase 2 behaviour)
    if gps_time_of_week is None:
        return valid_records[0]

    # Select the record whose Toe is closest to the observation time
    # Handle week rollover when comparing times
    def toe_distance(record):
        toe = record[1]["Toe"]
        dt  = gps_time_of_week - toe
        # Unwrap to find true distance
        if dt > 302400:
            dt -= 604800
        elif dt < -302400:
            dt += 604800
        return abs(dt)

    best = min(valid_records, key=toe_distance)
    return best


def compute_satellite_position(eph, transmit_time_seconds):
    sqrt_a = eph["sqrtA"]
    semi_major_axis = sqrt_a**2
    eccentricity = eph["Eccentricity"]

    mean_motion_0 = math.sqrt(MU / semi_major_axis**3)
    corrected_mean_motion = mean_motion_0 + eph["DeltaN"]

    time_from_ephemeris = transmit_time_seconds - eph["Toe"]

    # Handle week crossover in time_from_ephemeris
    if time_from_ephemeris > 302400:
        time_from_ephemeris -= 604800
    elif time_from_ephemeris < -302400:
        time_from_ephemeris += 604800

    mean_anomaly = eph["M0"] + corrected_mean_motion * time_from_ephemeris

    eccentric_anomaly = solve_kepler(mean_anomaly, eccentricity)

    true_anomaly = math.atan2(
        math.sqrt(1 - eccentricity**2) * math.sin(eccentric_anomaly),
        math.cos(eccentric_anomaly) - eccentricity,
    )

    argument_of_latitude = true_anomaly + eph["omega"]

    delta_u = eph["Cus"] * math.sin(2 * argument_of_latitude) + eph["Cuc"] * math.cos(2 * argument_of_latitude)
    delta_r = eph["Crs"] * math.sin(2 * argument_of_latitude) + eph["Crc"] * math.cos(2 * argument_of_latitude)
    delta_i = eph["Cis"] * math.sin(2 * argument_of_latitude) + eph["Cic"] * math.cos(2 * argument_of_latitude)

    corrected_u = argument_of_latitude + delta_u
    corrected_r = semi_major_axis * (1 - eccentricity * math.cos(eccentric_anomaly)) + delta_r
    corrected_i = eph["Io"] + delta_i + eph["IDOT"] * time_from_ephemeris

    x_orbital = corrected_r * math.cos(corrected_u)
    y_orbital = corrected_r * math.sin(corrected_u)

    # Corrected longitude of ascending node
    # Formula: Omega0 + (OmegaDot - OMEGA_E_DOT) * tk - OMEGA_E_DOT * Toe
    omega_dot = eph.get("OmegaDot", 0.0)
    corrected_omega = (
        eph["Omega0"]
        + (omega_dot - OMEGA_E_DOT) * time_from_ephemeris
        - OMEGA_E_DOT * eph["Toe"]
    )

    x_ecef = (
        x_orbital * math.cos(corrected_omega)
        - y_orbital * math.cos(corrected_i) * math.sin(corrected_omega)
    )
    y_ecef = (
        x_orbital * math.sin(corrected_omega)
        + y_orbital * math.cos(corrected_i) * math.cos(corrected_omega)
    )
    z_ecef = y_orbital * math.sin(corrected_i)

    return x_ecef, y_ecef, z_ecef


if __name__ == "__main__":
    nav_file = Path("data/raw/extracted/ALGO00CAN_R_20251520000_01D_MN.rnx")
    nav = gr.load(nav_file)

    sat = "G02"
    epoch, eph = get_first_valid_ephemeris(nav, sat)

    print("Satellite:", sat)
    print("Ephemeris epoch:", epoch)

    x, y, z = compute_satellite_position(eph, transmit_time_seconds=0.0)

    print("\nSatellite ECEF position:")
    print("X:", x)
    print("Y:", y)
    print("Z:", z)
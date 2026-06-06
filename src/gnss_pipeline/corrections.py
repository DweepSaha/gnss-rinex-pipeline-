import numpy as np

# Physical constants
SPEED_OF_LIGHT = 299_792_458.0        # metres per second
MU = 3.986005e14                       # Earth's gravitational constant m^3/s^2
OMEGA_E_DOT = 7.2921151467e-5         # Earth's rotation rate rad/s
F = -4.442807633e-10                   # Relativistic correction constant


def satellite_clock_correction(eph: dict, t: float) -> float:
    toc = float(eph.get("Toe", 0.0))
    af0 = float(eph.get("SVclockBias", 0.0))
    af1 = float(eph.get("SVclockDrift", 0.0))
    af2 = float(eph.get("SVclockDriftRate", 0.0))

    dt = t - toc

    # Handle week rollover in both directions
    if dt > 302400:
        dt -= 604800
    elif dt < -302400:
        dt += 604800

    return af0 + af1 * dt + af2 * dt**2


def relativistic_correction(eph: dict, Ek: float) -> float:
    """
    Compute relativistic clock correction in seconds.

    This is a small but mandatory correction (~nanoseconds)
    caused by the satellite's velocity and gravitational potential.

    eph: ephemeris dict containing sqrtA and Eccentricity
    Ek:  eccentric anomaly in radians (from ephemeris.py)

    Returns correction in seconds.
    """
    sqrtA = float(eph["sqrtA"])
    e = float(eph["Eccentricity"])
    A = sqrtA**2
    return F * e * sqrtA * np.sin(Ek)


def klobuchar_iono_correction(
    eph_header: dict,
    elevation_rad: float,
    azimuth_rad: float,
    lat_receiver_rad: float,
    lon_receiver_rad: float,
    gps_time_seconds: float,
) -> float:
    """
    Klobuchar ionospheric delay model.
    Returns ionospheric delay in metres on L1 frequency.

    eph_header: dict with keys 'IONOSPHERIC CORR' containing alpha and beta
    elevation_rad: satellite elevation in radians
    azimuth_rad:   satellite azimuth in radians
    lat_receiver_rad: receiver geodetic latitude in radians
    lon_receiver_rad: receiver geodetic longitude in radians
    gps_time_seconds: GPS time of week in seconds
    """
    # Extract Klobuchar coefficients from navigation file header
    # georinex stores them as GPSA (alpha) and GPSB (beta)
    alpha = eph_header.get("GPSA", [0.0, 0.0, 0.0, 0.0])
    beta  = eph_header.get("GPSB", [0.0, 0.0, 0.0, 0.0])

    # If not found, return 0 (no correction applied)
    if alpha is None or beta is None:
        return 0.0

    a0, a1, a2, a3 = [float(x) for x in alpha]
    b0, b1, b2, b3 = [float(x) for x in beta]

    # Semi-circle units (Klobuchar uses semi-circles, not degrees or radians)
    phi_u = lat_receiver_rad / np.pi   # receiver latitude in semi-circles
    lam_u = lon_receiver_rad / np.pi   # receiver longitude in semi-circles
    El = elevation_rad / np.pi         # elevation in semi-circles
    Az = azimuth_rad / np.pi           # azimuth in semi-circles

    # Earth-centred angle (semi-circles)
    psi = 0.0137 / (El + 0.11) - 0.022

    # Subionospheric latitude (semi-circles)
    phi_I = phi_u + psi * np.cos(azimuth_rad)
    phi_I = np.clip(phi_I, -0.416, 0.416)

    # Subionospheric longitude (semi-circles)
    lam_I = lam_u + (psi * np.sin(azimuth_rad)) / np.cos(phi_I * np.pi)

    # Geomagnetic latitude of subionospheric point (semi-circles)
    phi_m = phi_I + 0.064 * np.cos((lam_I - 1.617) * np.pi)

    # Local time at subionospheric point (seconds)
    t_local = 43200.0 * lam_I + gps_time_seconds
    t_local = t_local % 86400.0  # wrap to 0-86400

    # Amplitude of ionospheric delay
    AMP = a0 + a1 * phi_m + a2 * phi_m**2 + a3 * phi_m**3
    AMP = max(AMP, 0.0)

    # Period of ionospheric delay
    PER = b0 + b1 * phi_m + b2 * phi_m**2 + b3 * phi_m**3
    PER = max(PER, 72000.0)

    # Phase of ionospheric delay
    X = 2.0 * np.pi * (t_local - 50400.0) / PER

    # Slant factor (elevation-dependent mapping function)
    F_iono = 1.0 + 16.0 * (0.53 - El) ** 3

    # Ionospheric delay in seconds
    if abs(X) < 1.57:
        T_iono = F_iono * (5e-9 + AMP * (1 - X**2 / 2 + X**4 / 24))
    else:
        T_iono = F_iono * 5e-9

    # Convert to metres
    return T_iono * SPEED_OF_LIGHT


def tropospheric_delay(elevation_rad: float) -> float:
    """
    Simplified tropospheric delay model (Hopfield simplified).
    Returns tropospheric delay in metres.

    elevation_rad: satellite elevation angle in radians

    Accuracy: approximately 1-3 metres.
    Adequate for Phase 2; can be replaced with Saastamoinen in Phase 3.
    """
    elevation_deg = np.degrees(elevation_rad)
    # Avoid division by near-zero for very low elevation satellites
    if elevation_deg < 5.0:
        return 0.0  # exclude very low satellites entirely
    return 2.47 / (np.sin(elevation_rad) + 0.0121)
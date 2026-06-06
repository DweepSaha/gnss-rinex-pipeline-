import numpy as np
import pymap3d as pm


def compute_az_el(sat_x, sat_y, sat_z, lat_deg, lon_deg, height_m):
    """
    Compute azimuth, elevation, and range from receiver to satellite.

    sat_x, sat_y, sat_z: satellite ECEF position in metres
    lat_deg, lon_deg, height_m: receiver geodetic position

    Returns (azimuth_deg, elevation_deg, range_m)
    """
    az, el, rng = pm.ecef2aer(
        sat_x, sat_y, sat_z,
        lat_deg, lon_deg, height_m,
        deg=True
    )
    return az, el, rng
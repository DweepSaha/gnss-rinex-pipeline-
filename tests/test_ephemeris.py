import georinex as gr

from src.gnss_pipeline.ephemeris import (
    compute_satellite_position,
    get_first_valid_ephemeris,
)


def test_g02_broadcast_ephemeris_position():
    nav = gr.load("data/raw/extracted/ALGO00CAN_R_20251520000_01D_MN.rnx")

    sat = "G02"
    epoch, eph = get_first_valid_ephemeris(nav, sat)

    x, y, z = compute_satellite_position(eph, transmit_time_seconds=0.0)

    expected_x = -15142547.116033388
    expected_y = 4117458.830998603
    expected_z = 21819137.842778813

    tolerance_meters = 1.0

    assert abs(x - expected_x) < tolerance_meters
    assert abs(y - expected_y) < tolerance_meters
    assert abs(z - expected_z) < tolerance_meters
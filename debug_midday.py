"""
Diagnose midday session positioning failure.
Run from project root.
"""
import georinex as gr
import numpy as np
from src.gnss_pipeline.ephemeris import compute_satellite_position, get_first_valid_ephemeris
from src.gnss_pipeline.az_el import compute_az_el
from src.gnss_pipeline.spp_solver import solve_spp_epoch, geodetic_to_ecef, ecef_to_geodetic
from src.gnss_pipeline.accuracy import load_reference_coords, compute_position_error

SPEED_OF_LIGHT = 299_792_458.0
OBS_FILE = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx"
NAV_FILE = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_MN.rnx"
REF_FILE = "data/reference/nrcan_reference_coords.json"

ref       = load_reference_coords(REF_FILE)["FRDN"]
gps_epoch = np.datetime64("1980-01-06T00:00:00", "s")

print("Loading midday observation file...")
obs = gr.load(OBS_FILE, use="G",
              tlim=["2025-06-01T14:00:00", "2025-06-01T14:05:00"])
nav = gr.load(NAV_FILE, use="G")

epoch = obs.time.values[0]
print(f"First epoch: {epoch}")

epoch_s           = epoch.astype("datetime64[s]")
total_gps_seconds = float((epoch_s - gps_epoch).astype(float))
gps_time_of_week  = total_gps_seconds % 604800.0
gps_week          = int(total_gps_seconds // 604800)

print(f"Total GPS seconds: {total_gps_seconds:.1f}")
print(f"GPS week:          {gps_week}")
print(f"GPS time of week:  {gps_time_of_week:.1f} s")
print()

gps_sats = [s for s in obs.sv.values if str(s).startswith("G")]

pseudoranges  = {}
sat_positions = {}
elevations    = {}
azimuths      = {}
ephemerides   = {}

print("Satellite diagnostics (using closest ephemeris to observation time):")
print(f"{'Sat':<6} {'PR (Mm)':>10} {'Toe':>10} {'ToW':>10} {'dt':>10} {'GeomR (Mm)':>12} {'PR-Geom (km)':>14} {'El':>6}")
print("-" * 88)

rx, ry, rz = geodetic_to_ecef(ref["lat"], ref["lon"], ref["height"])

for sat in gps_sats:
    try:
        pr = float(obs.sel(sv=sat, time=epoch)["C1C"].values)
        if np.isnan(pr) or pr < 1e6:
            continue

        # Pass gps_time_of_week to select the closest ephemeris record
        ep_time, eph = get_first_valid_ephemeris(nav, sat, gps_time_of_week)
        toe          = float(eph.get("Toe", 0.0))
        travel_time  = pr / SPEED_OF_LIGHT

        # Robust transmit time alignment
        transmit_raw = gps_time_of_week - travel_time
        dt_raw       = transmit_raw - toe
        if dt_raw < -302400:
            transmit_time = transmit_raw + 604800.0
        elif dt_raw > 302400:
            transmit_time = transmit_raw - 604800.0
        else:
            transmit_time = transmit_raw

        x, y, z   = compute_satellite_position(eph, transmit_time_seconds=transmit_time)
        az, el, _ = compute_az_el(x, y, z, ref["lat"], ref["lon"], ref["height"])

        geom         = np.sqrt((x-rx)**2 + (y-ry)**2 + (z-rz)**2)
        diff         = (pr - geom) / 1000
        dt_effective = transmit_time - toe

        print(f"{str(sat):<6} {pr/1e6:>10.3f} {toe:>10.0f} {gps_time_of_week:>10.1f} "
              f"{dt_effective:>10.1f} {geom/1e6:>12.3f} {diff:>14.1f} {el:>6.1f}")

        pseudoranges[str(sat)]  = pr
        sat_positions[str(sat)] = (x, y, z)
        elevations[str(sat)]    = np.radians(el)
        azimuths[str(sat)]      = np.radians(az)
        ephemerides[str(sat)]   = eph

    except Exception as e:
        print(f"{str(sat):<6} ERROR: {e}")
        continue

print()
print(f"Satellites with valid data: {len(pseudoranges)}")
print()
print("Expected: Toe values close to 50400, dt values under 7200 s")
print("Expected: PR-Geom under 500 km")
print()

if len(pseudoranges) >= 4:
    toes = [float(ephemerides[s].get("Toe", 0.0)) for s in ephemerides]
    median_toe = float(np.median(toes))

    dt_check = gps_time_of_week - median_toe
    if dt_check < -302400:
        solver_gps_time = gps_time_of_week + 604800.0
    elif dt_check > 302400:
        solver_gps_time = gps_time_of_week - 604800.0
    else:
        solver_gps_time = gps_time_of_week

    print(f"Solver GPS time: {solver_gps_time:.1f}")
    print(f"Median Toe:      {median_toe:.1f}")
    print(f"dt to Toe:       {solver_gps_time - median_toe:.1f} s  (should be < 7200)")
    print()

    x0_xyz = geodetic_to_ecef(ref["lat"], ref["lon"], ref["height"])
    x0     = np.array([x0_xyz[0], x0_xyz[1], x0_xyz[2], 0.0])

    # Pass all required dicts correctly
    eccentric_anomalies = {sat: 0.0 for sat in pseudoranges}

    result = solve_spp_epoch(
        pseudoranges, sat_positions, ephemerides,
        eccentric_anomalies, elevations, azimuths,
        {},
        gps_time=solver_gps_time, x0=x0
    )

    if result["converged"]:
        print(f"Position fix obtained:")
        print(f"  lat={result['lat']:.6f}  lon={result['lon']:.6f}  h={result['height']:.1f} m")
        error = compute_position_error(
            result["lat"], result["lon"], result["height"],
            ref["lat"],    ref["lon"],    ref["height"]
        )
        print(f"  Horizontal error: {error['horizontal_m']:.1f} m")
        print(f"  Vertical error:   {error['vertical_m']:.1f} m")
        if error["horizontal_m"] < 500:
            print()
            print("PASS — midday positioning working correctly")
        else:
            print()
            print(f"Large error — residuals: {result.get('residuals', {})}")
    else:
        print(f"SPP did not converge. Satellites used: {result.get('n_sats_used', 0)}")
        print()
        print("Debugging — checking elevation mask:")
        for sat in pseudoranges:
            el_deg = np.degrees(elevations.get(sat, 0))
            print(f"  {sat}: elevation={el_deg:.1f} deg")
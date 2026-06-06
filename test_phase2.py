"""Quick Phase 2 integration test — run from project root."""
import math
import georinex as gr
import numpy as np
from src.gnss_pipeline.ephemeris import compute_satellite_position, get_first_valid_ephemeris
from src.gnss_pipeline.az_el import compute_az_el
from src.gnss_pipeline.spp_solver import solve_spp_epoch, geodetic_to_ecef, ecef_to_geodetic

# Constants
SPEED_OF_LIGHT = 299_792_458.0

# Load data for FRDN (Fredericton — your local station)
OBS_FILE = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx"
NAV_FILE = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_MN.rnx"

obs = gr.load(OBS_FILE, use="G", tlim=["2025-06-01T00:00:30", "2025-06-01T00:10:00"])
nav = gr.load(NAV_FILE, use="G")

# Get the first epoch
epoch = obs.time.values[0]
print(f"Processing epoch: {epoch}")

# Compute GPS time of week
gps_epoch = np.datetime64("1980-01-06T00:00:00", "s")
epoch_s = epoch.astype("datetime64[s]")
total_gps_seconds = float((epoch_s - gps_epoch).astype(float))
gps_week = int(total_gps_seconds // 604800)
gps_time_of_week = total_gps_seconds % 604800.0

print(f"Total GPS seconds: {total_gps_seconds:.1f}")
print(f"GPS week number:   {gps_week}")
print(f"GPS time of week:  {gps_time_of_week:.1f} s")

# Get all GPS satellites visible at this epoch
gps_sats = [s for s in obs.sv.values if str(s).startswith("G")]

pseudoranges        = {}
sat_positions       = {}
elevations          = {}
azimuths            = {}
ephemerides         = {}
eccentric_anomalies = {}

# Approximate FRDN position
approx_lat = 45.9455
approx_lon = -66.6443
approx_h   = 24.0

for sat in gps_sats:
    try:
        pr = float(obs.sel(sv=sat, time=epoch)["C1C"].values)
        if np.isnan(pr) or pr < 1e6:
            continue

        ep_time, eph = get_first_valid_ephemeris(nav, sat)
        toe = float(eph.get("Toe", 0.0))

        # Travel time correction
        travel_time = pr / SPEED_OF_LIGHT

        # Align transmit time to the same GPS week as Toe
        if toe > 302400 and gps_time_of_week < 302400:
            transmit_time = gps_time_of_week + 604800.0 - travel_time
        else:
            transmit_time = gps_time_of_week - travel_time

        x, y, z = compute_satellite_position(eph, transmit_time_seconds=transmit_time)
        az, el, _ = compute_az_el(x, y, z, approx_lat, approx_lon, approx_h)

        pseudoranges[str(sat)]        = pr
        sat_positions[str(sat)]       = (x, y, z)
        elevations[str(sat)]          = np.radians(el)
        azimuths[str(sat)]            = np.radians(az)
        ephemerides[str(sat)]         = eph
        eccentric_anomalies[str(sat)] = 0.0

    except Exception as e:
        print(f"  Skipping {sat}: {e}")
        continue

print(f"Satellites with valid data: {len(pseudoranges)}")

# Geometric range check — PR vs actual receiver-to-satellite distance
rx, ry, rz = geodetic_to_ecef(approx_lat, approx_lon, approx_h)
print(f"\nReceiver ECEF: X={rx:.0f} Y={ry:.0f} Z={rz:.0f}")
print(f"Geometric ranges from FRDN:")
for sat in list(pseudoranges.keys())[:4]:
    pr  = pseudoranges[sat]
    sp  = sat_positions[sat]
    geom = math.sqrt((sp[0]-rx)**2 + (sp[1]-ry)**2 + (sp[2]-rz)**2)
    diff = geom - pr
    print(f"  {sat}: PR={pr/1e6:.3f} Mm  Geom={geom/1e6:.3f} Mm  Diff={diff/1000:.1f} km")

# Clock timing debug
if ephemerides:
    first_sat = list(ephemerides.keys())[0]
    eph_sample = ephemerides[first_sat]
    toe = eph_sample.get("Toe", 0.0)
    if toe > 302400 and gps_time_of_week < 302400:
        effective_tow = gps_time_of_week + 604800.0
    else:
        effective_tow = gps_time_of_week
    dt = effective_tow - toe
    print(f"\nClock debug for {first_sat}:")
    print(f"  SVclockBias:    {eph_sample.get('SVclockBias'):.6e}")
    print(f"  Toe:            {toe:.1f} s")
    print(f"  Effective ToW:  {effective_tow:.1f} s")
    print(f"  dt (ToW-Toe):   {dt:.1f} s  (should be < 7200)")

# Roundtrip check
x0_xyz = geodetic_to_ecef(approx_lat, approx_lon, approx_h)
x0 = np.array([x0_xyz[0], x0_xyz[1], x0_xyz[2], 0.0])
lat_rt, lon_rt, h_rt = ecef_to_geodetic(x0[0], x0[1], x0[2])
print(f"\nRoundtrip geodetic check:")
print(f"  Input:  lat={approx_lat} lon={approx_lon} h={approx_h}")
print(f"  Output: lat={lat_rt:.4f} lon={lon_rt:.4f} h={h_rt:.2f}")

# Aligned GPS time for solver
if ephemerides:
    first_eph = list(ephemerides.values())[0]
    toe_first = float(first_eph.get("Toe", 0.0))
    if toe_first > 302400 and gps_time_of_week < 302400:
        solver_gps_time = gps_time_of_week + 604800.0
    else:
        solver_gps_time = gps_time_of_week
else:
    solver_gps_time = gps_time_of_week

print(f"\nPassing gps_time={solver_gps_time:.1f} to solver")

# Empty header — no ionospheric correction for first test
nav_header = {}

# Solve SPP
result = solve_spp_epoch(
    pseudoranges, sat_positions, ephemerides,
    eccentric_anomalies, elevations, azimuths,
    nav_header, gps_time=solver_gps_time,
    x0=x0
)

if result["converged"]:
    print(f"\nPosition fix obtained!")
    print(f"  Latitude:  {result['lat']:.6f} deg")
    print(f"  Longitude: {result['lon']:.6f} deg")
    print(f"  Height:    {result['height']:.2f} m")
    print(f"  Satellites used: {result['n_sats_used']}")
    print(f"\nExpected FRDN: {approx_lat:.4f}, {approx_lon:.4f}, {approx_h:.1f} m")
    print(f"  Lat error:    {abs(result['lat'] - approx_lat)*111000:.1f} m")
    print(f"  Lon error:    {abs(result['lon'] - approx_lon)*111000*np.cos(np.radians(approx_lat)):.1f} m")
    print(f"  Height error: {abs(result['height'] - approx_h):.1f} m")
else:
    print(f"\nSPP did not converge. Satellites used: {result.get('n_sats_used', 0)}")
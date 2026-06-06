"""
Ionospheric correction validation test — with correct ephemeris selection.
Compares SPP accuracy with and without Klobuchar correction
for midnight and midday sessions from the same FRDN data.
Run from project root.
"""
import georinex as gr
import numpy as np
from src.gnss_pipeline.ephemeris import compute_satellite_position, get_first_valid_ephemeris
from src.gnss_pipeline.az_el import compute_az_el
from src.gnss_pipeline.spp_solver import solve_spp_epoch, geodetic_to_ecef
from src.gnss_pipeline.accuracy import load_reference_coords, compute_position_error, compute_accuracy_statistics
from src.gnss_pipeline.nav_header_utils import get_nav_header
from src.gnss_pipeline.corrections import klobuchar_iono_correction

SPEED_OF_LIGHT = 299_792_458.0
OBS_FILE = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx"
NAV_FILE = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_MN.rnx"
REF_FILE = "data/reference/nrcan_reference_coords.json"

ref        = load_reference_coords(REF_FILE)["FRDN"]
nav_header = get_nav_header()
gps_epoch  = np.datetime64("1980-01-06T00:00:00", "s")

sessions = [
    {
        "label":      "Midnight (00:00-02:00 UTC)",
        "tlim_start": "2025-06-01T00:00:30",
        "tlim_end":   "2025-06-01T02:00:00",
    },
    {
        "label":      "Midday   (14:00-16:00 UTC)",
        "tlim_start": "2025-06-01T14:00:00",
        "tlim_end":   "2025-06-01T16:00:00",
    },
]


def process_epoch(obs, nav, epoch, use_iono: bool) -> dict:
    """Process a single epoch. Returns error dict or None if failed."""
    epoch_s           = epoch.astype("datetime64[s]")
    total_gps_seconds = float((epoch_s - gps_epoch).astype(float))
    gps_time_of_week  = total_gps_seconds % 604800.0

    gps_sats = [s for s in obs.sv.values if str(s).startswith("G")]

    pseudoranges        = {}
    sat_positions       = {}
    elevations          = {}
    azimuths            = {}
    ephemerides         = {}
    eccentric_anomalies = {}

    for sat in gps_sats:
        try:
            pr = float(obs.sel(sv=sat, time=epoch)["C1C"].values)
            if np.isnan(pr) or pr < 1e6:
                continue

            # Use closest ephemeris to observation time
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

            pseudoranges[str(sat)]        = pr
            sat_positions[str(sat)]       = (x, y, z)
            elevations[str(sat)]          = np.radians(el)
            azimuths[str(sat)]            = np.radians(az)
            ephemerides[str(sat)]         = eph
            eccentric_anomalies[str(sat)] = 0.0

        except Exception:
            continue

    if len(pseudoranges) < 4:
        return None

    toes = [float(ephemerides[s].get("Toe", 0.0)) for s in ephemerides]
    median_toe = float(np.median(toes))
    dt_check   = gps_time_of_week - median_toe
    if dt_check < -302400:
        solver_gps_time = gps_time_of_week + 604800.0
    elif dt_check > 302400:
        solver_gps_time = gps_time_of_week - 604800.0
    else:
        solver_gps_time = gps_time_of_week

    x0_xyz = geodetic_to_ecef(ref["lat"], ref["lon"], ref["height"])
    x0     = np.array([x0_xyz[0], x0_xyz[1], x0_xyz[2], 0.0])

    header = nav_header if use_iono else {}

    result = solve_spp_epoch(
        pseudoranges, sat_positions, ephemerides,
        eccentric_anomalies, elevations, azimuths,
        header, gps_time=solver_gps_time, x0=x0
    )

    if not result["converged"]:
        return None

    return compute_position_error(
        result["lat"], result["lon"], result["height"],
        ref["lat"],    ref["lon"],    ref["height"]
    )


def run_session(obs, nav, use_iono: bool) -> tuple:
    """Process all epochs in a session."""
    errors_h = []
    errors_v = []

    for epoch_idx, epoch in enumerate(obs.time.values):
        if epoch_idx % 30 == 0:
            print(f"    Epoch {epoch_idx+1}/{len(obs.time.values)}...", end="\r")
        error = process_epoch(obs, nav, epoch, use_iono)
        if error is not None:
            errors_h.append(error["horizontal_m"])
            errors_v.append(error["vertical_m"])

    return compute_accuracy_statistics(errors_h, errors_v), len(errors_h)


# Load nav once
print("Loading navigation file...")
nav = gr.load(NAV_FILE, use="G")
print()

print("GNSS Ionospheric Correction Validation")
print("=" * 72)
print(f"{'Session + metric':<40} {'No iono':>10} {'With iono':>10} {'Change':>10}")
print("-" * 72)

all_results = {}

for session in sessions:
    print(f"\nLoading {session['label']}...")
    obs = gr.load(
        OBS_FILE, use="G",
        tlim=[session["tlim_start"], session["tlim_end"]]
    )
    print(f"  Epochs loaded: {len(obs.time.values)}")

    # Sample iono correction for this session
    epoch_s = obs.time.values[0].astype("datetime64[s]")
    total   = float((epoch_s - gps_epoch).astype(float))
    tow     = total % 604800.0
    lat_r   = np.radians(ref["lat"])
    lon_r   = np.radians(ref["lon"])
    i_45    = klobuchar_iono_correction(nav_header, np.radians(45), np.radians(180), lat_r, lon_r, tow)
    i_20    = klobuchar_iono_correction(nav_header, np.radians(20), np.radians(180), lat_r, lon_r, tow)
    print(f"  Klobuchar correction: {i_45:.2f} m at 45 deg,  {i_20:.2f} m at 20 deg elevation")

    print(f"  Running without iono correction...")
    stats_no, n_no = run_session(obs, nav, use_iono=False)

    print(f"\n  Running with iono correction...")
    stats_wi, n_wi = run_session(obs, nav, use_iono=True)

    print(f"\n  Epochs processed: {n_no} (no iono)  {n_wi} (with iono)")

    all_results[session["label"]] = {
        "no_iono": stats_no,
        "with_iono": stats_wi,
        "n": n_wi,
        "iono_45": i_45,
        "iono_20": i_20,
    }

    for metric in ["CEP50", "CEP95", "RMSE_H", "RMSE_V"]:
        no_i  = stats_no.get(metric, float("nan"))
        w_i   = stats_wi.get(metric, float("nan"))
        chg   = w_i - no_i
        arrow = "↓" if chg < -0.5 else ("↑" if chg > 0.5 else " ")
        label = f"  {session['label']} — {metric}"
        print(f"{label:<40} {no_i:>8.1f} m  {w_i:>8.1f} m  {arrow}{abs(chg):>6.1f} m")

print()
print("=" * 72)
print()
print("Summary:")
for label, r in all_results.items():
    cep_no = r["no_iono"].get("CEP50", float("nan"))
    cep_wi = r["with_iono"].get("CEP50", float("nan"))
    improvement = (1 - cep_wi / cep_no) * 100 if cep_no > 0 else 0
    direction = "improvement" if improvement > 0 else "degradation"
    print(f"  {label}: CEP50 {cep_no:.1f} m → {cep_wi:.1f} m  "
          f"({abs(improvement):.1f}% {direction})")
    print(f"    Iono corrections: {r['iono_45']:.2f} m at 45 deg, "
          f"{r['iono_20']:.2f} m at 20 deg")
print()
print("Interpretation:")
print("  Larger iono corrections + larger improvement = model validated")
print("  Similar corrections at both sessions = ionosphere quiet all day")
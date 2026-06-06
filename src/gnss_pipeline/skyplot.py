from pathlib import Path
import warnings

import georinex as gr
import numpy as np
import matplotlib.pyplot as plt
import pymap3d as pm

warnings.filterwarnings("ignore", category=FutureWarning)


APPROX_RECEIVER_LAT = 45.9555
APPROX_RECEIVER_LON = -78.0714
APPROX_RECEIVER_HEIGHT = 200.0


def load_observation_file(obs_file_path: str):
    obs_path = Path(obs_file_path)

    if not obs_path.exists():
        raise FileNotFoundError(f"File not found: {obs_path}")

    print("Loading observation file...")

    obs = gr.load(
        obs_path,
        tlim=("2025-06-01T00:00:00", "2025-06-01T00:30:00")
    )

    print("Observation file loaded.")
    return obs


def make_demo_skyplot(obs):
    satellites = obs.sv.values
    times = obs.time.values

    print("\nSatellites:")
    print(satellites)

    print("\nEpoch count:")
    print(len(times))

    azimuths = []
    elevations = []
    labels = []

    for i, sv in enumerate(satellites):
        # TEMPORARY demo satellite tracks
        # Later we replace this with real ECEF positions from broadcast ephemeris.
        az = np.linspace(0, 360, len(times)) + i * 15
        az = az % 360

        el = 20 + 40 * np.sin(np.linspace(0, np.pi, len(times)) + i * 0.2)

        azimuths.append(az)
        elevations.append(el)
        labels.append(str(sv))

    fig = plt.figure(figsize=(8, 8))
    ax = plt.subplot(111, polar=True)

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    ax.set_rlim(90, 0)
    ax.set_yticks([0, 30, 60, 90])
    ax.set_yticklabels(["90°", "60°", "30°", "0°"])

    for az, el, label in zip(azimuths, elevations, labels):
        r = 90 - el
        theta = np.deg2rad(az)
        ax.plot(theta, r, marker="o", label=label)

    ax.set_title("Static Sky Plot - Demo Satellite Tracks")
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=8)

    output_path = Path("outputs/plots/skyplot_demo.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"\nSky plot saved to: {output_path}")


if __name__ == "__main__":
    obs_file = "data/raw/extracted/ALGO00CAN_R_20251520000_01D_30S_MO.rnx"
    obs = load_observation_file(obs_file)
    make_demo_skyplot(obs)
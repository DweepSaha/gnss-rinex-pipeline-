from pathlib import Path
import warnings
import georinex as gr

warnings.filterwarnings("ignore", category=FutureWarning)


def parse_observation_file(obs_file_path: str) -> None:
    obs_path = Path(obs_file_path)

    if not obs_path.exists():
        raise FileNotFoundError(f"File not found: {obs_path}")

    print("Loading RINEX observation file...")
    obs = gr.load(
    obs_path,
    tlim=("2025-06-01T00:00:00", "2025-06-01T00:10:00")
)

    print("\nRINEX file loaded successfully.")
    print("\nObservation types:")
    print(list(obs.data_vars))

    print("\nSatellite list:")
    print(obs.sv.values)

    print("\nEpoch count:")
    print(len(obs.time.values))

    print("\nFirst epoch:")
    print(obs.time.values[0])

    print("\nLast epoch:")
    print(obs.time.values[-1])


if __name__ == "__main__":
    observation_file = "data/raw/extracted/ALGO00CAN_R_20251520000_01D_30S_MO.rnx"
    parse_observation_file(observation_file)
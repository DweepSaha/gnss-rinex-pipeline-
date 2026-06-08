"""
Check what observation types the JPL file contains.
"""
import georinex as gr
import numpy as np

OBS_FILE = "data/raw/extracted/jplm1750.21o"

print("Loading JPL observation file...")
obs = gr.load(OBS_FILE, use="G", tlim=["2021-06-24T00:00:00", "2021-06-24T00:10:00"])

print(f"Observation types: {list(obs.data_vars)}")
print(f"Satellites: {list(obs.sv.values)}")
print(f"Epochs: {len(obs.time.values)}")
print()

# Check first epoch for any satellite
sat = str(obs.sv.values[0])
epoch = obs.time.values[0]
print(f"Sample data for {sat} at first epoch:")
for var in obs.data_vars:
    try:
        val = float(obs.sel(sv=sat, time=epoch)[var].values)
        if not np.isnan(val):
            print(f"  {var}: {val:.3f}")
    except Exception:
        pass
import georinex as gr
from pathlib import Path

nav_files = list(Path("data/raw/extracted").glob("*MN.rnx"))

for nav_file in nav_files:
    print(f"\nChecking: {nav_file.name}")
    try:
        nav = gr.load(str(nav_file), use='G')
        print(f"  Header keys: {list(nav.attrs.keys())}")
        if 'GPSA' in nav.attrs:
            print(f"  GPSA: {nav.attrs['GPSA']}")
        else:
            print(f"  GPSA: not found")
        if 'GPSB' in nav.attrs:
            print(f"  GPSB: {nav.attrs['GPSB']}")
        else:
            print(f"  GPSB: not found")
    except Exception as e:
        print(f"  Error: {e}")
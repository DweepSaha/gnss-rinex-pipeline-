import georinex as gr
obs = gr.load(
    'data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx',
    use='G',
    tlim=['2025-06-01T00:00:30', '2025-06-01T00:10:00']
)
print('Observation types:', list(obs.data_vars))
import numpy as np


def compute_dop(H: np.ndarray) -> dict:
    """
    Compute Dilution of Precision values from the design matrix H.

    H is an (n x 4) matrix where each row is [-lx, -ly, -lz, 1]
    for each satellite used in the solution.

    Returns dict with GDOP, PDOP, HDOP, VDOP.
    HDOP and VDOP are computed in ECEF, which is an approximation.
    They are correct enough for quality reporting at this stage.
    """
    if H is None or H.shape[0] < 4:
        return {"GDOP": np.nan, "PDOP": np.nan, "HDOP": np.nan, "VDOP": np.nan}

    try:
        HtH = H.T @ H
        Q = np.linalg.inv(HtH)
    except np.linalg.LinAlgError:
        return {"GDOP": np.nan, "PDOP": np.nan, "HDOP": np.nan, "VDOP": np.nan}

    # Diagonal elements of Q correspond to variance of each unknown
    # Q[0,0] = X variance, Q[1,1] = Y variance, Q[2,2] = Z variance, Q[3,3] = clock variance
    GDOP = np.sqrt(abs(Q[0,0] + Q[1,1] + Q[2,2] + Q[3,3]))
    PDOP = np.sqrt(abs(Q[0,0] + Q[1,1] + Q[2,2]))
    HDOP = np.sqrt(abs(Q[0,0] + Q[1,1]))
    VDOP = np.sqrt(abs(Q[2,2]))

    return {
        "GDOP": round(GDOP, 3),
        "PDOP": round(PDOP, 3),
        "HDOP": round(HDOP, 3),
        "VDOP": round(VDOP, 3),
    }
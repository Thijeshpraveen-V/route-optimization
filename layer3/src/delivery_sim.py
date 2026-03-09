# Simulates actual delivery outcomes with systematic + random noise
# The systematic delays are the "hidden truth" the learner must discover

import random
from layer3.src.eta_learner import get_time_band

# Ground truth: segments always slower than OSRM predicts
# These represent real Bengaluru patterns — Hosur Rd, ORR, Whitefield
SYSTEMATIC_DELAYS = {
    # Hosur Road corridor — always 40-55% slower in morning
    (0,  9):  1.45,   (9,  0):  1.40,
    (0, 10):  1.55,   (10, 0):  1.50,
    (9, 10):  1.40,   (10, 9):  1.35,
    (10, 11): 1.25,   (11, 10): 1.20,
    (11, 12): 1.20,   (12, 11): 1.15,
    (4,  9):  1.30,   (9,  4):  1.25,
    # Whitefield corridor — 30-35% slower
    (0, 14):  1.35,   (14, 0):  1.30,
    (7, 14):  1.30,   (14, 7):  1.25,
    # Indiranagar — moderate 10-15%
    (0, 13):  1.15,   (13, 0):  1.10,
}


def simulate_actual_times(routes: list,
                           base_time_matrix: list,
                           seed: int = None) -> list:
    """
    Simulates real delivery times for a set of routes.

    For each road segment traversed:
      actual_time = base_time × systematic_factor × random_noise

    systematic_factor: known only to the simulator (what learner discovers)
    random_noise:      gaussian ±8% (irreducible randomness)

    Returns observations list ready for ETALearner.record_observations()
    """
    if seed is not None:
        random.seed(seed)

    observations = []

    for r in routes:
        if "route_wt" in r:
            nodes = [n for n, _ in r["route_wt"]]
        elif "route_nodes" in r:
            nodes = r["route_nodes"]
        else:
            nodes = r.get("route", [0])

        cur_min = 0
        prev    = 0

        for node in nodes[1:]:
            base_s = base_time_matrix[prev][node]
            if base_s <= 0:
                prev = node
                continue

            sys_f = SYSTEMATIC_DELAYS.get((prev, node), 1.0)
            noise = random.gauss(1.0, 0.08)
            noise = max(0.85, min(1.15, noise))

            actual_s = int(base_s * sys_f * noise)
            band     = get_time_band(cur_min)

            observations.append({
                "from_node":   prev,
                "to_node":     node,
                "time_band":   band,
                "base_pred_s": base_s,
                "actual_s":    actual_s,
                "sys_factor":  sys_f,
                "noise":       round(noise, 3),
            })

            cur_min += actual_s // 60
            prev     = node

    return observations

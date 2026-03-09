"""module2/src/naive_solver_m2.py — Siloed fleets: 1 vehicle per order, no sharing."""
from module2.data.network_m2 import ALL_LOCS_M2, ORDERS_M2


def solve_naive_m2(dist, time_):
    """
    Completely siloed approach (no AI):
    - 14 dedicated delivery vehicles (one per delivery order)
    - 3 dedicated pickup vehicles (one per return order)
    Neither fleet shares routes or capacity.
    """
    routes   = []
    total_d  = 0
    total_t  = 0
    n_del    = 0
    n_pick   = 0

    for i, order in enumerate(ORDERS_M2):
        _, stop_id, stop_type, demand, tw_s, tw_e, priority = order
        rd = dist[0][stop_id] + dist[stop_id][0]
        rt = time_[0][stop_id] + time_[stop_id][0]
        routes.append({
            "vehicle":   f"V{i+1:02d}",
            "route":     [0, stop_id, 0],
            "stop_type": stop_type,
            "demand":    demand,
            "dist_m":    rd,
            "time_s":    rt,
        })
        total_d += rd
        total_t += rt
        if stop_type == "DELIVERY":
            n_del += 1
        else:
            n_pick += 1

    return {
        "routes":            routes,
        "total_km":          total_d / 1000,
        "total_min":         total_t / 60,
        "n_veh":             len(routes),
        "delivery_vehicles": n_del,
        "pickup_vehicles":   n_pick,
    }

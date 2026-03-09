from layer1.data.network import ALL_LOCS, ORDERS, VEHICLES


def solve_naive(dist, time_):
    """
    ONE VEHICLE PER ORDER — the real baseline.

    This is how logistics companies operate without AI route optimisation:
    each shipment is assigned its own dedicated delivery vehicle.
    It is the most honest comparison because:
      - Companies without batching intelligence literally dispatch N agents
        for N orders (confirmed by Swiggy/Zomato pre-batching era)
      - Shows the full fleet savings possible with AI

    Does NOT respect time windows — delivers on arrival regardless of window.
    """
    routes  = []
    total_d = 0
    total_t = 0

    for i, order in enumerate(ORDERS):
        stop_id = order[1]
        rd = dist[0][stop_id] + dist[stop_id][0]    # depot → stop → depot
        rt = time_[0][stop_id] + time_[stop_id][0]

        routes.append({
            "vehicle": f"V{i+1:02d}",
            "route":   [0, stop_id, 0],
            "dist_m":  rd,
            "time_s":  rt,
        })
        total_d += rd
        total_t += rt

    return {
        "routes":    routes,
        "total_km":  total_d / 1000,
        "total_min": total_t / 60,
        "n_veh":     len(routes),
    }

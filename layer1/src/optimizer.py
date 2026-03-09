from ortools.constraint_solver import routing_enums_pb2, pywrapcp
from layer1.data.network import ALL_LOCS, ORDERS, VEHICLES, PRIORITY_PENALTY_PER_MIN


def solve_vrptw(dist, time_):
    """
    OR-Tools VRPTW solver with:
      - Soft time windows  (late delivery penalised, not forbidden)
      - Vehicle capacity   (demand units per vehicle)
      - Shipment priority  (penalty scales with HIGH/MEDIUM/LOW)
      - Minimise total distance (arc cost) + SLA breach penalties
    """
    n_locs = len(ALL_LOCS)
    n_veh  = len(VEHICLES)
    depot  = 0

    manager = pywrapcp.RoutingIndexManager(n_locs, n_veh, depot)
    routing = pywrapcp.RoutingModel(manager)

    # ── Arc cost: distance (meters) ───────────────────────────────────
    def dist_cb(fi, ti):
        return dist[manager.IndexToNode(fi)][manager.IndexToNode(ti)]

    def time_cb(fi, ti):
        return time_[manager.IndexToNode(fi)][manager.IndexToNode(ti)]

    dist_transit = routing.RegisterTransitCallback(dist_cb)
    time_transit = routing.RegisterTransitCallback(time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(dist_transit)

    # ── Time dimension ────────────────────────────────────────────────
    # slack_max=7200s (2h wait allowed), max_route=36000s (10h), start_at_zero=True
    routing.AddDimension(time_transit, 7200, 36000, True, "Time")
    td = routing.GetDimensionOrDie("Time")

    # Lookup dicts: node_id → (tw_start_sec, tw_end_sec) and priority
    tw_map  = {o[1]: (o[4]*60, o[5]*60) for o in ORDERS}
    pri_map = {o[1]: o[2]               for o in ORDERS}

    # Apply soft time windows with priority-scaled penalties
    for node in range(1, n_locs):
        if node not in tw_map:
            continue
        idx      = manager.NodeToIndex(node)
        tw_s, tw_e = tw_map[node]
        # penalty = ₹/sec late → convert from ₹/min, minimum 1
        pen_per_sec = max(1, PRIORITY_PENALTY_PER_MIN[pri_map[node]] // 60)

        td.CumulVar(idx).SetMin(tw_s)                      # earliest arrival
        td.SetCumulVarSoftUpperBound(idx, tw_e, pen_per_sec) # soft latest

    # Encourage minimising end time across all vehicles
    for v in range(n_veh):
        routing.AddVariableMinimizedByFinalizer(td.CumulVar(routing.End(v)))

    # ── Capacity dimension ────────────────────────────────────────────
    dem_map = {o[1]: o[3] for o in ORDERS}

    def demand_cb(fi):
        return dem_map.get(manager.IndexToNode(fi), 0)

    dem_transit = routing.RegisterUnaryTransitCallback(demand_cb)
    capacities  = [v[1] for v in VEHICLES]
    routing.AddDimensionWithVehicleCapacity(
        dem_transit, 0, capacities, True, "Capacity"
    )

    # ── Search strategy ───────────────────────────────────────────────
    prm = pywrapcp.DefaultRoutingSearchParameters()
    prm.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    prm.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    prm.time_limit.seconds = 20

    solution = routing.SolveWithParameters(prm)
    if not solution:
        return None

    # ── Extract routes ────────────────────────────────────────────────
    routes  = []
    total_d = 0
    total_t = 0

    for v in range(n_veh):
        if not routing.IsVehicleUsed(solution, v):
            continue

        route_wt = []    # [(node_id, arrival_sec), ...]
        rd = 0
        rt = 0
        idx = routing.Start(v)

        while not routing.IsEnd(idx):
            node  = manager.IndexToNode(idx)
            t_arr = solution.Min(td.CumulVar(idx))
            route_wt.append((node, t_arr))
            nxt   = solution.Value(routing.NextVar(idx))
            rd   += dist[node][manager.IndexToNode(nxt)]
            rt   += time_[node][manager.IndexToNode(nxt)]
            idx   = nxt

        # depot end
        route_wt.append((manager.IndexToNode(idx),
                          solution.Min(td.CumulVar(idx))))
        total_d += rd
        total_t += rt

        routes.append({
            "vehicle":  VEHICLES[v][0],
            "route_wt": route_wt,    # node + arrival times from solver
            "dist_m":   rd,
            "time_s":   rt,
        })

    return {
        "routes":    routes,
        "total_km":  total_d / 1000,
        "total_min": total_t / 60,
        "n_veh":     len(routes),
    }

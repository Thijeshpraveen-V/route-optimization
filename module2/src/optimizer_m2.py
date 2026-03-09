"""module2/src/optimizer_m2.py — Unified VRPTW combining deliveries + return pickups."""
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
from module2.data.network_m2 import (
    ALL_LOCS_M2, ORDERS_M2, VEHICLES_M2, PRIORITY_PENALTY_M2
)

TYPE_MAP_M2 = {loc[0]: loc[5] for loc in ALL_LOCS_M2}


def solve_vrptw_m2(dist, time_):
    """
    Single unified fleet handles BOTH deliveries AND return pickups.

    OR-Tools treats all stops (delivery + pickup) as demand nodes.
    Capacity constraint forces the solver to mix stops intelligently:
    vehicles drop packages and immediately use freed space for returns.

    This is how Flipkart/Amazon real-world reverse logistics works.
    """
    n     = len(ALL_LOCS_M2)      # 18 nodes (depot + 14 delivery + 3 pickup)
    n_veh = len(VEHICLES_M2)
    depot = 0

    manager = pywrapcp.RoutingIndexManager(n, n_veh, depot)
    routing = pywrapcp.RoutingModel(manager)

    # ── Arc cost (distance) ───────────────────────────────────────────────────
    def dist_cb(fi, ti):
        return dist[manager.IndexToNode(fi)][manager.IndexToNode(ti)]

    def time_cb(fi, ti):
        return time_[manager.IndexToNode(fi)][manager.IndexToNode(ti)]

    dist_tr = routing.RegisterTransitCallback(dist_cb)
    time_tr = routing.RegisterTransitCallback(time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(dist_tr)

    # ── Time dimension with soft time windows ─────────────────────────────────
    routing.AddDimension(time_tr, 7_200, 36_000, True, "Time")
    td     = routing.GetDimensionOrDie("Time")
    tw_map = {o[1]: (o[4] * 60, o[5] * 60) for o in ORDERS_M2}
    pr_map = {o[1]: o[6] for o in ORDERS_M2}

    for node in range(1, n):
        if node not in tw_map:
            continue
        idx        = manager.NodeToIndex(node)
        tw_s, tw_e = tw_map[node]
        pen        = max(1, PRIORITY_PENALTY_M2[pr_map[node]] // 60)
        td.CumulVar(idx).SetMin(tw_s)
        td.SetCumulVarSoftUpperBound(idx, tw_e, pen)

    for v in range(n_veh):
        routing.AddVariableMinimizedByFinalizer(td.CumulVar(routing.End(v)))

    # ── Capacity dimension ──────────────────────────────────────────────────
    # Both delivery and pickup demand units consume vehicle capacity.
    # The solver will naturally balance loads across the mixed route.
    dem_map = {o[1]: o[3] for o in ORDERS_M2}

    def demand_cb(fi):
        return dem_map.get(manager.IndexToNode(fi), 0)

    dem_tr = routing.RegisterUnaryTransitCallback(demand_cb)
    caps   = [v[1] for v in VEHICLES_M2]
    routing.AddDimensionWithVehicleCapacity(dem_tr, 0, caps, True, "Capacity")

    # ── Search parameters ─────────────────────────────────────────────────────
    prm = pywrapcp.DefaultRoutingSearchParameters()
    prm.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
    prm.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    prm.time_limit.seconds = 25

    sol = routing.SolveWithParameters(prm)
    if not sol:
        return None

    # ── Extract solution ──────────────────────────────────────────────────────
    routes  = []
    total_d = 0
    total_t = 0

    for v in range(n_veh):
        if not routing.IsVehicleUsed(sol, v):
            continue
        route_wt = []
        rd = rt  = 0
        idx = routing.Start(v)

        while not routing.IsEnd(idx):
            node  = manager.IndexToNode(idx)
            t_arr = sol.Min(td.CumulVar(idx))
            route_wt.append((node, t_arr))
            nxt  = sol.Value(routing.NextVar(idx))
            rd  += dist[node][manager.IndexToNode(nxt)]
            rt  += time_[node][manager.IndexToNode(nxt)]
            idx  = nxt

        route_wt.append((manager.IndexToNode(idx), sol.Min(td.CumulVar(idx))))
        total_d += rd
        total_t += rt

        stops_on = [n for n, _ in route_wt if n != 0]
        n_del    = sum(1 for n in stops_on if TYPE_MAP_M2.get(n) == "DELIVERY")
        n_pick   = sum(1 for n in stops_on if TYPE_MAP_M2.get(n) == "PICKUP")

        routes.append({
            "vehicle":      VEHICLES_M2[v][0],
            "route_wt":     route_wt,
            "dist_m":       rd,
            "time_s":       rt,
            "n_deliveries": n_del,
            "n_pickups":    n_pick,
        })

    return {
        "routes":    routes,
        "total_km":  total_d / 1000,
        "total_min": total_t / 60,
        "n_veh":     len(routes),
    }

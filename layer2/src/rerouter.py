# layer2/src/rerouter.py
# Delay detector + re-optimization trigger

from layer1.data.network     import ALL_LOCS, ORDERS, VEHICLES, PRIORITY_PENALTY_PER_MIN
from layer1.src.optimizer    import solve_vrptw

TW_MAP  = {o[1]: (o[4]*60, o[5]*60) for o in ORDERS}   # seconds
PRI_MAP = {o[1]: o[2]               for o in ORDERS}
REROUTE_THRESHOLD_SEC = 15 * 60    # 15-minute delay triggers rerouting


def simulate_route(route_nodes: list, time_matrix: list,
                   tw_map: dict) -> list:
    """
    Simulates a vehicle driving a given route with a (possibly congested)
    time matrix. Returns stop-level detail including arrival, SLA status,
    delay vs window.
    """
    results = []
    cur_t   = 0
    prev    = 0

    for node in route_nodes[1:]:           # skip depot at start
        cur_t += time_matrix[prev][node]

        if node == 0:                      # returning to depot
            results.append({
                "node": node, "name": "Depot",
                "arrival_s": cur_t, "arrival_min": round(cur_t/60, 1),
                "sla": "DEPOT", "delay_s": 0,
            })
            break

        tw_s, tw_e = tw_map.get(node, (0, 9999999))
        priority   = PRI_MAP.get(node, "LOW")

        # Vehicle waits if it arrives before window opens
        if cur_t < tw_s:
            cur_t = tw_s

        if cur_t <= tw_e:
            sla    = "ON_TIME"
            delay  = 0
        else:
            sla    = "BREACH"
            delay  = cur_t - tw_e          # seconds over window

        results.append({
            "node":        node,
            "name":        ALL_LOCS[node][1],
            "priority":    priority,
            "tw_start_m":  tw_s // 60,
            "tw_end_m":    tw_e // 60,
            "arrival_s":   cur_t,
            "arrival_min": round(cur_t / 60, 1),
            "sla":         sla,
            "delay_s":     delay,
            "delay_min":   round(delay / 60, 1),
        })
        prev = node

    return results


def run_scenario_b(optimized_routes: list, congested_time: list) -> dict:
    """
    Scenario B: Vehicles follow the ORIGINAL optimized routes
    but travel times are now congested. No rerouting.
    This is the 'naive response' — dispatcher ignores traffic alerts.
    """
    all_stops    = []
    total_time_s = 0
    on_time      = 0
    breaches     = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    routes_detail = []
    for r in optimized_routes:
        nodes  = [n for n, _ in r["route_wt"]]
        stops  = simulate_route(nodes, congested_time, TW_MAP)

        for s in stops:
            if s["sla"] == "DEPOT":
                total_time_s += s["arrival_s"]
                continue
            all_stops.append(s)
            if s["sla"] == "ON_TIME":
                on_time += 1
            else:
                breaches[s["priority"]] += 1

        routes_detail.append({
            "vehicle":     r["vehicle"],
            "stops":       stops,
            "dist_m":      r["dist_m"],
            "route_nodes": nodes,          # ← for map polylines
        })

    total   = len(all_stops)
    sla_pct = round(100 * on_time / total, 1) if total else 0

    return {
        "scenario":     "B",
        "label":        "Original Routes — No Rerouting",
        "routes":       routes_detail,
        "total_time_s": total_time_s,
        "total_time_min": round(total_time_s / 60, 1),
        "sla_pct":      sla_pct,
        "on_time":      on_time,
        "total_stops":  total,
        "breaches":     breaches,
        "rerouted":     False,
    }


def run_scenario_c(dist_matrix: list, congested_time: list) -> dict:
    """
    Scenario C: Re-run OR-Tools VRPTW with the congested time matrix.
    This is the AI response — full re-optimization under traffic.
    """
    data_override = {
        "time_matrix_override": congested_time,
    }
    # Solve with congested times
    opt = solve_vrptw(dist_matrix, congested_time)
    if not opt:
        return None

    # Simulate to get SLA status
    all_stops    = []
    total_time_s = 0
    on_time      = 0
    breaches     = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    routes_detail = []
    for r in opt["routes"]:
        nodes = [n for n, _ in r["route_wt"]]
        stops = simulate_route(nodes, congested_time, TW_MAP)

        for s in stops:
            if s["sla"] == "DEPOT":
                total_time_s += s["arrival_s"]
                continue
            all_stops.append(s)
            if s["sla"] == "ON_TIME":
                on_time += 1
            else:
                breaches[s["priority"]] += 1

        routes_detail.append({
            "vehicle":     r["vehicle"],
            "stops":       stops,
            "dist_m":      r["dist_m"],
            "time_s":      r["time_s"],
            "route_nodes": nodes,          # ← for map polylines
        })

    total   = len(all_stops)
    sla_pct = round(100 * on_time / total, 1) if total else 0

    return {
        "scenario":       "C",
        "label":          "AI Re-Optimized — Traffic Aware",
        "routes":         routes_detail,
        "opt_result":     opt,
        "total_time_s":   total_time_s,
        "total_time_min": round(total_time_s / 60, 1),
        "sla_pct":        sla_pct,
        "on_time":        on_time,
        "total_stops":    total,
        "breaches":       breaches,
        "rerouted":       True,
        "vehicles_used":  opt["n_veh"],
    }


def detect_congested_segments(multiplier_matrix: list,
                               threshold: float = 1.5) -> list:
    """Returns list of (from_node, to_node, multiplier) for congested segments."""
    n = len(multiplier_matrix)
    hot = []
    for i in range(n):
        for j in range(n):
            if i != j and multiplier_matrix[i][j] >= threshold:
                hot.append({
                    "from_node":  i,
                    "to_node":    j,
                    "from_name":  ALL_LOCS[i][1],
                    "to_name":    ALL_LOCS[j][1],
                    "multiplier": round(multiplier_matrix[i][j], 2),
                    "severity":   (
                        "🔴 SEVERE" if multiplier_matrix[i][j] >= 2.5 else
                        "🟠 HEAVY"  if multiplier_matrix[i][j] >= 1.8 else
                        "🟡 MODERATE"
                    ),
                })
    # Sort by severity descending
    return sorted(hot, key=lambda x: -x["multiplier"])

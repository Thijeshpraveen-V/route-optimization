# layer2/src/scenario_runner.py
# Three meaningful scenarios for judges:
#   A = NAIVE (no AI, no traffic) — how logistics works today
#   B = AI OPTIMIZED (no traffic) — what AI delivers on a normal day
#   C = AI + TRAFFIC AWARE — AI staying resilient when congestion hits

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from layer1.src.naive_solver    import solve_naive
from layer1.src.optimizer       import solve_vrptw
from layer1.data.network        import ALL_LOCS, ORDERS, COST_PER_KM
from layer2.src.traffic_engine  import (
    TRAFFIC_EVENTS, apply_combined_events, get_segment_multipliers
)
from layer2.src.rerouter        import simulate_route, detect_congested_segments, TW_MAP

PRI_MAP = {o[1]: o[2] for o in ORDERS}


def _extract_nodes(result, use_route_wt=True):
    """Pull node lists from solver output."""
    out = []
    for r in result["routes"]:
        if use_route_wt and "route_wt" in r:
            nodes = [n for n, _ in r["route_wt"]]
        elif "route" in r:
            nodes = r["route"]
        else:
            nodes = []
        out.append({
            "vehicle":     r.get("vehicle", "V"),
            "route_nodes": nodes,
            "dist_m":      r.get("dist_m", 0),
            "time_s":      r.get("time_s", 0),
        })
    return out


def _simulate_and_score(routes_detail, time_matrix):
    """Run simulate_route on each vehicle and collect SLA metrics."""
    all_stops    = []
    total_time_s = 0
    on_time      = 0
    breaches     = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    final_routes = []

    for r in routes_detail:
        nodes = r["route_nodes"]
        stops = simulate_route(nodes, time_matrix, TW_MAP)
        for s in stops:
            if s["sla"] == "DEPOT":
                total_time_s += s["arrival_s"]
                continue
            all_stops.append(s)
            if s["sla"] == "ON_TIME":
                on_time += 1
            else:
                breaches[s["priority"]] += 1
        final_routes.append({**r, "stops": stops})

    total   = len(all_stops)
    sla_pct = round(100 * on_time / total, 1) if total else 0
    return final_routes, total_time_s, sla_pct, on_time, total, breaches


def run_all_scenarios(dist_matrix, base_time_matrix, selected_event_ids):
    """
    Three scenarios that tell a clear story:

    A — NAIVE (no AI, no traffic)
        One truck per order, greedy NN, ignores time windows.
        Represents 'how logistics works today without AI.'

    B — AI OPTIMIZED (normal traffic, no congestion)
        OR-Tools VRPTW on clean road times.
        Represents 'what AI delivers on a normal day.'

    C — AI TRAFFIC-AWARE (congested time matrix)
        OR-Tools VRPTW re-solved with congested times.
        Represents 'AI staying resilient when traffic hits.'

    A → B  dramatic fleet + SLA improvement (baseline AI value)
    B → C  route changes under congestion (real-time intelligence)
    A → C  overall AI value even under real-world traffic
    """
    # ── Build congested matrix ────────────────────────────────────────────────
    congested_time = apply_combined_events(base_time_matrix, selected_event_ids)
    multiplier_mtx = get_segment_multipliers(selected_event_ids, len(dist_matrix))
    congested_segs = detect_congested_segments(multiplier_mtx, threshold=1.5)

    # ── Scenario A: Naive baseline, no traffic ────────────────────────────────
    naive = solve_naive(dist_matrix, base_time_matrix)
    a_routes = _extract_nodes(naive, use_route_wt=False)
    a_final, a_tot_s, a_sla, a_on, a_total, a_br = _simulate_and_score(
        a_routes, base_time_matrix
    )
    scenario_a = {
        "scenario":       "A",
        "label":          "Naive — No AI, Normal Roads",
        "routes":         a_final,
        "total_km":       naive["total_km"],
        "total_time_min": round(a_tot_s / 60, 1),
        "sla_pct":        a_sla,
        "on_time":        a_on,
        "total_stops":    a_total,
        "breaches":       a_br,
        "vehicles_used":  naive["n_veh"],
    }

    # ── Scenario B: AI optimized, no traffic ──────────────────────────────────
    opt_base = solve_vrptw(dist_matrix, base_time_matrix)
    b_routes = _extract_nodes(opt_base, use_route_wt=True)
    b_final, b_tot_s, b_sla, b_on, b_total, b_br = _simulate_and_score(
        b_routes, base_time_matrix
    )
    scenario_b = {
        "scenario":       "B",
        "label":          "AI Optimized — Normal Roads",
        "routes":         b_final,
        "total_km":       opt_base["total_km"],
        "total_time_min": round(b_tot_s / 60, 1),
        "sla_pct":        b_sla,
        "on_time":        b_on,
        "total_stops":    b_total,
        "breaches":       b_br,
        "vehicles_used":  opt_base["n_veh"],
    }

    # ── Scenario C: AI re-solved with congested times ─────────────────────────
    opt_cong = solve_vrptw(dist_matrix, congested_time)
    c_routes = _extract_nodes(opt_cong, use_route_wt=True)
    c_final, c_tot_s, c_sla, c_on, c_total, c_br = _simulate_and_score(
        c_routes, congested_time
    )
    scenario_c = {
        "scenario":       "C",
        "label":          "AI Traffic-Aware — Rerouted",
        "routes":         c_final,
        "total_km":       opt_cong["total_km"],
        "total_time_min": round(c_tot_s / 60, 1),
        "sla_pct":        c_sla,
        "on_time":        c_on,
        "total_stops":    c_total,
        "breaches":       c_br,
        "vehicles_used":  opt_cong["n_veh"],
    }

    # ── Stops saved vs naive ──────────────────────────────────────────────────
    a_breach_nodes = {s["node"] for r in a_final for s in r["stops"] if s["sla"] == "BREACH"}
    c_breach_nodes = {s["node"] for r in c_final for s in r["stops"] if s["sla"] == "BREACH"}
    stops_saved = [ALL_LOCS[n][1] for n in (a_breach_nodes - c_breach_nodes)]

    delay_saved_c_vs_b = round(scenario_b["total_time_min"] - scenario_c["total_time_min"], 1)

    comparison = {
        "vehicles":       [scenario_a["vehicles_used"], scenario_b["vehicles_used"], scenario_c["vehicles_used"]],
        "sla_pct":        [scenario_a["sla_pct"],       scenario_b["sla_pct"],       scenario_c["sla_pct"]],
        "total_time_min": [scenario_a["total_time_min"],scenario_b["total_time_min"],scenario_c["total_time_min"]],
        "total_km":       [scenario_a["total_km"],      scenario_b["total_km"],      scenario_c["total_km"]],
        "cost":           [round(scenario_a["total_km"] * COST_PER_KM),
                           round(scenario_b["total_km"] * COST_PER_KM),
                           round(scenario_c["total_km"] * COST_PER_KM)],
        "high_breach":    [scenario_a["breaches"]["HIGH"],
                           scenario_b["breaches"]["HIGH"],
                           scenario_c["breaches"]["HIGH"]],
        "stops_saved_by_rerouting": stops_saved,
        "delay_b_vs_a":      round(scenario_b["total_time_min"] - scenario_a["total_time_min"], 1),
        "delay_c_vs_a":      round(scenario_c["total_time_min"] - scenario_a["total_time_min"], 1),
        "delay_saved_c_vs_b": delay_saved_c_vs_b,
    }

    return {
        "scenario_a":     scenario_a,
        "scenario_b":     scenario_b,
        "scenario_c":     scenario_c,
        "comparison":     comparison,
        "congested_segs": congested_segs,
        "multiplier_mtx": multiplier_mtx,
        "congested_time": congested_time,
        "active_events":  [e for e in TRAFFIC_EVENTS if e["id"] in selected_event_ids],
    }

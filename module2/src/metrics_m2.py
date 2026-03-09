"""module2/src/metrics_m2.py — SLA computation split by delivery vs pickup type."""
from module2.data.network_m2 import ALL_LOCS_M2, ORDERS_M2, COST_PER_KM_M2

TW_MAP_M2  = {o[1]: (o[4] * 60, o[5] * 60) for o in ORDERS_M2}
PRI_MAP_M2 = {o[1]: o[6]                    for o in ORDERS_M2}
TYPE_MAP_M2 = {loc[0]: loc[5]               for loc in ALL_LOCS_M2}


def compute_sla_m2(result, time_, use_solver_times=False):
    """Compute SLA metrics split by stop type (DELIVERY vs PICKUP)."""
    on_time  = 0
    total    = 0
    breaches = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    type_sla = {
        "DELIVERY": {"on": 0, "total": 0},
        "PICKUP":   {"on": 0, "total": 0},
    }

    for r in result["routes"]:
        if use_solver_times:
            # Optimized routes: use solver arrival times stored in route_wt
            for node, arr_s in r["route_wt"]:
                if node == 0:
                    continue
                tw_s, tw_e = TW_MAP_M2.get(node, (0, 999_999))
                total += 1
                stype  = TYPE_MAP_M2.get(node, "DELIVERY")
                type_sla[stype]["total"] += 1
                if tw_s <= arr_s <= tw_e:
                    on_time += 1
                    type_sla[stype]["on"] += 1
                else:
                    breaches[PRI_MAP_M2.get(node, "LOW")] += 1
        else:
            # Naive routes: simulate travel time from scratch
            cur_t  = 0
            prev   = 0
            for node in r["route"][1:]:
                if node == 0:
                    break
                cur_t += time_[prev][node]
                tw_s, tw_e = TW_MAP_M2.get(node, (0, 999_999))
                total += 1
                stype  = TYPE_MAP_M2.get(node, "DELIVERY")
                type_sla[stype]["total"] += 1
                if tw_s <= cur_t <= tw_e:
                    on_time += 1
                    type_sla[stype]["on"] += 1
                else:
                    breaches[PRI_MAP_M2.get(node, "LOW")] += 1
                prev = node

    def safe_pct(a, b):
        return round(100 * a / b, 1) if b else 0

    return {
        "sla_pct":      safe_pct(on_time, total),
        "on_time":      on_time,
        "total":        total,
        "high_breach":  breaches["HIGH"],
        "med_breach":   breaches["MEDIUM"],
        "low_breach":   breaches["LOW"],
        "delivery_sla": safe_pct(type_sla["DELIVERY"]["on"], type_sla["DELIVERY"]["total"]),
        "pickup_sla":   safe_pct(type_sla["PICKUP"]["on"],   type_sla["PICKUP"]["total"]),
    }


def print_report_m2(naive, opt, n_sla, o_sla):
    n_cost = naive["total_km"] * COST_PER_KM_M2
    o_cost = opt["total_km"]   * COST_PER_KM_M2

    def pct(a, b):
        return f"-{(a - b) / a * 100:.1f}%" if a else "-"

    W = 72
    print("═" * W)
    print("  MODULE 2 — Forward + Reverse Logistics")
    print("  Naive (Siloed Fleets)  vs  AI Unified Fleet (OR-Tools VRPTW)")
    print("═" * W)
    print(f"\n  {'Metric':<32} {'Naive':>14}  {'AI Opt':>10}  {'Δ':>12}")
    print("─" * W)
    rows = [
        ("Total Vehicles",         naive["n_veh"],                     opt["n_veh"],
         f"{naive['n_veh'] - opt['n_veh']:+d}"),
        ("  — Delivery vehicles",  naive["delivery_vehicles"],         "unified",   ""),
        ("  — Pickup vehicles",    naive["pickup_vehicles"],           "unified",   ""),
        ("Total Distance",         f"{naive['total_km']:.1f} km",      f"{opt['total_km']:.1f} km",
         pct(naive["total_km"], opt["total_km"])),
        ("Total Route Time",       f"{naive['total_min']:.0f} min",    f"{opt['total_min']:.0f} min",
         pct(naive["total_min"], opt["total_min"])),
        ("Total Cost",             f"₹{n_cost:.0f}",                   f"₹{o_cost:.0f}",
         f"₹{int(n_cost - o_cost)} saved"),
        ("Overall SLA",            f"{n_sla['sla_pct']}%",             f"{o_sla['sla_pct']}%",
         f"+{o_sla['sla_pct'] - n_sla['sla_pct']:.1f} pts"),
        ("Delivery SLA",           f"{n_sla['delivery_sla']}%",        f"{o_sla['delivery_sla']}%", ""),
        ("Pickup SLA",             f"{n_sla['pickup_sla']}%",          f"{o_sla['pickup_sla']}%",   ""),
        ("HIGH Priority Breaches", n_sla["high_breach"],               o_sla["high_breach"],        ""),
    ]
    for label, nv, ov, delta in rows:
        print(f"  {label:<32} {str(nv):>14}  {str(ov):>10}  {str(delta):>12}")

    print("\n" + "─" * W)
    print("  OPTIMISED ROUTES — Mixed Delivery + Pickup per Vehicle")
    print("─" * W)
    for r in opt["routes"]:
        nodes = [n for n, _ in r["route_wt"]]
        times = [t // 60 for _, t in r["route_wt"]]
        print(f"  {r['vehicle']}  📦{r['n_deliveries']} deliveries  🔄{r['n_pickups']} pickups  "
              f"{r['dist_m'] / 1000:.1f}km  {r['time_s'] / 60:.0f}min")
        seq = " → ".join(
            f"{'📦' if TYPE_MAP_M2.get(n) == 'DELIVERY' else '🔄' if TYPE_MAP_M2.get(n) == 'PICKUP' else '🏭'}"
            f"{ALL_LOCS_M2[n][1][:12]}(@{t}m)"
            for n, t in zip(nodes, times)
        )
        print(f"       {seq}")
    print("═" * W)

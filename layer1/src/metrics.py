from layer1.data.network import ALL_LOCS, ORDERS, COST_PER_KM, PRIORITY_PENALTY_PER_MIN


def compute_sla(result, time_, use_solver_times=False):
    """
    Calculates SLA compliance and priority breach counts.
    - use_solver_times=True  → use OR-Tools solver arrival times (accurate)
    - use_solver_times=False → simulate manually along naive route
    """
    tw_map  = {o[1]: (o[4]*60, o[5]*60) for o in ORDERS}
    pri_map = {o[1]: o[2]               for o in ORDERS}

    on_time = 0
    total   = 0
    breaches = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    for r in result["routes"]:
        if use_solver_times:
            for node, arr_s in r["route_wt"]:
                if node == 0:
                    continue
                _, tw_e = tw_map.get(node, (0, 999999))
                total += 1
                if arr_s <= tw_e:
                    on_time += 1
                else:
                    breaches[pri_map.get(node, "LOW")] += 1
        else:
            # Naive: no waiting — delivers on arrival regardless of window
            # Arriving early = breach, arriving late = breach
            cur_t = 0
            prev  = 0
            for node in r["route"][1:]:
                if node == 0:
                    break
                cur_t  += time_[prev][node]
                tw_s, tw_e = tw_map.get(node, (0, 999999))
                total  += 1
                # REMOVED: if cur_t < tw_s: cur_t = tw_s
                # Naive delivers immediately — no waiting for window
                if tw_s <= cur_t <= tw_e:
                    on_time += 1
                else:
                    breaches[pri_map.get(node, "LOW")] += 1
                prev = node

    return {
        "sla_pct":      round(100 * on_time / total, 1) if total else 0,
        "on_time":      on_time,
        "total":        total,
        "high_breach":  breaches["HIGH"],
        "med_breach":   breaches["MEDIUM"],
        "low_breach":   breaches["LOW"],
    }


def compute_cost(total_km):
    """Simple cost model: ₹12/km operational cost."""
    return round(total_km * COST_PER_KM, 0)


def print_report(naive, opt, n_sla, o_sla):
    """Prints the full Layer 1 comparison report to console."""
    n_cost = compute_cost(naive["total_km"])
    o_cost = compute_cost(opt["total_km"])

    def pct_saved(a, b):
        return f"-{(a-b)/a*100:.1f}%" if a else "-"

    W = 72
    print("═" * W)
    print("  LAYER 1 — Naive (Greedy NN)  vs  AI Optimised (OR-Tools VRPTW)")
    print("═" * W)
    print(f"\n  {'Metric':<28} {'Naive':>16}  {'AI Opt':>12}  {'Δ':>14}")
    print("─" * W)
    rows = [
        ("Vehicles Used",          naive["n_veh"],                   opt["n_veh"],
         f"{naive['n_veh']-opt['n_veh']:+d}"),
        ("Total Distance",         f"{naive['total_km']:.1f} km",    f"{opt['total_km']:.1f} km",
         pct_saved(naive["total_km"], opt["total_km"])),
        ("Total Route Time",       f"{naive['total_min']:.0f} min",  f"{opt['total_min']:.0f} min",
         pct_saved(naive["total_min"], opt["total_min"])),
        ("Fuel/Ops Cost",          f"₹{n_cost:.0f}",                 f"₹{o_cost:.0f}",
         f"₹{int(n_cost-o_cost)} saved"),
        ("SLA Compliance",         f"{n_sla['sla_pct']}%",           f"{o_sla['sla_pct']}%",
         f"+{o_sla['sla_pct']-n_sla['sla_pct']:.1f} pts"),
        ("HIGH Priority Breaches", n_sla["high_breach"],             o_sla["high_breach"], ""),
        ("MEDIUM Breaches",        n_sla["med_breach"],              o_sla["med_breach"],  ""),
        ("LOW Breaches",           n_sla["low_breach"],              o_sla["low_breach"],  ""),
    ]
    for label, nv, ov, delta in rows:
        print(f"  {label:<28} {str(nv):>16}  {str(ov):>12}  {str(delta):>14}")

    print("\n" + "─" * W)
    print("  NAIVE ROUTES")
    print("─" * W)
    for i, r in enumerate(naive["routes"]):
        zones = list({ALL_LOCS[n][4] for n in r["route"] if n != 0})
        names = " → ".join(ALL_LOCS[n][1][:15] for n in r["route"])
        print(f"  V{i+1} [Zones {zones}]  {r['dist_m']/1000:.1f}km  {r['time_s']/60:.0f}min")
        print(f"       {names}")

    print("\n" + "─" * W)
    print("  OPTIMISED ROUTES  (arrival time from solver)")
    print("─" * W)
    for i, r in enumerate(opt["routes"]):
        nodes = [n for n, _ in r["route_wt"]]
        times = [t//60 for _, t in r["route_wt"]]
        zones = list({ALL_LOCS[n][4] for n in nodes if n != 0})
        print(f"  {r['vehicle']} [Zones {zones}]  {r['dist_m']/1000:.1f}km  {r['time_s']/60:.0f}min")
        seq = " → ".join(f"{ALL_LOCS[n][1][:13]}(@{t}m)" for n, t in zip(nodes, times))
        print(f"       {seq}")

    print("═" * W)

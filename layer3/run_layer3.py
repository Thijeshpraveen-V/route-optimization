# Layer 3 — ETA Continuous Learning Loop
# Run: python layer3/run_layer3.py

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from layer1.src.matrices     import get_matrices
from layer1.src.optimizer    import solve_vrptw
from layer1.src.metrics      import compute_sla
from layer3.src.eta_learner  import ETALearner
from layer3.src.delivery_sim import simulate_actual_times

N_ROUNDS = 4

def sep(c="─", w=72): print(c * w)


if __name__ == "__main__":
    print("🔧 Loading matrices from cache…")
    dist, time_ = get_matrices()

    learner       = ETALearner(alpha=0.3)
    current_time  = [row[:] for row in time_]
    round_results = []

    for rnd in range(1, N_ROUNDS + 1):
        sep("═")
        label = "Base OSRM times" if rnd == 1 else f"Corrected times (Round {rnd-1} learning applied)"
        print(f"  ROUND {rnd} — {label}")
        sep("═")

        opt = solve_vrptw(dist, current_time)
        if not opt:
            print("❌ Solver failed — re-run run_layer1.py first")
            sys.exit(1)

        sla = compute_sla(opt, current_time, use_solver_times=True)

        obs        = simulate_actual_times(opt["routes"], time_, seed=rnd * 42)
        mae_before = learner.compute_mae(obs)
        mae_after  = learner.record_observations(obs)

        current_time = learner.apply_to_matrix(time_)

        top = learner.get_top_corrections(5)

        learner.history.append({
            "round":         rnd,
            "mae_before":    mae_before,
            "mae_after":     mae_after,
            "sla_pct":       sla["sla_pct"],
            "n_obs":         len(obs),
            "n_corrections": len(learner.factors),
            "vehicles":      opt["n_veh"],
            "total_km":      opt["total_km"],
        })

        print(f"\n  🚚 Routes   : {opt['n_veh']} vehicles | {opt['total_km']:.1f} km")
        print(f"  ✅ SLA      : {sla['sla_pct']}%")
        print(f"  📊 Observations : {len(obs)} segments")
        print(f"  📉 ETA Error BEFORE: {mae_before}%")
        print(f"  📈 ETA Error AFTER : {mae_after}%")
        print(f"  🧠 Corrections     : {len(learner.factors)} segment-band pairs")

        if top:
            print(f"\n  🔍 Top Learned Delay Factors:")
            print(f"  {'From':<22} {'To':<22} {'Band':<8} {'Factor':>8}  Impact")
            sep()
            for t in top:
                print(
                    f"  {t['from_name'][:22]:<22} {t['to_name'][:22]:<22} "
                    f"{t['band']:<8} {t['factor']:>8.3f}  {t['impact']}"
                )

        round_results.append(learner.history[-1])

    learner.save()
    output = {
        "rounds":            round_results,
        "top_corrections":   learner.get_top_corrections(15),
        "alpha":             learner.alpha,
        "total_corrections": len(learner.factors),
    }
    with open("layer3_output.json", "w") as f:
        json.dump(output, f, indent=2)

    sep("═")
    print("  LEARNING SUMMARY — ETA Error Reduction Across 4 Rounds")
    sep("═")
    print(f"\n  {'Round':<8} {'ETA Error Before':>18} {'ETA Error After':>17} {'Corrections':>13} {'SLA':>6}")
    sep()
    for r in round_results:
        arrow = "▼" if r["mae_after"] < r["mae_before"] else "─"
        print(
            f"  {r['round']:<8} "
            f"{str(r['mae_before'])+'%':>18} "
            f"{arrow} {str(r['mae_after'])+'%':>15} "
            f"{r['n_corrections']:>13} "
            f"{r['sla_pct']:>5}%"
        )

    first_mae = round_results[0]["mae_before"]
    last_mae  = round_results[-1]["mae_after"]
    print(f"\n  📉 Total ETA Error Reduction : {first_mae}% → {last_mae}%  "
          f"(-{round(first_mae - last_mae, 1)} pts)")
    print(f"  🧠 Total Segments Learned    : {round_results[-1]['n_corrections']}")
    sep("═")
    print("💾  Saved: layer3_output.json + layer3/data/eta_corrections.json")
    sep("═")

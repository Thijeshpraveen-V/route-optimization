# app.py — SmartDeliver AI · Route Optimization Dashboard
# Run: streamlit run app.py

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from layer1.src.matrices     import get_matrices
from layer1.src.naive_solver import solve_naive
from layer1.src.optimizer    import solve_vrptw
from layer1.src.metrics      import compute_sla, compute_cost
from layer1.data.network     import ALL_LOCS, ORDERS, VEHICLES
from layer2.src.traffic_engine  import TRAFFIC_EVENTS, apply_combined_events, get_segment_multipliers
from layer2.src.scenario_runner import run_all_scenarios
from layer2.src.rerouter        import detect_congested_segments
from layer3.src.eta_learner     import ETALearner
from layer3.src.delivery_sim    import simulate_actual_times
from module2.src.matrices_m2     import get_matrices_m2
from module2.src.naive_solver_m2 import solve_naive_m2
from module2.src.optimizer_m2    import solve_vrptw_m2
from module2.src.metrics_m2      import compute_sla_m2
from module2.data.network_m2     import ALL_LOCS_M2, ORDERS_M2, COST_PER_KM_M2

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title  = "SmartDeliver AI",
    page_icon   = "🚚",
    layout      = "wide",
    initial_sidebar_state = "expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
ROUTE_COLORS  = ["#E63946", "#2196F3", "#4CAF50", "#FF9800",
                 "#9C27B0", "#00BCD4", "#F44336", "#8BC34A"]
PRIORITY_ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
DEPOT         = ALL_LOCS[0]
TW_MAP        = {o[1]: (o[4], o[5]) for o in ORDERS}
PRI_MAP       = {o[1]: o[2]         for o in ORDERS}

# ── Cache solver so re-runs don't re-solve ────────────────────────────────────
@st.cache_data(show_spinner=False)
def run_solvers():
    dist, time_ = get_matrices()
    naive        = solve_naive(dist, time_)
    opt          = solve_vrptw(dist, time_)
    n_sla        = compute_sla(naive, time_, use_solver_times=False)
    o_sla        = compute_sla(opt,   time_, use_solver_times=True)
    return dist, time_, naive, opt, n_sla, o_sla

# ── Map builder ───────────────────────────────────────────────────────────────
def build_map(result, time_, use_solver_times, title):
    """Builds a Folium map for either naive or optimised result."""
    center = [DEPOT[2], DEPOT[3]]
    m      = folium.Map(location=center, zoom_start=13, tiles="CartoDB positron")

    # Depot marker
    folium.Marker(
        location = [DEPOT[2], DEPOT[3]],
        tooltip  = f"🏭 Depot: {DEPOT[1]}",
        icon     = folium.Icon(color="black", icon="home", prefix="fa"),
    ).add_to(m)

    for v_idx, r in enumerate(result["routes"]):
        color = ROUTE_COLORS[v_idx % len(ROUTE_COLORS)]

        if use_solver_times:
            nodes  = [n for n, _ in r["route_wt"]]
            times_ = [t for _, t in r["route_wt"]]
        else:
            nodes  = r["route"]
            times_ = None

        # Polyline
        coords = [[ALL_LOCS[n][2], ALL_LOCS[n][3]] for n in nodes]
        folium.PolyLine(
            coords, color=color, weight=4.5, opacity=0.85,
            tooltip=f"{r['vehicle']} · {r['dist_m']/1000:.1f}km · {r['time_s']/60:.0f}min"
        ).add_to(m)

        # Stop markers (skip depot)
        for s_idx, node in enumerate(nodes[1:-1], 1):
            loc    = [ALL_LOCS[node][2], ALL_LOCS[node][3]]
            name   = ALL_LOCS[node][1]
            tw_s, tw_e = TW_MAP.get(node, (0, 240))
            priority   = PRI_MAP.get(node, "LOW")

            if use_solver_times:
                arr_min  = times_[s_idx] // 60
                sla_ok   = tw_s <= arr_min <= tw_e
                sla_icon = "✅" if sla_ok else "❌"
                popup_html = (
                    f"<b>{name}</b><br>"
                    f"{PRIORITY_ICON[priority]} {priority}<br>"
                    f"Window: {tw_s}–{tw_e} min<br>"
                    f"Arrival: {arr_min} min {sla_icon}"
                )
            else:
                popup_html = (
                    f"<b>{name}</b><br>"
                    f"{PRIORITY_ICON[priority]} {priority}<br>"
                    f"Window: {tw_s}–{tw_e} min<br>"
                    f"<i>No time-window awareness</i>"
                )

            folium.CircleMarker(
                location    = loc,
                radius      = 10,
                color       = color,
                fill        = True,
                fill_color  = color,
                fill_opacity= 0.8,
                tooltip     = name,
                popup       = folium.Popup(popup_html, max_width=200),
            ).add_to(m)

            folium.Marker(
                location = loc,
                icon     = folium.DivIcon(
                    html = (
                        f'<div style="font-size:11px;font-weight:bold;color:white;'
                        f'background:{color};border-radius:50%;width:20px;height:20px;'
                        f'text-align:center;line-height:20px;">{s_idx}</div>'
                    ),
                    icon_size=(20, 20), icon_anchor=(10, 10),
                ),
            ).add_to(m)

    return m



def build_scenario_map(scenario_result, congested_segs, scenario_id, ghost_result=None):
    """
    Crystal-clear maps for non-technical judges:

    Scenario A (Naive): Many criss-crossing vehicles, red breach badges
    Scenario B (AI):    4 clean routes, green badges, congestion context shown
    Scenario C (AI+traffic): Ghost gray lines = WHERE B route was,
                             thick animated blue = WHERE AI went instead,
                             🚧 markers on blocked roads
    """
    center = [ALL_LOCS[0][2], ALL_LOCS[0][3]]
    m = folium.Map(location=center, zoom_start=13, tiles="CartoDB positron")

    stops_all = [s for r in scenario_result["routes"]
                 for s in r["stops"] if s.get("sla") != "DEPOT"]
    n_breach  = sum(1 for s in stops_all if s["sla"] == "BREACH")
    n_total   = len(stops_all)
    n_ok      = n_total - n_breach
    veh_used  = scenario_result.get("vehicles_used", len(scenario_result["routes"]))

    # ── Story banner ─────────────────────────────────────────────────────────
    if scenario_id == "A":
        banner_bg    = "#4A4A4A"
        banner_emoji = "⚫"
        banner_text  = (
            f"No AI — {veh_used} vehicles, {n_breach}/{n_total} deliveries MISSED"
            if n_breach else
            f"No AI — {veh_used} vehicles dispatched, all somehow delivered"
        )
    elif scenario_id == "B":
        banner_bg    = "#1B5E20"
        banner_emoji = "🤖"
        banner_text  = (
            f"AI: 4 vehicles, 100% deliveries on time ✅ — target achieved!"
            if not n_breach else
            f"AI: {n_ok}/{n_total} on time — {n_breach} missed"
        )
    else:
        banner_bg    = "#0D47A1"
        banner_emoji = "🔵"
        banner_text  = (
            f"AI dodged traffic — still {n_ok}/{n_total} on time despite road chaos!"
            if n_breach else
            f"AI rerouted perfectly — 100% deliveries saved under congestion! 🎉"
        )
    m.get_root().html.add_child(folium.Element(
        f"<div style='position:fixed;top:10px;left:50%;transform:translateX(-50%);"
        f"z-index:2000;background:{banner_bg};color:white;padding:10px 22px;"
        f"border-radius:30px;font-size:15px;font-weight:bold;font-family:Arial;"
        f"box-shadow:0 4px 14px rgba(0,0,0,0.45);white-space:nowrap;'>"
        f"{banner_emoji} {banner_text}</div>"
    ))

    # ── 1. Traffic blobs + 🚧 markers (B+C) ───────────────────────────────────
    if congested_segs and scenario_id in ["B", "C"]:
        fg_traffic = folium.FeatureGroup(name="🚧 Blocked Roads", show=True)
        seen       = set()
        block_nodes = set()
        for seg in congested_segs:
            i, j = seg["from_node"], seg["to_node"]
            key  = (min(i, j), max(i, j))
            if key in seen:
                continue
            seen.add(key)
            mult  = seg["multiplier"]
            color = ("#D50000" if mult >= 2.5 else "#E65100" if mult >= 1.8 else "#F9A825")
            wt    = min(22, int(8 + (mult - 1.0) * 6))
            op    = (0.80 if mult >= 2.5 else 0.65 if mult >= 1.8 else 0.50)
            tip   = f"🚧 BLOCKED — road is {mult:.1f}× slower · {seg['severity']}"
            folium.PolyLine(
                [[ALL_LOCS[i][2], ALL_LOCS[i][3]], [ALL_LOCS[j][2], ALL_LOCS[j][3]]],
                color=color, weight=wt, opacity=op, tooltip=tip,
            ).add_to(fg_traffic)
            if mult >= 1.8:
                block_nodes.add(i); block_nodes.add(j)
        for nid in block_nodes:
            folium.Marker(
                location=[ALL_LOCS[nid][2], ALL_LOCS[nid][3]],
                tooltip=f"🚧 Road blocked: {ALL_LOCS[nid][1]}",
                icon=folium.DivIcon(
                    html='<div style="font-size:22px;line-height:1;">🚧</div>',
                    icon_size=(28, 28), icon_anchor=(14, 22),
                ),
            ).add_to(fg_traffic)
        fg_traffic.add_to(m)

    # ── 2. Ghost overlay (Scenario C) — WHERE the B route was ─────────────────
    if scenario_id == "C" and ghost_result is not None:
        fg_ghost = folium.FeatureGroup(name="👻 Original Route (avoided)", show=True)
        GCOLS    = ["#9E9E9E", "#BDBDBD", "#757575", "#616161"]
        for v_idx, r in enumerate(ghost_result["routes"]):
            nodes  = r.get("route_nodes", [])
            if not nodes:
                nodes = [0] + [s["node"] for s in r["stops"] if s.get("sla") != "DEPOT"] + [0]
            coords = [[ALL_LOCS[n][2], ALL_LOCS[n][3]] for n in nodes]
            folium.PolyLine(
                coords,
                color=GCOLS[v_idx % len(GCOLS)],
                weight=2, opacity=0.45, dash_array="6 5",
                tooltip="👻 Original plan (before traffic hit)",
            ).add_to(fg_ghost)
        fg_ghost.add_to(m)

    # ── 3. Depot ─────────────────────────────────────────────────────────────
    folium.Marker(
        [ALL_LOCS[0][2], ALL_LOCS[0][3]],
        tooltip="🏭 Depot — all vehicles start here",
        icon=folium.DivIcon(
            html='<div style="font-size:28px;line-height:1;">🏭</div>',
            icon_size=(34, 34), icon_anchor=(17, 30),
        ),
    ).add_to(m)

    # ── 4. Vehicle routes ────────────────────────────────────────────────────
    fg_routes = folium.FeatureGroup(name="🚚 Truck Routes", show=True)
    fg_stops  = folium.FeatureGroup(name="📦 Deliveries",   show=True)

    if scenario_id == "A":
        VCOLS = ["#E53935","#F4511E","#FB8C00","#FDD835","#8E24AA",
                 "#1E88E5","#00ACC1","#43A047","#6D4C41","#78909C",
                 "#D81B60","#546E7A","#00897B","#5E35B1"]
        thick, anim = 3, False
    elif scenario_id == "B":
        VCOLS = ["#1565C0","#2E7D32","#6A1B9A","#BF360C"]
        thick, anim = 4, False
    else:
        VCOLS = ["#1E88E5","#29B6F6","#4FC3F7","#81D4FA"]
        thick, anim = 5, True

    for v_idx, r in enumerate(scenario_result["routes"]):
        v_color = VCOLS[v_idx % len(VCOLS)]
        nodes   = r.get("route_nodes", [])
        if not nodes:
            nodes = [0] + [s["node"] for s in r["stops"] if s.get("sla") != "DEPOT"] + [0]
        coords  = [[ALL_LOCS[n][2], ALL_LOCS[n][3]] for n in nodes]
        stops   = [s for s in r["stops"] if s.get("sla") != "DEPOT"]

        if anim and len(coords) >= 2:
            from folium.plugins import AntPath
            AntPath(
                coords,
                color=v_color, pulse_color="#FFFFFF",
                weight=thick, opacity=0.90, delay=400,
                tooltip=f"🔵 AI Rerouted Truck {v_idx+1} — new path avoiding jams",
            ).add_to(fg_routes)
        else:
            folium.PolyLine(
                coords, color=v_color, weight=thick, opacity=0.90,
                tooltip=f"🚚 Truck {v_idx+1}",
            ).add_to(fg_routes)

        if len(coords) >= 2:
            mid = coords[len(coords) // 2]
            folium.Marker(
                location=mid,
                icon=folium.DivIcon(
                    html=f'<div style="color:{v_color};font-size:{"18" if anim else "14"}px;">&#x25B6;</div>',
                    icon_size=(20, 20), icon_anchor=(10, 10),
                ),
            ).add_to(fg_routes)

        for s in stops:
            node    = s["node"]
            loc     = [ALL_LOCS[node][2], ALL_LOCS[node][3]]
            on_time = s["sla"] == "ON_TIME"
            delay_m = s.get("delay_min", 0)
            name    = s["name"]
            arr     = s["arrival_min"]
            tw_s    = s.get("tw_start_m", "?")
            tw_e    = s.get("tw_end_m", "?")
            prio    = s.get("priority", "LOW")
            st_line = (
                "<span style='color:#2E7D32;font-weight:bold'>✅ Delivered on time!</span>"
                if on_time else
                f"<span style='color:#C62828;font-weight:bold'>❌ Missed — {delay_m:.0f} min late</span>"
            )
            popup_html = (
                f"<div style='font-family:Arial;font-size:13px;min-width:210px;"
                f"padding:8px;line-height:1.7'>"
                f"<b style='font-size:14px'>{name}</b><br>"
                f"Priority: <b>{prio}</b><br>"
                f"Window: <b>{tw_s}–{tw_e} min</b><br>"
                f"Arrived: <b>{arr} min</b><br>"
                f"{st_line}</div>"
            )
            badge_emoji = "✅" if on_time else "🚨"
            bg_col      = "#2E7D32" if on_time else "#C62828"
            short       = name.split()[0][:10]
            late_tag    = (
                f"<br><span style='font-size:10px;color:#FFCDD2;'>+{delay_m:.0f}m late</span>"
                if not on_time else ""
            )
            folium.Marker(
                location=loc,
                tooltip=f"{'\u2705 On time' if on_time else '\u274c LATE'} \u2014 {name}",
                popup=folium.Popup(popup_html, max_width=240),
                icon=folium.DivIcon(
                    html=(
                        '<div style="background:' + bg_col + ';color:white;'
                        'border:3px solid white;border-radius:10px;'
                        'padding:4px 9px;font-size:11px;font-weight:bold;'
                        'font-family:Arial;text-align:center;'
                        'box-shadow:0 3px 8px rgba(0,0,0,0.5);">'
                        + badge_emoji + ' ' + short + late_tag + '</div>'
                    ),
                    icon_size=(100, 44), icon_anchor=(50, 22),
                ),
            ).add_to(fg_stops)

    fg_routes.add_to(m)
    fg_stops.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    # ── 5. Legend ─────────────────────────────────────────────────────────────
    if scenario_id == "A":
        lbl  = "⚫ Scenario A — Naive (No AI)"
        body = ("<div style='line-height:1.9;margin-top:6px'>"
                "🚨 Red badge = delivery MISSED<br>"
                "✅ Green = delivered (lucky)<br>"
                "─── Each colour = one truck<br>"
                "<small>14 vehicles, no coordination</small></div>")
    elif scenario_id == "B":
        lbl  = "🟢 Scenario B — AI + Clear Roads"
        body = ("<div style='line-height:1.9;margin-top:6px'>"
                "✅ All green = 100% on time<br>"
                "─── = AI-coordinated route<br>"
                "🚧 = congested road<br>"
                "4 vehicles instead of 14</div>")
    else:
        lbl  = "🔵 Scenario C — AI + Real Traffic"
        body = ("<div style='line-height:1.9;margin-top:6px'>"
                "🚧 = blocked road<br>"
                "<span style='color:#9E9E9E'>&mdash; &mdash;</span> = original B route<br>"
                "<span style='color:#1E88E5'>⇒⇒⇒</span> = AI rerouted path<br>"
                "✅ = delivery saved by AI!</div>")
    m.get_root().html.add_child(folium.Element(
        f"<div style='position:fixed;bottom:20px;left:10px;z-index:1000;"
        f"background:rgba(10,10,20,0.92);color:white;"
        f"padding:12px 16px;border-radius:10px;font-size:12px;"
        f"font-family:Arial;border:1px solid #555;max-width:240px;'>"
        f"<b style='font-size:13px'>{lbl}</b>{body}</div>"
    ))
    return m


    """
    Non-technical-friendly map:
    - Traffic = thick blobs + 🔥 icons (clearly NOT route lines)
    - Routes  = thin 3px solid lines per vehicle
    - Stops   = large emoji badges (✅ / 🚨) with readable name labels
    - Banner  = plain-English story pinned at top
    """
    center = [ALL_LOCS[0][2], ALL_LOCS[0][3]]
    m = folium.Map(location=center, zoom_start=13, tiles="CartoDB positron")

    stops_all = [s for r in scenario_result["routes"]
                 for s in r["stops"] if s.get("sla") != "DEPOT"]
    n_breach  = sum(1 for s in stops_all if s["sla"] == "BREACH")
    n_total   = len(stops_all)
    n_ok      = n_total - n_breach

    # ── Story banner — plain English, pinned top-center ─────────────────────
    if scenario_id == "A":
        banner_bg, banner_emoji = "#1B5E20", "✅"
        banner_text = f"Perfect plan — all {n_total} deliveries on time, no traffic yet"
    elif scenario_id == "B":
        banner_bg, banner_emoji = "#B71C1C", "🚨"
        banner_text = (
            f"{n_breach} deliver{'y' if n_breach==1 else 'ies'} MISSED — stuck in traffic!"
            if n_breach else f"Traffic hit but all {n_total} deliveries got through (barely)"
        )
    else:
        banner_bg, banner_emoji = "#0D47A1", "🤖"
        banner_text = (
            f"AI rerouted — {n_ok}/{n_total} deliveries saved"
            + (" · 100% on time! 🎉" if not n_breach else f" · {n_breach} unavoidable")
        )
    m.get_root().html.add_child(folium.Element(
        f"<div style='position:fixed;top:10px;left:50%;transform:translateX(-50%);"
        f"z-index:2000;background:{banner_bg};color:white;padding:10px 22px;"
        f"border-radius:30px;font-size:15px;font-weight:bold;font-family:Arial;"
        f"box-shadow:0 4px 14px rgba(0,0,0,0.45);white-space:nowrap;'>"
        f"{banner_emoji} {banner_text}</div>"
    ))

    # ── 1. Congestion blobs (B+C) — thick & vivid, clearly NOT route lines ──
    if scenario_id in ["B", "C"]:
        fg_traffic    = folium.FeatureGroup(name="🔥 Traffic Jams", show=True)
        seen_segs     = set()
        hotspot_nodes = set()
        for seg in congested_segs:
            i, j  = seg["from_node"], seg["to_node"]
            key   = (min(i, j), max(i, j))
            if key in seen_segs:
                continue
            seen_segs.add(key)
            mult    = seg["multiplier"]
            color   = ("#D50000" if mult >= 2.5 else "#E65100" if mult >= 1.8 else "#F9A825")
            opacity = (0.75 if mult >= 2.5 else 0.58 if mult >= 1.8 else 0.42)
            weight  = min(20, int(7 + (mult - 1.0) * 6))
            label   = ("🔴 Standstill" if mult >= 2.5 else "🟠 Heavy jam" if mult >= 1.8 else "🟡 Slow")
            folium.PolyLine(
                [[ALL_LOCS[i][2], ALL_LOCS[i][3]], [ALL_LOCS[j][2], ALL_LOCS[j][3]]],
                color=color, weight=weight, opacity=opacity,
                tooltip=f"{label} — road is {mult:.1f}x slower than normal",
            ).add_to(fg_traffic)
            if mult >= 2.0:
                hotspot_nodes.add(i)
                hotspot_nodes.add(j)
        for node_id in hotspot_nodes:
            folium.Marker(
                location=[ALL_LOCS[node_id][2], ALL_LOCS[node_id][3]],
                tooltip=f"🔥 Traffic hotspot: {ALL_LOCS[node_id][1]}",
                icon=folium.DivIcon(
                    html='<div style="font-size:24px;line-height:1;">🔥</div>',
                    icon_size=(30, 30), icon_anchor=(15, 22),
                ),
            ).add_to(fg_traffic)
        fg_traffic.add_to(m)

    # ── 2. Depot ─────────────────────────────────────────────────────────────
    folium.Marker(
        [ALL_LOCS[0][2], ALL_LOCS[0][3]],
        tooltip="🏭 Warehouse / Depot — vehicles start here",
        icon=folium.DivIcon(
            html='<div style="font-size:28px;line-height:1;">🏭</div>',
            icon_size=(34, 34), icon_anchor=(17, 30),
        ),
    ).add_to(m)

    # ── 3. Vehicle routes — thin (3px), solid, one color per truck ───────────
    fg_routes = folium.FeatureGroup(name="🚚 Truck Routes", show=True)
    fg_stops  = folium.FeatureGroup(name="📦 Deliveries",   show=True)
    VCOLS     = ["#1565C0", "#2E7D32", "#6A1B9A", "#BF360C"]

    for v_idx, r in enumerate(scenario_result["routes"]):
        v_color = VCOLS[v_idx % len(VCOLS)]
        nodes   = r.get("route_nodes", [0] + [s["node"] for s in r["stops"]])
        coords  = [[ALL_LOCS[n][2], ALL_LOCS[n][3]] for n in nodes]
        stops   = [s for s in r["stops"] if s.get("sla") != "DEPOT"]

        folium.PolyLine(
            coords, color=v_color, weight=3, opacity=0.95,
            tooltip=f"🚚 Truck {v_idx+1} route",
        ).add_to(fg_routes)

        if len(coords) >= 2:
            mid = coords[len(coords) // 2]
            folium.Marker(
                location=mid,
                icon=folium.DivIcon(
                    html=f'<div style="color:{v_color};font-size:14px;">▶</div>',
                    icon_size=(18, 18), icon_anchor=(9, 9),
                ),
            ).add_to(fg_routes)

        for s in stops:
            node    = s["node"]
            loc     = [ALL_LOCS[node][2], ALL_LOCS[node][3]]
            on_time = s["sla"] == "ON_TIME"
            delay_m = s.get("delay_min", 0)
            name    = s["name"]
            arr     = s["arrival_min"]
            tw_s    = s.get("tw_start_m", "?")
            tw_e    = s.get("tw_end_m", "?")
            prio    = s.get("priority", "LOW")

            status_line = (
                "<span style='color:#2E7D32;font-weight:bold'>✅ Delivered on time!</span>"
                if on_time else
                f"<span style='color:#C62828;font-weight:bold'>❌ Missed — truck arrived {delay_m:.0f} min too late</span>"
            )
            popup_html = (
                f"<div style='font-family:Arial;font-size:13px;min-width:210px;"
                f"padding:8px;line-height:1.7'>"
                f"<b style='font-size:14px'>{name}</b><br>"
                f"Priority: <b>{prio}</b><br>"
                f"Allowed delivery window: <b>{tw_s}–{tw_e} min</b><br>"
                f"Truck arrived at: <b>{arr} min</b><br>"
                f"{status_line}</div>"
            )

            badge_emoji = "✅" if on_time else "🚨"
            bg_col      = "#2E7D32" if on_time else "#C62828"
            short       = name.split()[0]
            late_tag    = (
                f"<br><span style='font-size:10px;color:#FFCDD2;'>+{delay_m:.0f}m late</span>"
                if not on_time else ""
            )

            folium.Marker(
                location=loc,
                tooltip=f"{'✅' if on_time else '❌ DELAYED'} — {name}",
                popup=folium.Popup(popup_html, max_width=240),
                icon=folium.DivIcon(
                    html=(
                        '<div style="background:' + bg_col + ';color:white;'
                        'border:3px solid white;border-radius:10px;'
                        'padding:4px 9px;font-size:11px;font-weight:bold;'
                        'font-family:Arial;text-align:center;'
                        'box-shadow:0 3px 8px rgba(0,0,0,0.5);">'
                        + badge_emoji + ' ' + short + late_tag + '</div>'
                    ),
                    icon_size=(100, 44), icon_anchor=(50, 22),
                ),
            ).add_to(fg_stops)

    fg_routes.add_to(m)
    fg_stops.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    # ── 4. Legend — plain English ────────────────────────────────────────────
    if scenario_id == "A":
        legend_body = ("<div style='line-height:1.9;margin-top:6px'>"
                       "✅ Green = delivered on time<br>─── Thin line = truck route</div>")
    elif scenario_id == "B":
        legend_body = ("<div style='line-height:1.9;margin-top:6px'>"
                       "🚨 Red badge = MISSED delivery<br>"
                       "✅ Green badge = on time<br>"
                       "🔥 = traffic hotspot<br>"
                       "<span style='color:#D50000'>███</span> Red = standstill road<br>"
                       "<span style='color:#E65100'>███</span> Orange = heavy jam<br>"
                       "─── Thin line = truck route</div>")
    else:
        legend_body = ("<div style='line-height:1.9;margin-top:6px'>"
                       "✅ Green = AI rescued this delivery!<br>"
                       "🚨 Red = still missed (unavoidable)<br>"
                       "🔥 = congestion AI avoided<br>"
                       "─── = AI rerouted truck path</div>")
    label = (
        "🟢 Without Traffic — Normal Plan" if scenario_id == "A" else
        "🔴 With Traffic — No AI Help" if scenario_id == "B" else
        "🔵 With Traffic + AI Rerouting"
    )
    m.get_root().html.add_child(folium.Element(
        f"<div style='position:fixed;bottom:20px;left:10px;z-index:1000;"
        f"background:rgba(10,10,20,0.92);color:white;"
        f"padding:12px 16px;border-radius:10px;font-size:12px;"
        f"font-family:Arial;border:1px solid #555;max-width:230px;'>"
        f"<b style='font-size:13px'>{label}</b>{legend_body}</div>"
    ))
    return m


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/color/96/delivery-truck.png", width=60)
    st.title("SmartDeliver AI")
    st.caption("Route Optimization Engine · Bengaluru")
    st.divider()
    st.markdown("**Network**")
    st.info(f"📍 {len(ALL_LOCS)-1} delivery stops\n\n"
            f"🚚 {len(VEHICLES)} vehicles (cap: {VEHICLES[0][1]} units)\n\n"
            f"📦 {len(ORDERS)} active orders")
    st.divider()
    run_btn   = st.button("🚀 Run Optimization", type="primary", use_container_width=True)
    clear_btn = st.button("🔄 Clear Cache & Re-solve", use_container_width=True)

    if clear_btn:
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown("**Key Features**")

    # ── Layer 2 sidebar box ───────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**🚦 Traffic & Rerouting**")
        st.caption("Simulate congestion and AI real-time rerouting")
        ec1, ec2, ec3 = st.columns(3)
        sel_e1 = ec1.checkbox("Hosur",   value=True,  key="sb_e1")
        sel_e2 = ec2.checkbox("ORR",     value=False, key="sb_e2")
        sel_e3 = ec3.checkbox("Rain",    value=False, key="sb_e3")
        traffic_btn = st.button("▶ Simulate", use_container_width=True, key="traffic_btn")

    # ── Layer 3 sidebar box ───────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**🧠 ETA Learning**")
        st.caption("Adaptive EMA bias correction over 4 rounds")
        learning_btn = st.button("▶ Run Learning", use_container_width=True, key="learning_btn")

    # ── Module 2 sidebar box ─────────────────────────────────────────
    with st.container(border=True):
        st.markdown("❌️ **Forward & Reverse Logistics**")
        st.caption("📦 Deliver + 🔄 Collect returns on the SAME vehicle")
        m2_btn = st.button("▶ Run Module 2", use_container_width=True, key="m2_btn")

    st.divider()
    st.markdown("**Zone Legend**")
    st.markdown("🔵 **Zone A** — Jayanagar cluster")
    st.markdown("🟠 **Zone B** — HSR Layout cluster")
    st.markdown("🟢 **Zone C** — Hosur Rd corridor")
    st.markdown("🔴 **Zone D** — Outliers / Priority trap")

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🚚 SmartDeliver AI — Route Optimization Engine")
st.caption("Layer 1 · Bengaluru Urban Delivery Network · OR-Tools VRPTW + Greedy NN Baseline")

if "results" not in st.session_state:
    st.session_state.results = None

if run_btn or st.session_state.results is None:
    with st.spinner("⚙️ Optimising routes with OR-Tools VRPTW…"):
        try:
            dist, time_, naive, opt, n_sla, o_sla = run_solvers()
            st.session_state.results = (dist, time_, naive, opt, n_sla, o_sla)
        except Exception as e:
            st.error(f"Solver error: {e}")
            st.stop()

if st.session_state.results:
    dist, time_, naive, opt, n_sla, o_sla = st.session_state.results
    n_cost = compute_cost(naive["total_km"])
    o_cost = compute_cost(opt["total_km"])

    # ── KPI Metrics ───────────────────────────────────────────────────────────
    st.subheader("📊 Performance Impact")
    k1, k2, k3, k4, k5 = st.columns(5)

    def pct(a, b): return f"-{(a-b)/a*100:.0f}%"

    k1.metric("Fleet Size",       f"{opt['n_veh']} vehicles",
              f"{opt['n_veh']-naive['n_veh']} vehicles",   delta_color="inverse")
    k2.metric("Total Distance",   f"{opt['total_km']:.1f} km",
              pct(naive["total_km"], opt["total_km"]),      delta_color="inverse")
    k3.metric("Total Time",       f"{opt['total_min']:.0f} min",
              pct(naive["total_min"], opt["total_min"]),    delta_color="inverse")
    k4.metric("Ops Cost",         f"₹{o_cost:.0f}",
              f"-₹{int(n_cost-o_cost)} saved",             delta_color="inverse")
    k5.metric("SLA Compliance",   f"{o_sla['sla_pct']}%",
              f"+{o_sla['sla_pct']-n_sla['sla_pct']:.0f} pts vs naive")

    st.divider()

    # ── Maps ──────────────────────────────────────────────────────────────────
    st.subheader("🗺️ Route Visualization")

    tab1, tab2, tab3 = st.tabs(
        ["🗺️ Side-by-Side Maps", "📈 Performance Charts", "📋 Route Details"]
    )

    with tab1:
        mc1, mc2 = st.columns(2)
        with mc1:
            st.markdown(
                f"#### ❌ Naive Routing (1 Vehicle/Order)\n"
                f"**{naive['n_veh']} vehicles** · {naive['total_km']:.1f} km · "
                f"SLA {n_sla['sla_pct']}% · ₹{n_cost:.0f}"
            )
            m_naive = build_map(naive, time_, use_solver_times=False, title="Naive")
            st_folium(m_naive, width=None, height=420,
                      key="map_naive", returned_objects=[])

        with mc2:
            st.markdown(
                f"#### ✅ AI Optimized (OR-Tools VRPTW)\n"
                f"**{opt['n_veh']} vehicles** · {opt['total_km']:.1f} km · "
                f"SLA {o_sla['sla_pct']}% · ₹{o_cost:.0f}"
            )
            m_opt = build_map(opt, time_, use_solver_times=True, title="Optimized")
            st_folium(m_opt, width=None, height=420,
                      key="map_opt", returned_objects=[])

        st.caption(
            "💡 Click any stop marker to see time window, arrival time, and SLA status."
        )

    with tab2:
        ch1, ch2 = st.columns(2)

        with ch1:
            # Grouped bar: Naive vs Optimized across metrics
            metrics_df = pd.DataFrame({
                "Metric":    ["Vehicles", "Distance (km)", "Time (min)", "Cost (₹/10)"],
                "Naive":     [naive["n_veh"], naive["total_km"],
                              naive["total_min"], n_cost/10],
                "AI Optimized": [opt["n_veh"], opt["total_km"],
                                 opt["total_min"], o_cost/10],
            })
            fig = go.Figure()
            fig.add_bar(name="Naive (1 vehicle/order)",
                        x=metrics_df["Metric"], y=metrics_df["Naive"],
                        marker_color="#EF5350", text=metrics_df["Naive"].round(1),
                        textposition="outside")
            fig.add_bar(name="AI Optimized (VRPTW)",
                        x=metrics_df["Metric"], y=metrics_df["AI Optimized"],
                        marker_color="#42A5F5", text=metrics_df["AI Optimized"].round(1),
                        textposition="outside")
            fig.update_layout(
                barmode="group", title="Naive vs AI Optimized",
                height=380, legend=dict(orientation="h", y=-0.2),
                plot_bgcolor="#0E1117", paper_bgcolor="#0E1117",
                font_color="white",
            )
            st.plotly_chart(fig, use_container_width=True)

        with ch2:
            # SLA compliance stacked bar
            sla_df = pd.DataFrame({
                "System":      ["Naive", "AI Optimized"],
                "On-Time":     [n_sla["on_time"],            o_sla["on_time"]],
                "HIGH Breach": [n_sla["high_breach"],        o_sla["high_breach"]],
                "MED Breach":  [n_sla["med_breach"],         o_sla["med_breach"]],
                "LOW Breach":  [n_sla["low_breach"],         o_sla["low_breach"]],
            })
            fig2 = go.Figure()
            fig2.add_bar(name="On-Time ✅",    x=sla_df["System"],
                         y=sla_df["On-Time"],     marker_color="#66BB6A")
            fig2.add_bar(name="HIGH Breach 🔴", x=sla_df["System"],
                         y=sla_df["HIGH Breach"], marker_color="#EF5350")
            fig2.add_bar(name="MED Breach 🟡",  x=sla_df["System"],
                         y=sla_df["MED Breach"],  marker_color="#FFA726")
            fig2.add_bar(name="LOW Breach 🟢",  x=sla_df["System"],
                         y=sla_df["LOW Breach"],  marker_color="#BDBDBD")
            fig2.update_layout(
                barmode="stack", title="SLA Compliance Breakdown",
                height=380, legend=dict(orientation="h", y=-0.2),
                plot_bgcolor="#0E1117", paper_bgcolor="#0E1117",
                font_color="white",
            )
            st.plotly_chart(fig2, use_container_width=True)

        # Savings summary callout
        st.success(
            f"💰 **Total Savings:** "
            f"**{naive['n_veh']-opt['n_veh']} fewer vehicles** · "
            f"**{naive['total_km']-opt['total_km']:.1f} km saved** · "
            f"**₹{int(n_cost-o_cost)} cost reduction** · "
            f"**{o_sla['sla_pct']-n_sla['sla_pct']:.0f} pts SLA improvement**"
        )

    with tab3:
        st.markdown("#### Optimized Route Details")
        rows = []
        for r in opt["routes"]:
            nodes = [n for n, _ in r["route_wt"]]
            times_arr = [t//60 for _, t in r["route_wt"]]
            for node, arr_min in zip(nodes[1:-1], times_arr[1:-1]):
                tw_s, tw_e = TW_MAP.get(node, (0, 240))
                priority   = PRI_MAP.get(node, "LOW")
                on_time    = tw_s <= arr_min <= tw_e
                rows.append({
                    "Vehicle":   r["vehicle"],
                    "Stop":      ALL_LOCS[node][1],
                    "Zone":      ALL_LOCS[node][4],
                    "Priority":  f"{PRIORITY_ICON[priority]} {priority}",
                    "TW Open":   f"{tw_s} min",
                    "TW Close":  f"{tw_e} min",
                    "Arrival":   f"{arr_min} min",
                    "SLA":       "✅ On-time" if on_time else "❌ Breach",
                })

        df = pd.DataFrame(rows)
        st.dataframe(
            df.style.apply(
                lambda row: ["background-color: #1a3a1a" if row["SLA"] == "✅ On-time"
                             else "background-color: #3a1a1a"] * len(row),
                axis=1,
            ),
            use_container_width=True,
            hide_index=True,
            height=420,
        )

        st.markdown("#### Naive Baseline — All Routes")
        naive_rows = []
        for r in naive["routes"]:
            node = r["route"][1]    # only 1 stop per vehicle
            tw_s, tw_e   = TW_MAP.get(node, (0, 240))
            arr_min      = time_[0][node] // 60
            on_time      = tw_s <= arr_min <= tw_e
            priority     = PRI_MAP.get(node, "LOW")
            naive_rows.append({
                "Vehicle":  r["vehicle"],
                "Stop":     ALL_LOCS[node][1],
                "Priority": f"{PRIORITY_ICON[priority]} {priority}",
                "TW":       f"{tw_s}–{tw_e} min",
                "Arrival":  f"{arr_min} min",
                "SLA":      "✅" if on_time else "❌ Breach",
                "Distance": f"{r['dist_m']/1000:.1f} km",
            })
        st.dataframe(pd.DataFrame(naive_rows), use_container_width=True,
                     hide_index=True, height=420)

    # ═══════════════════════════════════════════════════════════════════════
    # 🚦 LAYER 2 — Traffic & Rerouting (sidebar button triggered)
    # ═══════════════════════════════════════════════════════════════════════
    selected_ids = (
        (["EVT_001"] if sel_e1 else []) +
        (["EVT_002"] if sel_e2 else []) +
        (["EVT_003"] if sel_e3 else [])
    )

    if traffic_btn and selected_ids:
        with st.spinner("Solving all 3 scenarios — Naive / AI / AI+Traffic…"):
            l2 = run_all_scenarios(dist, time_, selected_ids)
            st.session_state.l2_result = l2
            st.session_state.l2_ids    = selected_ids

    if "l2_result" in st.session_state:
        st.divider()
        st.subheader("🚦 Traffic & Rerouting — Live Simulation")
        st.caption("Simulating real Bengaluru congestion events and AI rerouting vs naive response")

        l2  = st.session_state.l2_result
        cmp = l2["comparison"]
        A   = l2["scenario_a"]
        B   = l2["scenario_b"]
        C   = l2["scenario_c"]

        for evt in l2["active_events"]:
            st.warning(f"{evt['icon']} **{evt['name']}** — {evt['description']}")

        st.markdown("#### 📊 3-Scenario Comparison")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("##### ⚫ Scenario A\nNaive — No AI, Normal Roads")
            st.metric("Vehicles Used",  A.get('vehicles_used', '—'))
            st.metric("SLA Compliance", f"{A['sla_pct']}%")
            st.metric("Fleet Distance", f"{A['total_km']:.1f} km")
            st.metric("HIGH Breaches",  A["breaches"]["HIGH"])
        with col_b:
            st.markdown("##### 🟢 Scenario B\nAI Optimized — Clear Roads")
            dv = A.get('vehicles_used',14) - B.get('vehicles_used',4)
            st.metric("Vehicles Used",  B.get('vehicles_used','—'),
                      f"-{dv} vehicles saved 🚚", delta_color="normal")
            st.metric("SLA Compliance", f"{B['sla_pct']}%",
                      f"+{round(B['sla_pct']-A['sla_pct'],1)} pts vs Naive", delta_color="normal")
            st.metric("Fleet Distance", f"{B['total_km']:.1f} km",
                      f"-{round(A['total_km']-B['total_km'],1)} km", delta_color="normal")
            st.metric("HIGH Breaches",  B["breaches"]["HIGH"])
        with col_c:
            st.markdown("##### 🔵 Scenario C\nAI + Real-Time Traffic")
            st.metric("Vehicles Used",  C.get('vehicles_used','—'))
            st.metric("SLA vs Naive",   f"{C['sla_pct']}%",
                      f"+{round(C['sla_pct']-A['sla_pct'],1)} pts vs Naive", delta_color="normal")
            st.metric("Fleet Distance", f"{C['total_km']:.1f} km")
            st.metric("HIGH Breaches",  C["breaches"]["HIGH"])

        if cmp["stops_saved_by_rerouting"]:
            st.success(
                f"✅ **AI recovered {len(cmp['stops_saved_by_rerouting'])} SLA breach(es):** "
                f"{', '.join(cmp['stops_saved_by_rerouting'])}"
            )
        else:
            st.info("ℹ️ All stops reachable under this traffic. AI minimises delay.")

        st.markdown("#### 🗺️ Live Route Maps")
        st.caption(
            "⚫ A = Naive chaos  ·  🟢 B = AI clean plan  ·  🔵 C = AI dodges traffic  ·  "
            "🚧 Red blobs = blocked roads  ·  Ghost lines = original plan  ·  Animated = AI rerouted"
        )

        map_a_tab, map_b_tab, map_c_tab = st.tabs([
            "⚫ Scenario A — Naive (No AI)",
            "🟢 Scenario B — AI + Clear Roads",
            "🔵 Scenario C — AI + Traffic",
        ])
        with map_a_tab:
            st.caption(
                "🔴 **14 separate vehicles, no coordination.** Many stops missed — this is logistics without AI."
            )
            m_a = build_scenario_map(A, [], "A")
            st_folium(m_a, width=None, height=520, key="l2_map_a", returned_objects=[])
        with map_b_tab:
            st.caption(
                "🟢 **4 vehicles, AI-coordinated routes.** All ✅ = 100% SLA on clear roads. "
                "This is your baseline proof that AI works."
            )
            m_b = build_scenario_map(B, l2["congested_segs"], "B")
            st_folium(m_b, width=None, height=520, key="l2_map_b", returned_objects=[])
        with map_c_tab:
            st.caption(
                "🔵 **Same 4 vehicles, but traffic hit.** 🚧 Red blobs = blocked roads. "
                "Ghost lines = original B route. **Animated lines = AI-rerouted path.**"
            )
            m_c = build_scenario_map(C, l2["congested_segs"], "C", ghost_result=B)
            st_folium(m_c, width=None, height=520, key="l2_map_c", returned_objects=[])

        with st.expander("🚦 Congested Segments Detail"):
            if l2["congested_segs"]:
                cdf = pd.DataFrame(l2["congested_segs"])
                cdf = cdf[["from_name","to_name","multiplier","severity"]]
                cdf.columns = ["From","To","Multiplier","Severity"]
                st.dataframe(cdf, use_container_width=True, hide_index=True)

        st.divider()
        ch1, ch2 = st.columns(2)
        with ch1:
            fig_sla = go.Figure(go.Bar(
                x=["A · Naive","B · AI","C · AI+Traffic"],
                y=cmp["sla_pct"],
                marker_color=["#9E9E9E","#43A047","#1E88E5"],
                text=[f"{v}%" for v in cmp["sla_pct"]], textposition="outside",
            ))
            fig_sla.update_layout(title="SLA Compliance", yaxis=dict(range=[0,120]),
                height=340, plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="white")
            st.plotly_chart(fig_sla, use_container_width=True)
        with ch2:
            fig_veh = go.Figure(go.Bar(
                x=["A · Naive","B · AI","C · AI+Traffic"],
                y=cmp["vehicles"],
                marker_color=["#9E9E9E","#43A047","#1E88E5"],
                text=cmp["vehicles"], textposition="outside",
            ))
            fig_veh.update_layout(title="vehicles Used",
                height=340, plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="white")
            st.plotly_chart(fig_veh, use_container_width=True)

    # ═══════════════════════════════════════════════════════════════════════
    # 🧠 LAYER 3 — ETA Continuous Learning (sidebar button triggered)
    # ═══════════════════════════════════════════════════════════════════════
    if learning_btn:
        with st.spinner("Running 4 delivery rounds + EMA correction…"):
            learner      = ETALearner(alpha=0.3)
            current_time = [row[:] for row in time_]
            round_results = []
            for rnd in range(1, 5):
                opt_r = solve_vrptw(dist, current_time)
                if not opt_r:
                    break
                obs          = simulate_actual_times(opt_r["routes"], time_, seed=rnd * 42)
                mae_before   = learner.compute_mae(obs)
                mae_after    = learner.record_observations(obs)
                current_time = learner.apply_to_matrix(time_)
                round_results.append({
                    "round":         rnd,
                    "mae_before":    mae_before,
                    "mae_after":     mae_after,
                    "n_corrections": len(learner.factors),
                    "total_km":      opt_r["total_km"],
                    "n_vehicles":    opt_r["n_veh"],
                })
            learner.save()
            st.session_state.l3_result  = round_results
            st.session_state.l3_learner = learner

    if "l3_result" in st.session_state:
        st.divider()
        st.subheader("🧠 ETA Continuous Learning — Adaptive Bias Correction")
        st.caption(
            "After each delivery round, actual vs predicted travel times are compared. "
            "An EMA updates per-segment correction factors — the optimizer gets smarter each day."
        )
        st.info(
            "**How it works:** Segments like Hosur Road (40–55% slower than OSRM) are discovered "
            "automatically. The solver uses corrected times in the next planning cycle."
        )

        round_results = st.session_state.l3_result
        learner       = st.session_state.l3_learner
        first         = round_results[0]
        last          = round_results[-1]

        k1, k2, k3 = st.columns(3)
        k1.metric("Round 1 ETA Error",  f"{first['mae_before']}%",  "Before learning")
        k2.metric("Round 4 ETA Error",  f"{last['mae_after']}%",
                  f"-{round(first['mae_before']-last['mae_after'],1)} pts", delta_color="inverse")
        k3.metric("Segments Learned",   last["n_corrections"], "segment × time-band pairs")

        st.markdown("#### 📉 ETA Error — 4 Rounds of Learning")
        rounds = [r["round"]     for r in round_results]
        mae_b  = [r["mae_before"] for r in round_results]
        mae_a  = [r["mae_after"]  for r in round_results]
        fig_learn = go.Figure()
        fig_learn.add_scatter(
            x=rounds, y=mae_b, mode="lines+markers+text", name="Before EMA Update",
            line=dict(color="#FF7043", width=4, dash="dot"),
            marker=dict(size=12, color="#FF7043", line=dict(color="white", width=2)),
            text=[f"{v}%" for v in mae_b], textposition="top center",
            textfont=dict(color="#FF7043", size=13, family="Arial Black"),
        )
        fig_learn.add_scatter(
            x=rounds, y=mae_a, mode="lines+markers+text", name="After EMA Update ↓",
            line=dict(color="#69F0AE", width=4),
            marker=dict(size=13, color="#69F0AE", symbol="star", line=dict(color="white", width=2)),
            text=[f"{v}%" for v in mae_a], textposition="bottom center",
            textfont=dict(color="#69F0AE", size=13, family="Arial Black"),
            fill="tozeroy", fillcolor="rgba(105,240,174,0.10)",
        )
        fig_learn.update_layout(
            title=dict(text="ETA Error Decreasing with Each Delivery Round",
                       font=dict(color="white", size=15)),
            legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center",
                        font=dict(color="white", size=12),
                        bgcolor="rgba(30,30,40,0.7)", bordercolor="#555", borderwidth=1),
            height=400, plot_bgcolor="#0E1117", paper_bgcolor="#0E1117",
            font_color="white",
        )
        fig_learn.update_xaxes(
            title_text="Delivery Round", tickvals=[1, 2, 3, 4],
            gridcolor="#333", zeroline=False, title_font=dict(color="white"),
        )
        fig_learn.update_yaxes(
            title_text="Mean Absolute Error %",
            range=[0, max(mae_b) + 8] if mae_b else [0, 30],
            gridcolor="#333", zeroline=False, title_font=dict(color="white"),
        )
        st.plotly_chart(fig_learn, use_container_width=True)

        st.markdown("#### 🔍 What the System Learned — Delay Factors per Segment")
        st.caption(
            "Factor > 1.0 = this road is consistently slower than map data predicted. "
            "The AI now plans around these segments."
        )
        top = learner.get_top_corrections(12)
        if top:
            df_corr = pd.DataFrame(top)
            df_corr = df_corr[["from_name","to_name","band","factor","count","impact"]]
            df_corr.columns = ["From","To","Time Band","Correction Factor","Observations","Impact"]
            df_corr["Correction Factor"] = df_corr["Correction Factor"].apply(lambda x: f"×{x:.3f}")
            st.dataframe(df_corr, use_container_width=True, hide_index=True, height=360)

        st.markdown("#### 📊 Round-by-Round Performance")
        rdf = pd.DataFrame(round_results)
        rdf.columns = ["Round","ETA Error Before","ETA Error After",
                        "Corrections Learned","Total Distance (km)","Vehicles"]
        rdf["ETA Error Before"]     = rdf["ETA Error Before"].apply(lambda x: f"{x}%")
        rdf["ETA Error After"]      = rdf["ETA Error After"].apply(lambda x: f"{x}%")
        rdf["Total Distance (km)"]  = rdf["Total Distance (km)"].apply(lambda x: f"{x:.1f}")
        st.dataframe(rdf, use_container_width=True, hide_index=True)

        with st.expander("📖 How EMA Correction Works"):
            st.markdown("""
**EMA Update Rule:**
```
new_factor = (1 - α) × old_factor + α × observed_factor
```
Where `α = 0.3` — 30% weight on new observation, 70% on history.

**Example — Hosur Road:**
- OSRM predicted: `800s`  
- Round 1 actual: `1240s` → observed factor = 1.55  
- After Round 1: `factor = 0.7×1.0 + 0.3×1.55 = 1.165`  
- Round 2 prediction: `800 × 1.165 = 932s` (closer to reality)  
- After 4 rounds: factor converges to 1.45–1.55

**Why this matters:** OR-Tools reschedules those stops to avoid compounding delays —
serving them earlier, pairing differently, or routing via less congested roads.
            """)

    # ═══════════════════════════════════════════════════════════════════════
    # 📦 MODULE 2 — Forward + Reverse Logistics (sidebar button triggered)
    # ═══════════════════════════════════════════════════════════════════════
    if m2_btn or "m2_result" in st.session_state:
        if m2_btn:
            with st.spinner("🔄 Building 18×18 matrix + solving Forward+Reverse VRPTW…"):
                try:
                    dist_m2, time_m2 = get_matrices_m2()
                    naive_m2 = solve_naive_m2(dist_m2, time_m2)
                    opt_m2   = solve_vrptw_m2(dist_m2, time_m2)
                    if not opt_m2:
                        st.error("❌ OR-Tools found no feasible solution. Check capacity / time-window data.")
                        st.stop()
                    n_sla_m2 = compute_sla_m2(naive_m2, time_m2, use_solver_times=False)
                    o_sla_m2 = compute_sla_m2(opt_m2,   time_m2, use_solver_times=True)
                    st.session_state.m2_result = (dist_m2, time_m2, naive_m2, opt_m2, n_sla_m2, o_sla_m2)
                except Exception as e:
                    st.error(f"Module 2 error: {e}")
                    st.stop()

        if "m2_result" in st.session_state:
            dist_m2, time_m2, naive_m2, opt_m2, n_sla_m2, o_sla_m2 = st.session_state.m2_result
            n_cost_m2 = naive_m2["total_km"] * COST_PER_KM_M2
            o_cost_m2 = opt_m2["total_km"]   * COST_PER_KM_M2
            type_map_m2 = {loc[0]: loc[5] for loc in ALL_LOCS_M2}
            tw_map_m2   = {o[1]: (o[4] * 60, o[5] * 60) for o in ORDERS_M2}
            pri_map_m2  = {o[1]: o[6] for o in ORDERS_M2}

            st.divider()
            st.subheader("🔄 Forward + Reverse Logistics — Unified Fleet")
            st.caption(
                "AI combines outbound deliveries 📦 and return pickups 🔄 on the **SAME 4 vehicles**. "
                "A truck dropping a package has free capacity — AI uses it to collect a return "
                "on the same loop. **Zero extra trips. Zero wasted capacity.**"
            )

            ci1, ci2 = st.columns(2)
            ci1.info("📦 **14 Delivery stops** — outbound packages to customers")
            ci2.info("🔄 **3 Return pickup stops** — customer returns collected on same trip")

            # ── KPI metrics ─────────────────────────────────────────────────────────────
            st.markdown("#### 📊 Impact — Siloed Fleets vs Unified AI Fleet")
            mk1, mk2, mk3, mk4, mk5 = st.columns(5)
            veh_saved = naive_m2["n_veh"] - opt_m2["n_veh"]
            mk1.metric("Total Vehicles",  opt_m2["n_veh"],
                       f"-{veh_saved} vehicles eliminated 🚚", delta_color="normal")
            mk2.metric("Fleet Distance",  f"{opt_m2['total_km']:.1f} km",
                       f"-{naive_m2['total_km']-opt_m2['total_km']:.1f} km", delta_color="normal")
            mk3.metric("Route Time",      f"{opt_m2['total_min']:.0f} min",
                       f"-{naive_m2['total_min']-opt_m2['total_min']:.0f} min", delta_color="normal")
            mk4.metric("Cost Savings",    f"₹{int(n_cost_m2-o_cost_m2)} saved",
                       f"₹{n_cost_m2:.0f} → ₹{o_cost_m2:.0f}", delta_color="normal")
            mk5.metric("SLA Compliance",  f"{o_sla_m2['sla_pct']}%",
                       f"+{o_sla_m2['sla_pct']-n_sla_m2['sla_pct']:.1f} pts vs Naive", delta_color="normal")

            # SLA breakdown
            sk1, sk2 = st.columns(2)
            sk1.metric("📦 Delivery SLA",  f"{o_sla_m2['delivery_sla']}%",
                       f"was {n_sla_m2['delivery_sla']}% naive")
            sk2.metric("🔄 Pickup SLA",   f"{o_sla_m2['pickup_sla']}%",
                       f"was {n_sla_m2['pickup_sla']}% naive")

            st.divider()

            # ── Route map ──────────────────────────────────────────────────────────────
            st.markdown("#### 🗺️ Unified Fleet Routes")
            st.caption(
                "🟢 Green circle = delivery stop  ·  🔴 Red circle = return pickup  ·  "
                "Numbers = sequence order  ·  Click circle for arrival + SLA details"
            )

            center_m2 = [ALL_LOCS_M2[0][2], ALL_LOCS_M2[0][3]]
            m_m2      = folium.Map(location=center_m2, zoom_start=12, tiles="CartoDB positron")

            # Depot
            folium.Marker(
                center_m2, tooltip="🏭 Koramangala Hub — Depot",
                icon=folium.DivIcon(
                    html='<div style="font-size:26px;line-height:1;">🏭</div>',
                    icon_size=(32, 32), icon_anchor=(16, 28),
                )
            ).add_to(m_m2)

            # Banner
            m_m2.get_root().html.add_child(folium.Element(
                f"<div style='position:fixed;top:10px;left:50%;transform:translateX(-50%);"
                f"z-index:2000;background:#0D47A1;color:white;padding:10px 22px;"
                f"border-radius:30px;font-size:14px;font-weight:bold;font-family:Arial;"
                f"box-shadow:0 4px 14px rgba(0,0,0,0.4);white-space:nowrap;'>"
                f"📦 {opt_m2['n_veh']} vehicles handle ALL {len(ORDERS_M2)} stops "
                f"(14 deliveries + 3 pickups) — Zero wasted capacity!</div>"
            ))

            # Legend
            m_m2.get_root().html.add_child(folium.Element(
                "<div style='position:fixed;bottom:20px;left:10px;z-index:1000;"
                "background:rgba(10,10,20,0.92);color:white;"
                "padding:12px 16px;border-radius:10px;font-size:12px;"
                "font-family:Arial;border:1px solid #555;max-width:230px;'>"
                "<b style='font-size:13px'>🔄 Module 2 — Mixed Fleet</b>"
                "<div style='line-height:1.9;margin-top:6px'>"
                "🟢 <b>Green</b> = delivery stop<br>"
                "🔴 <b>Red</b> = return pickup<br>"
                "─── = vehicle route<br>"
                "Number = stop sequence</div></div>"
            ))

            M2_VEH_COLORS = ["#1565C0", "#2E7D32", "#6A1B9A", "#BF360C"]

            for v_idx, r in enumerate(opt_m2["routes"]):
                v_color = M2_VEH_COLORS[v_idx % len(M2_VEH_COLORS)]
                nodes   = [n for n, _ in r["route_wt"]]
                times_  = [t // 60 for _, t in r["route_wt"]]
                coords  = [[ALL_LOCS_M2[n][2], ALL_LOCS_M2[n][3]] for n in nodes]

                folium.PolyLine(
                    coords, color=v_color, weight=4, opacity=0.85,
                    tooltip=f"{r['vehicle']} · 📦{r['n_deliveries']} deliveries · 🔄{r['n_pickups']} pickups",
                ).add_to(m_m2)

                for s_idx, (node, arr_min) in enumerate(zip(nodes[1:-1], times_[1:-1]), 1):
                    stype     = type_map_m2.get(node, "DELIVERY")
                    tw_s, tw_e = tw_map_m2.get(node, (0, 99_999))
                    on_time   = (tw_s // 60) <= arr_min <= (tw_e // 60)
                    name      = ALL_LOCS_M2[node][1]
                    fill_c    = "#43A047" if stype == "DELIVERY" else "#FF6D00"
                    icon_t    = "📦" if stype == "DELIVERY" else "🔄"
                    prio      = pri_map_m2.get(node, "—")

                    popup_html = (
                        f"<div style='font-family:Arial;font-size:13px;min-width:200px;"
                        f"padding:8px;line-height:1.7'>"
                        f"<b>{icon_t} {name}</b><br>"
                        f"Type: <b>{stype}</b><br>"
                        f"Priority: {prio}<br>"
                        f"Window: {tw_s//60}–{tw_e//60} min<br>"
                        f"Arrived: <b>{arr_min} min</b><br>"
                        f"{'<span style=\'color:#2E7D32\'>✅ On-time</span>' if on_time else '<span style=\'color:#C62828\'>❌ Breach</span>'}"
                        f"</div>"
                    )

                    # Simple clear colors: green = delivery, red = pickup
                    stop_color = "#2E7D32" if stype == "DELIVERY" else "#C62828"

                    folium.CircleMarker(
                        location=[ALL_LOCS_M2[node][2], ALL_LOCS_M2[node][3]],
                        radius=14, color="white", weight=3,
                        fill=True, fill_color=stop_color, fill_opacity=0.92,
                        tooltip=f"{icon_t} {name} — {'On time' if on_time else 'BREACH'}",
                        popup=folium.Popup(popup_html, max_width=210),
                    ).add_to(m_m2)

                    # Sequence number — same green/red background
                    folium.Marker(
                        location=[ALL_LOCS_M2[node][2], ALL_LOCS_M2[node][3]],
                        icon=folium.DivIcon(
                            html=(
                                f'<div style="font-size:10px;font-weight:bold;color:white;'
                                f'background:{stop_color};border-radius:50%;width:18px;height:18px;'
                                f'text-align:center;line-height:18px;">{s_idx}</div>'
                            ),
                            icon_size=(18, 18), icon_anchor=(9, 9),
                        ),
                    ).add_to(m_m2)

            st_folium(m_m2, width=None, height=520, key="map_m2", returned_objects=[])

            # ── Route detail table ──────────────────────────────────────────────────────────
            with st.expander("📋 Optimized Route Details — Mixed Delivery + Pickup Fleet", expanded=False):
                rows_m2 = []
                for r in opt_m2["routes"]:
                    nodes  = [n for n, _ in r["route_wt"]]
                    times_ = [t // 60 for _, t in r["route_wt"]]
                    for node, arr in zip(nodes[1:-1], times_[1:-1]):
                        stype     = type_map_m2.get(node, "DELIVERY")
                        tw_s, tw_e = tw_map_m2.get(node, (0, 99_999))
                        on_time   = (tw_s // 60) <= arr <= (tw_e // 60)
                        rows_m2.append({
                            "Vehicle":  r["vehicle"],
                            "Stop":     ALL_LOCS_M2[node][1],
                            "Type":     f"{'📦' if stype == 'DELIVERY' else '🔄'} {stype}",
                            "Priority": pri_map_m2.get(node, "—"),
                            "Window":   f"{tw_s//60}–{tw_e//60} min",
                            "Arrival":  f"{arr} min",
                            "SLA":      "✅" if on_time else "❌",
                        })
                st.dataframe(pd.DataFrame(rows_m2), use_container_width=True,
                             hide_index=True, height=420)

            # ── Comparison chart ─────────────────────────────────────────────────────────
            st.markdown("#### 📈 Siloed Fleets vs Unified AI Fleet")
            ch_m1, ch_m2 = st.columns(2)
            with ch_m1:
                fig_m2_veh = go.Figure()
                fig_m2_veh.add_bar(
                    name="Siloed (No AI)",
                    x=["vehicles", "Distance (km)", "Time (min)"],
                    y=[naive_m2["n_veh"], round(naive_m2["total_km"], 1), round(naive_m2["total_min"])],
                    marker_color="#EF5350", text=[naive_m2["n_veh"],
                        f"{naive_m2['total_km']:.1f}", f"{naive_m2['total_min']:.0f}"],
                    textposition="outside",
                )
                fig_m2_veh.add_bar(
                    name="Unified AI Fleet",
                    x=["vehicles", "Distance (km)", "Time (min)"],
                    y=[opt_m2["n_veh"], round(opt_m2["total_km"], 1), round(opt_m2["total_min"])],
                    marker_color="#42A5F5", text=[opt_m2["n_veh"],
                        f"{opt_m2['total_km']:.1f}", f"{opt_m2['total_min']:.0f}"],
                    textposition="outside",
                )
                fig_m2_veh.update_layout(
                    barmode="group", title="Fleet & Distance Comparison",
                    height=360, legend=dict(orientation="h", y=-0.22),
                    plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="white",
                )
                st.plotly_chart(fig_m2_veh, use_container_width=True)

            with ch_m2:
                fig_m2_sla = go.Figure()
                cats = ["Overall SLA", "Delivery SLA", "Pickup SLA"]
                fig_m2_sla.add_bar(
                    name="Siloed (No AI)",
                    x=cats,
                    y=[n_sla_m2["sla_pct"], n_sla_m2["delivery_sla"], n_sla_m2["pickup_sla"]],
                    marker_color="#EF5350",
                    text=[f"{v}%" for v in [n_sla_m2["sla_pct"], n_sla_m2["delivery_sla"], n_sla_m2["pickup_sla"]]],
                    textposition="outside",
                )
                fig_m2_sla.add_bar(
                    name="Unified AI Fleet",
                    x=cats,
                    y=[o_sla_m2["sla_pct"], o_sla_m2["delivery_sla"], o_sla_m2["pickup_sla"]],
                    marker_color="#42A5F5",
                    text=[f"{v}%" for v in [o_sla_m2["sla_pct"], o_sla_m2["delivery_sla"], o_sla_m2["pickup_sla"]]],
                    textposition="outside",
                )
                fig_m2_sla.update_layout(
                    barmode="group", title="SLA Compliance",
                    yaxis=dict(range=[0, 115]),
                    height=360, legend=dict(orientation="h", y=-0.22),
                    plot_bgcolor="#0E1117", paper_bgcolor="#0E1117", font_color="white",
                )
                st.plotly_chart(fig_m2_sla, use_container_width=True)

            with st.expander("💡 Why This Matters — Real-World Impact"):
                st.markdown("""
**The core insight:** In traditional logistics, delivery vehicles go out empty on the way back,
and return pickup vans go out empty on the way to the customer. This wastes 50% of all mileage.

**Module 2 (AI unified fleet):**
- Vehicle V01 delivers packages to Zone A, then **collects a return from the same neighbourhood**
- Vehicle V02 serves the HSR cluster, picking up 2 returns on the same loop
- **Zero extra trips. Zero deadhead miles for returns.**

**This is exactly how Flipkart, Amazon, and BigBasket operate at scale** —
reverse logistics is not a separate operation; it\'s merged into the same optimized fleet.
                """)




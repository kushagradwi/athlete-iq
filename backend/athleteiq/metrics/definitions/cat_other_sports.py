"""Cycling, swimming, strength and sleep/recovery modules."""
from functools import partial

from ..registry import M

V, E, P, S, H = "implemented_validated", "implemented_experimental", "pending", "requires_sensor", "requires_history"
PW = ["power"]

# ------------------------------------------------------------------ Cycling (25)
CY = partial(M, "cycling")
CY("cycling.avg_power", "Average power", "W", "Mean power including zeros (coasting).", "mean(P)", PW, V)
CY("cycling.max_power_5s", "Best 5 s power", "W", "Highest 5 s mean power.", "max mean(P, 5 s)", PW, V)
CY("cycling.normalized_power", "Normalised power", "W", "4th-power mean of 30 s rolling power (Coggan).",
   "(mean(P₃₀⁴))^¼", PW, V)
CY("cycling.variability_index", "Variability index", "ratio", "NP / average power.", "NP/P̄", PW, V)
CY("cycling.intensity_factor", "Intensity factor", "ratio", "NP / FTP.", "NP/FTP", PW + ["ftp"], V)
CY("cycling.tss", "Training stress score", "AU", "Hours × IF² × 100.", "h·IF²·100", PW + ["ftp"], V)
CY("cycling.work_kj", "Work", "kJ", "Σ power × 1 s / 1000.", "ΣP/1000", PW, V)
CY("cycling.best_1min_power", "Best 1-min power", "W", "Highest 60 s mean power.", "max mean(P, 60 s)", PW, V)
CY("cycling.best_5min_power", "Best 5-min power", "W", "Highest 300 s mean power.", "max mean(P, 300 s)", PW, V)
CY("cycling.best_20min_power", "Best 20-min power", "W", "Highest 1200 s mean power.", "max mean(P, 1200 s)", PW, V)
CY("cycling.ftp_estimate", "FTP estimate (95% of 20 min)", "W", "0.95 × best 20-min power (Allen & Coggan field test).",
   "0.95·P₂₀", PW, E, limitations=["Only valid when the 20-min effort was maximal."])
CY("cycling.watts_per_kg", "Power-to-weight (20 min)", "W/kg", "Best 20-min power / body mass.", "P₂₀/kg", PW + ["weight"], E)
CY("cycling.efficiency_factor", "Efficiency factor (NP/HR)", "W/bpm", "Normalised power per heartbeat.", "NP/HR̄",
   PW + ["heart_rate"], V)
CY("cycling.power_hr_decoupling", "Power:HR decoupling", "%", "EF change between halves.", "(EF₁−EF₂)/EF₁×100",
   PW + ["heart_rate"], V)
CY("cycling.avg_cadence", "Average pedalling cadence", "rpm", "Mean cadence excluding zeros.", "mean(cad>0)", ["cadence"], V)
CY("cycling.coasting_share", "Coasting share", "%", "Moving time with zero power.", "Σ1[P=0 ∧ moving]/moving", PW, E)
CY("cycling.avg_speed", "Average moving speed", "m/s", "Distance / moving time.", "d/t", ["speed"], V)
CY("cycling.vam", "Climbing rate (VAM)", "m/h", "Elevation gain per hour on climbs > 3%.", "Σgain/Σt (g>3%)",
   ["altitude", "distance"], E)
CY("cycling.critical_power", "Critical power", "W", "2-parameter CP model from 3–20 min bests (history).", "P = W′/t + CP",
   PW + ["history"], H, calculation_method="history")
CY("cycling.w_prime", "W′", "kJ", "Anaerobic work capacity (2-parameter model).", "W′ intercept", PW + ["history"], H,
   calculation_method="history")
CY("cycling.w_prime_balance_min", "Minimum W′ balance", "kJ", "Skiba W′bal model minimum.", "Skiba 2012", PW + ["history"], P)
CY("cycling.left_right_balance", "Left/right balance", "% left", "Pedal power balance.", "device", ["lr_balance"], S)
CY("cycling.torque_effectiveness", "Torque effectiveness", "%", "Positive vs negative torque.", "device", ["torque_effectiveness"], S)
CY("cycling.pedal_smoothness", "Pedal smoothness", "%", "Average / peak power per revolution.", "device", ["pedal_smoothness"], S)
CY("cycling.cda_estimate", "Aero drag area estimate", "m²", "Virtual elevation method (Chung).", "VE", PW + ["altitude", "wind"], P)

# ------------------------------------------------------------------ Swimming (20)
SW = partial(M, "swimming")
for mid, name, unit, desc, inputs, st in [
        ("avg_pace_100m", "Average pace per 100 m", "s/100m", "Moving time per 100 m.", ["distance"], E),
        ("total_distance", "Swim distance", "m", "Total distance.", ["distance"], E),
        ("moving_time", "Swim moving time", "s", "Time with speed ≥ 0.2 m/s.", ["speed"], E),
        ("avg_heart_rate", "Swim average HR", "bpm", "Mean HR (optical HR in water is unreliable).", ["heart_rate"], E),
        ("swolf", "SWOLF", "score", "Strokes + seconds per length.", ["length_data"], S),
        ("stroke_rate", "Stroke rate", "spm", "Strokes per minute.", ["stroke_data"], S),
        ("distance_per_stroke", "Distance per stroke", "m", "Length / strokes.", ["stroke_data"], S),
        ("stroke_count_per_length", "Strokes per length", "count", "Mean strokes per pool length.", ["length_data"], S),
        ("stroke_type_mix", "Stroke type mix", "%", "Share by stroke.", ["length_data"], S),
        ("css", "Critical swim speed", "s/100m", "From 400 m and 200 m tests.", ["test_results"], H),
        ("css_pace_share", "Time near CSS", "%", "Time within ±3 s/100 m of CSS.", ["length_data", "css"], S),
        ("rest_interval_share", "Rest interval share", "%", "Rest between sets / total.", ["length_data"], S),
        ("pace_consistency", "Length pace consistency", "%", "CV of length times.", ["length_data"], S),
        ("kick_set_share", "Kick-set share", "%", "Drill/kick share.", ["length_data"], S),
        ("open_water_sighting_cost", "Open-water navigation cost", "%", "GPS distance vs straight line.", ["gps"], P),
        ("swim_tss", "Swim stress score", "AU", "h × (CSS/pace)³ × 100.", ["css", "length_data"], S),
        ("fatigue_index", "Swim fatigue index", "%", "Last vs first set pace.", ["length_data"], S),
        ("turn_time", "Turn time", "s", "Wall-to-wall turn duration.", ["imu"], S),
        ("breath_pattern", "Breathing pattern", "category", "Breaths per length.", ["imu"], S),
        ("pool_length_detected", "Pool length", "m", "Detected pool length.", ["length_data"], P)]:
    SW(f"swimming.{mid}", name, unit, desc, "see description", inputs, st)

# ------------------------------------------------------------------ Strength (20)
ST = partial(M, "strength")
for mid, name, unit, desc in [
        ("total_volume_load", "Volume load", "kg", "Σ sets × reps × load."),
        ("total_sets", "Sets", "count", "Working sets."), ("total_reps", "Reps", "count", "Total repetitions."),
        ("estimated_1rm", "Estimated 1RM", "kg", "Epley from best set."), ("relative_strength", "Relative strength", "×BW", "1RM / body mass."),
        ("session_rpe_load", "Session-RPE load", "AU", "RPE × minutes (Foster 2001)."),
        ("avg_rest_interval", "Average rest", "s", "Rest between sets."), ("time_under_tension", "Time under tension", "s", "Σ concentric+eccentric time."),
        ("bar_velocity_mean", "Mean bar velocity", "m/s", "VBT sensor."), ("velocity_loss", "Velocity loss", "%", "Within-set velocity loss."),
        ("muscle_group_balance", "Muscle-group balance", "ratio", "Push/pull, upper/lower volume."),
        ("progressive_overload_rate", "Overload rate", "%/week", "Volume-load trend."), ("pr_count", "Strength PRs", "count", "New e1RM records."),
        ("density", "Training density", "kg/min", "Volume load per minute."), ("rir_accuracy", "RIR accuracy", "reps", "Predicted vs actual reps to failure."),
        ("unilateral_asymmetry", "Unilateral asymmetry", "%", "Left vs right load."), ("power_output", "Power output", "W", "VBT power."),
        ("hr_during_sets", "HR during sets", "bpm", "Mean HR in working sets."), ("recovery_between_sets", "HR recovery between sets", "bpm", "HR drop in rest."),
        ("weekly_hard_sets", "Weekly hard sets per muscle", "count", "Sets ≥ RPE 7.")]:
    ST(f"strength.{mid}", name, unit, desc, "see description", ["strength_log"], S)

# ------------------------------------------------------------------ Sleep & recovery (20)
SL = partial(M, "recovery")
for mid, name, unit in [
        ("sleep_duration", "Sleep duration", "h"), ("sleep_efficiency", "Sleep efficiency", "%"),
        ("deep_sleep_share", "Deep sleep share", "%"), ("rem_share", "REM share", "%"), ("sleep_latency", "Sleep latency", "min"),
        ("awakenings", "Awakenings", "count"), ("sleep_regularity", "Sleep regularity index", "0–100"),
        ("overnight_hrv", "Overnight HRV (rMSSD)", "ms"), ("overnight_rhr", "Overnight resting HR", "bpm"),
        ("hrv_7d_baseline_ratio", "HRV vs 7-day baseline", "ratio"), ("rhr_7d_baseline_delta", "RHR vs 7-day baseline", "bpm"),
        ("respiratory_rate_night", "Night respiratory rate", "brpm"), ("skin_temp_deviation", "Skin temperature deviation", "°C"),
        ("sleep_debt_7d", "7-day sleep debt", "h"), ("nap_minutes", "Naps", "min"), ("subjective_recovery", "Subjective recovery", "1–5"),
        ("muscle_soreness", "Muscle soreness", "0–10"), ("post_session_hr_recovery", "Post-session HR recovery", "bpm"),
        ("time_to_rhr_baseline", "Time to RHR baseline", "h"), ("recovery_status", "Recovery status", "category")]:
    SL(f"recovery.{mid}", name, unit, f"{name} from a sleep/wellness source.", "device or survey", ["sleep_or_wellness"], S)

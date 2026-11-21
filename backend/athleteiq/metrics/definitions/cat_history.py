"""Categories that depend on history, discoveries or data the first release does not ingest."""
from functools import partial

from ..registry import M

V, E, P, S, H = "implemented_validated", "implemented_experimental", "pending", "requires_sensor", "requires_history"
HIST = dict(calculation_method="history", supported_timeframes=["activity", "7d", "28d", "42d"])

# ------------------------------------------------------------------ Training load (25)
L = partial(M, "load")
L("load.trimp_banister", "TRIMP (Banister)", "AU", "Exponentially HR-weighted training impulse (Banister 1991, male coefficients).",
  "Σ Δt·HRr·0.64·e^(1.92·HRr), HRr = (HR−rest)/(max−rest)", ["heart_rate", "max_hr", "rest_hr"], V,
  limitations=["Uses the male coefficient (1.92); the female coefficient is 1.67. ESTIMATED when max/rest HR are estimated."])
L("load.trimp_edwards", "TRIMP (Edwards)", "AU", "Minutes in 5 %HRmax bands weighted 1–5 (Edwards 1993).",
  "Σ minutes(zone k)·k", ["heart_rate", "max_hr"], V)
L("load.trimp_lucia", "TRIMP (Lucia)", "AU", "Minutes below/around/above LT weighted 1/2/3 (LTHR-anchored variant).",
  "Σ minutes·w", ["heart_rate", "lthr"], E)
L("load.hrtss", "hrTSS", "AU", "Banister TRIMP scaled so one hour at LTHR = 100.", "TRIMP / TRIMP(1 h @ LTHR) × 100",
  ["heart_rate", "lthr", "max_hr", "rest_hr"], V)
L("load.rtss", "rTSS", "AU", "Pace-based stress: hours × IF² × 100, IF from normalised graded pace.",
  "moving_h · (v_NGP/v_thr)² · 100", ["speed", "threshold_pace"], V)
L("load.intensity_factor", "Intensity factor", "ratio", "Normalised graded speed / threshold speed.", "v_NGP / v_thr",
  ["speed", "threshold_pace"], V)
L("load.time_above_lthr", "Time at or above LTHR", "s", "Moving seconds with HR ≥ LTHR.", "Σ 1[HR ≥ LTHR]",
  ["heart_rate", "lthr"], V)
L("load.energy_kcal", "Energy expenditure", "kcal", "Device calories when recorded; else 1.036 kcal/kg/km running estimate.",
  "device | 1.036·kg·km", ["distance", "weight"], E,
  limitations=["The estimate ignores grade and efficiency; state ESTIMATED when not device-measured."])
L("load.session_load", "Session load", "AU", "rTSS when pace data exist, else hrTSS. Feeds the ATL/CTL model.",
  "rTSS ?? hrTSS", ["speed|heart_rate"], V)
L("load.atl", "Acute training load (ATL)", "AU/day", "7-day exponentially weighted mean of daily session load.",
  "ATLₜ = ATLₜ₋₁ + (Lₜ − ATLₜ₋₁)/7", ["history"], E, **HIST,
  limitations=["Impulse-response model; not validated as a fatigue measure for individuals."])
L("load.ctl", "Chronic training load (CTL)", "AU/day", "42-day exponentially weighted mean of daily session load.",
  "CTLₜ = CTLₜ₋₁ + (Lₜ − CTLₜ₋₁)/42", ["history"], E, **HIST)
L("load.tsb", "Training stress balance (TSB)", "AU/day", "CTL − ATL before this session.", "CTL − ATL", ["history"], E, **HIST)
L("load.acwr", "Acute:chronic workload ratio", "ratio", "7-day rolling load / 28-day rolling mean weekly load (uncoupled).",
  "Σ₇L / (Σ₂₈L/4)", ["history"], E, **HIST,
  limitations=["ACWR's link to injury is contested (Impellizzeri 2020); shown as a load-change descriptor only."])
L("load.monotony", "Training monotony", "ratio", "Mean daily load / SD of daily load over 7 days (Foster 1998).",
  "μ₇/σ₇", ["history"], E, **HIST)
L("load.strain", "Training strain", "AU", "Weekly load × monotony (Foster 1998).", "Σ₇L · monotony", ["history"], E, **HIST)
L("load.weekly_load", "7-day load", "AU", "Sum of session load in the 7 days ending with this session.", "Σ₇L",
  ["history"], E, **HIST)
L("load.weekly_distance", "7-day distance", "m", "Sum of distance in the 7 days ending with this session.", "Σ₇d",
  ["history"], E, **HIST)
L("load.ctl_ramp", "Fitness ramp rate", "AU/week", "CTL change over the last 7 days.", "CTLₜ − CTLₜ₋₇", ["history"], E, **HIST)
L("load.low_intensity_share", "Low-intensity share", "%", "Share of moving time in HR zones 1–2.", "(Z1+Z2)/Σ zones",
  ["heart_rate", "lthr"], V)
L("load.high_intensity_share", "High-intensity share", "%", "Share of moving time in HR zones 4–5.", "(Z4+Z5)/Σ zones",
  ["heart_rate", "lthr"], V)
L("load.load_per_km", "Load density", "AU/km", "Session load per kilometre.", "load / km", ["speed|heart_rate"], E)
L("load.aerobic_training_effect", "Aerobic training effect (estimate)", "1–5",
  "TRIMP mapped to a 1–5 scale with saturation (in-house approximation, not Firstbeat).", "1 + 4·(1 − e^(−TRIMP/150))",
  ["heart_rate"], E, limitations=["Approximation; not comparable with device training-effect values."])
L("load.anaerobic_training_effect", "Anaerobic training effect", "1–5", "Contribution of high-intensity bouts.",
  "proprietary in devices", ["heart_rate", "speed"], P)
L("load.epoc_estimate", "EPOC estimate", "ml/kg", "Excess post-exercise oxygen consumption.", "requires VO2 model",
  ["heart_rate", "vo2max"], P)
L("load.recovery_time_estimate", "Recovery time estimate", "h", "Hours until next hard session is advisable.",
  "requires validated recovery model", ["history", "wellness"], P)

# ------------------------------------------------------------------ Progression (20)
G = partial(M, "progression")
G("progression.ef_vs_baseline", "Efficiency vs personal baseline", "z",
  "Robust z-score of this efficiency factor against your previous efforts.", "(EF − median)/(1.4826·MAD)",
  ["history", "heart_rate"], E, **HIST, confidence_requirements="≥ 5 previous activities with HR.")
G("progression.ef_trend_28d", "Efficiency trend (28 d)", "%/week", "Theil–Sen slope of efficiency factor over 28 days.",
  "Theil–Sen(EF ~ days) × 7 / median EF × 100", ["history", "heart_rate"], E, **HIST,
  confidence_requirements="≥ 4 activities in 28 days.")
G("progression.pace_at_reference_hr", "Pace at reference HR", "s/km",
  "Steady-segment pace at 80% LTHR from a robust (Huber) fit of pace on HR across 42 days.",
  "Huber RLM pace ~ HR, evaluated at 0.8·LTHR", ["history", "heart_rate"], E, **HIST,
  confidence_requirements="≥ 8 steady segments.")
G("progression.hr_at_reference_pace", "HR at reference pace", "bpm",
  "Steady-segment HR at threshold pace × 1.25 from a robust fit across 42 days.", "Huber RLM HR ~ speed",
  ["history", "heart_rate"], E, **HIST)
G("progression.pace_duration_prs", "Pace-duration records set", "count",
  "Durations (1–60 min) where this activity beats your previous best mean pace.", "Σ 1[best_d > prior best_d]",
  ["history", "speed"], V, **HIST)
G("progression.best_5km_change", "5 km best vs previous best", "s", "This activity's fastest 5 km minus your prior best.",
  "best5k − prior best5k", ["history", "distance"], E, **HIST)
G("progression.decoupling_trend", "Decoupling trend", "pp/week", "Theil–Sen slope of decoupling on long steady runs.",
  "Theil–Sen", ["history", "heart_rate"], E, **HIST)
G("progression.cadence_trend", "Cadence trend", "spm/week", "Theil–Sen slope of average cadence over 42 days.",
  "Theil–Sen", ["history", "cadence"], E, **HIST)
G("progression.weekly_volume_trend", "Weekly volume trend", "%", "Last 4 weeks' mean weekly distance vs the prior 4.",
  "(μ₄ − μ₄′)/μ₄′ × 100", ["history"], E, **HIST)
G("progression.long_run_trend", "Long-run trend", "%", "Longest run in last 28 d vs the prior 28 d.", "ratio − 1",
  ["history"], E, **HIST)
G("progression.split_consistency_trend", "Split consistency trend", "pp", "Median km-split CV last 28 d minus prior 28 d.",
  "median diff", ["history"], E, **HIST)
G("progression.critical_speed", "Critical speed", "m/s",
  "Slope of distance–time over best efforts of 3–20 min from the 90-day curve (Hill 1925 / Monod–Scherrer).",
  "d = D′ + CS·t, OLS", ["history", "speed"], E, **HIST,
  limitations=["Needs maximal efforts across durations; easy-only histories underestimate CS."])
G("progression.d_prime", "D′ (anaerobic distance capacity)", "m", "Intercept of the distance–time model.", "D′ from OLS",
  ["history", "speed"], E, **HIST)
G("progression.vo2max_estimate", "VO₂max estimate", "ml/kg/min", "Requires validated estimation (e.g. race result or lab).",
  "not implemented", ["history", "race_result"], P)
G("progression.threshold_pace_estimate", "Threshold pace estimate", "s/km", "Auto-detected threshold pace.",
  "requires validated detector", ["history"], P)
G("progression.race_prediction_10k", "10 km race prediction", "s", "Riegel prediction from recent best efforts.",
  "t₂ = t₁(d₂/d₁)^1.06", ["history"], P, limitations=["Pending validation against athlete race results."])
POST = dict(calculation_method="post_discovery", supported_timeframes=["56d"])
G("progression.durability_trend", "Durability index trend", "points/week", "Theil–Sen slope of the Durability Index.",
  "Theil–Sen", ["history", "indexes"], E, **POST)
G("progression.aerobic_index_trend", "Aerobic Efficiency Index trend", "points/week", "Theil–Sen slope of the AEI.",
  "Theil–Sen", ["history", "indexes"], E, **POST)
G("progression.longest_hold_record", "Longest hold at pace (record)", "s",
  "Longest continuous hold within any 10 s/km pace band where this activity sets a personal record.", "max over bands",
  ["history", "speed"], E, **HIST)
G("progression.consistency_streak", "Training consistency streak", "weeks", "Consecutive weeks with ≥ 3 sessions.",
  "count", ["history"], E, **HIST)

# ------------------------------------------------------------------ Cross-workout relationships (20)
C = partial(M, "cross")
C("cross.temperature_hr_cost", "Heat cost on heart rate", "beats/km per °C",
  "Slope of cardiac cost on device temperature across steady runs (Theil–Sen).", "Theil–Sen(cc ~ T)",
  ["history", "temperature", "heart_rate"], E, **HIST, confidence_requirements="≥ 8 activities spanning ≥ 8 °C.")
C("cross.prior_day_load_vs_decoupling", "Yesterday's load vs today's decoupling", "Spearman ρ",
  "Rank correlation between previous-day load and decoupling.", "Spearman", ["history"], E, **HIST)
C("cross.tsb_vs_efficiency", "Freshness vs efficiency", "Spearman ρ", "Rank correlation of TSB with efficiency factor.",
  "Spearman", ["history"], E, **HIST)
C("cross.time_of_day_efficiency", "Time-of-day efficiency gap", "%", "Median EF of runs before 10:00 vs after 16:00.",
  "median ratio − 1", ["history"], E, **HIST)
C("cross.elevation_vs_pace_cost", "Climb cost on pace", "s/km per 10 m/km", "Slope of pace on climb rate across runs.",
  "Theil–Sen", ["history", "altitude"], E, **HIST)
C("cross.weekly_load_vs_ef", "Weekly load vs efficiency", "Spearman ρ", "Correlation of 7-day load with EF.", "Spearman",
  ["history"], E, **HIST)
C("cross.cadence_vs_ef", "Cadence vs efficiency", "Spearman ρ", "Correlation of cadence with EF across runs.", "Spearman",
  ["history", "cadence"], E, **HIST)
C("cross.long_run_vs_next_ef", "Long run → next-run efficiency", "%", "Mean EF change on runs following a long run.",
  "mean ratio − 1", ["history"], E, **HIST)
C("cross.interval_vs_tempo_progress", "Intervals vs tempo progression", "ratio", "Rep-pace trend relative to tempo trend.",
  "slope ratio", ["history"], P)
C("cross.sleep_vs_pace", "Sleep vs pace", "Spearman ρ", "Sleep duration vs pace at reference HR.", "Spearman",
  ["sleep"], S)
C("cross.hrv_vs_efficiency", "HRV vs efficiency", "Spearman ρ", "Morning HRV vs EF.", "Spearman", ["hrv"], S)
C("cross.strength_vs_durability", "Strength work vs durability", "Spearman ρ", "Strength volume vs durability index.",
  "Spearman", ["strength_log"], S)
C("cross.surface_vs_cadence", "Surface vs cadence", "spm", "Cadence difference trail vs road.", "difference",
  ["surface"], P)
C("cross.shoe_vs_efficiency", "Shoe vs efficiency", "%", "EF difference by shoe.", "difference", ["gear"], P)
C("cross.cycling_to_running_transfer", "Cycling → running transfer", "Spearman ρ", "Cycling load vs running EF.", "Spearman",
  ["history_multisport"], P)
C("cross.weather_wind_vs_pace", "Wind vs pace", "s/km per m/s", "Pace sensitivity to wind.", "regression", ["wind"], P)
C("cross.altitude_exposure_vs_hr", "Altitude exposure vs HR", "bpm per 1000 m", "HR change with altitude.", "regression",
  ["history", "altitude"], P)
C("cross.recovery_days_vs_quality", "Recovery days vs session quality", "Spearman ρ",
  "Days since previous hard session vs efficiency.", "Spearman", ["history"], E, **HIST)
C("cross.menstrual_phase_vs_hr", "Cycle phase vs HR", "bpm", "Requires opt-in cycle data.", "difference", ["cycle_log"], S)
C("cross.nutrition_vs_durability", "Fuelling vs durability", "Spearman ρ", "Carbohydrate intake vs durability.",
  "Spearman", ["nutrition_log"], S)

# ------------------------------------------------------------------ AI discovery & confidence (20)
D = partial(M, "discovery", calculation_method="post_discovery")
D("discovery.count", "Discoveries generated", "count", "Number of evidence-backed discoveries for this activity.", "count",
  ["discoveries"], V)
D("discovery.top_significance", "Top significance", "0–1", "Highest ranking score among this activity's discoveries.",
  "max(score)", ["discoveries"], V)
D("discovery.mean_confidence", "Mean discovery confidence", "0–1", "Mean confidence across discoveries.", "mean", ["discoveries"], V)
D("discovery.personal_records", "Personal records", "count", "Discoveries classified PERSONAL_RECORD.", "count", ["discoveries"], V)
D("discovery.emerging_patterns", "Emerging patterns", "count", "Discoveries classified EMERGING_PATTERN.", "count",
  ["discoveries"], V)
D("discovery.confirmed_trends", "Confirmed trends", "count", "Discoveries classified CONFIRMED_TREND (Mann–Kendall p < 0.05).",
  "count", ["discoveries"], V)
D("discovery.anomalies", "Anomalies", "count", "Discoveries classified ANOMALY.", "count", ["discoveries"], V)
D("discovery.new_observations", "New observations", "count", "Discoveries classified NEW_OBSERVATION.", "count",
  ["discoveries"], V)
D("discovery.comparable_efforts", "Comparable efforts found", "count", "Historical segments matched to this activity's segments.",
  "count", ["segments", "history"], E)
D("discovery.match_quality", "Comparable match quality", "0–1", "Mean similarity of matched comparable efforts.", "mean",
  ["segments", "history"], E)
D("discovery.baseline_sample_size", "Baseline sample size", "activities", "Prior activities available for comparison.",
  "count", ["history"], V)
D("discovery.evidence_items", "Evidence items", "count", "Evidence rows attached across discoveries.", "count",
  ["discoveries"], V)
D("discovery.detectors_run", "Detectors run", "count", "Discovery detectors executed.", "count", ["discoveries"], V)
D("discovery.detectors_abstained", "Detectors abstained", "count", "Detectors that found insufficient evidence.", "count",
  ["discoveries"], V)
D("discovery.data_quality_weight", "Data-quality weight", "0–1", "Quality multiplier applied to discovery confidence.",
  "activity quality score", ["quality"], V)
D("discovery.ai_claims_verified", "AI claims verified", "ratio", "Share of AI commentary claims passing evidence checks.",
  "verified / total", ["ai_commentary"], E)
D("discovery.ai_claims_rejected", "AI claims rejected", "count", "AI claims dropped for uncited ids or unverifiable numbers.",
  "count", ["ai_commentary"], E)
D("discovery.goal_relevance", "Goal relevance", "0–1", "Mean goal-relevance component of ranked discoveries.", "mean",
  ["discoveries", "goal"], V)
D("discovery.novelty", "Novelty", "0–1", "Mean novelty component of ranked discoveries.", "mean", ["discoveries"], V)
D("discovery.actionability", "Actionability", "0–1", "Mean actionability component of ranked discoveries.", "mean",
  ["discoveries"], V)

# ------------------------------------------------------------------ Training readiness (15)
RD = partial(M, "readiness")
RD("readiness.days_since_last_activity", "Days since last activity", "days", "Days between this and the previous activity.",
   "Δ days", ["history"], E, **HIST)
RD("readiness.days_since_hard_session", "Days since hard session", "days",
   "Days since the last session with IF ≥ 0.9 or ≥ 10 min above LTHR.", "Δ days", ["history"], E, **HIST)
RD("readiness.pre_session_tsb", "Freshness before session", "AU/day", "TSB entering this session (same as load.tsb).", "CTL−ATL",
   ["history"], P, limitations=["Duplicate view of load.tsb; pending a validated readiness model."])
for mid, name, inp in [("resting_hr_deviation", "Resting HR deviation", "resting_hr"),
                       ("hrv_deviation", "HRV deviation", "hrv"),
                       ("sleep_debt", "Sleep debt", "sleep"),
                       ("soreness_score", "Soreness score", "wellness_survey"),
                       ("mood_score", "Mood score", "wellness_survey"),
                       ("stress_score", "Life-stress score", "wellness_survey"),
                       ("readiness_composite", "Readiness composite", "hrv"),
                       ("orthostatic_hr", "Orthostatic HR response", "orthostatic_test"),
                       ("grip_or_jump_test", "Neuromuscular test", "jump_test"),
                       ("illness_flag", "Illness flag", "wellness_survey"),
                       ("travel_jetlag", "Travel / jet-lag load", "calendar")]:
    RD(f"readiness.{mid}", name, "AU", f"{name} versus personal baseline.", "deviation from baseline", [inp], S)
RD("readiness.planned_session_fit", "Planned session fit", "category", "Fit between planned session and state.", "rules",
   ["training_plan"], P)

# ------------------------------------------------------------------ Injury & movement risk (15)
K = partial(M, "risk", limitations=["Descriptive load/movement signal only. Not a diagnosis or injury prediction."])
K("risk.load_spike_flag", "Load spike flag", "flag", "1 when 7-day load exceeds 1.5× the 28-day weekly mean.",
  "1[ACWR > 1.5]", ["history"], E, **HIST)
K("risk.weekly_distance_jump", "Weekly distance jump", "%", "7-day distance vs previous 7 days.", "(d₇/d₇′ − 1) × 100",
  ["history"], E, **HIST)
K("risk.long_run_share", "Long-run share of week", "%", "This run's distance / 7-day distance.", "d / Σ₇d", ["history"], E, **HIST)
K("risk.consecutive_hard_days", "Consecutive hard days", "days", "Run of days with IF ≥ 0.9 ending today.", "count",
  ["history"], E, **HIST)
K("risk.late_form_change", "Late-run form change", "%", "Step-length change in the last quarter at similar pace.",
  "ΔSL Q4 vs Q1", ["cadence", "speed"], E)
for mid, name, inp in [("asymmetry_gct", "GCT asymmetry", "gct_balance"), ("impact_trend", "Impact trend", "imu"),
                       ("pain_report_trend", "Pain report trend", "wellness_survey"),
                       ("injury_history_weight", "Injury history weight", "injury_log"),
                       ("shoe_mileage", "Shoe mileage", "gear"), ("surface_change", "Sudden surface change", "surface"),
                       ("downhill_load", "Downhill eccentric load", "altitude_history"),
                       ("bone_stress_load", "Bone-loading index", "imu"), ("sleep_risk_modifier", "Sleep modifier", "sleep"),
                       ("injury_risk_model", "Injury risk model", "injury_outcomes")]:
    K(f"risk.{mid}", name, "AU", f"{name}: registered for future work with validated inputs.", "pending", [inp],
      S if mid not in ("downhill_load", "injury_risk_model") else P)

# ------------------------------------------------------------------ Training planning (15)
PL = partial(M, "planning", calculation_method="history")
for mid, name, desc in [
        ("next_long_run_distance", "Suggested long-run distance", "Progression rule from recent long runs."),
        ("easy_pace_range", "Easy pace range", "Pace band from personal HR-pace relationship."),
        ("tempo_pace_range", "Tempo pace range", "From threshold pace."),
        ("interval_pace_targets", "Interval pace targets", "From critical speed."),
        ("weekly_volume_target", "Weekly volume target", "Ramp-limited from CTL."),
        ("taper_plan", "Taper plan", "Race-dependent volume reduction."),
        ("session_mix", "Session mix", "Intensity distribution target."),
        ("recovery_day_placement", "Recovery day placement", "From monotony and load."),
        ("race_pacing_plan", "Race pacing plan", "Per-km targets for an event."),
        ("fuel_plan", "Fuelling plan", "Carbohydrate per hour by duration."),
        ("heat_adjusted_pace", "Heat-adjusted pace", "Pace adjustment for temperature."),
        ("altitude_adjusted_pace", "Altitude-adjusted pace", "Pace adjustment for altitude."),
        ("repeat_effort_experiment", "Repeat-effort experiment", "Protocol to validate a discovery."),
        ("cadence_drill_target", "Cadence drill target", "From cadence-speed relationship."),
        ("deload_week_signal", "Deload week signal", "From ramp rate and strain.")]:
    PL(f"planning.{mid}", name, "varies", desc, "planning module (not yet built)", ["history", "goal"], P)

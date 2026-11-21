"""Single-activity categories: running, biomechanics, environment, workout execution."""
from functools import partial

from ..registry import M

V, E, P, S, H = "implemented_validated", "implemented_experimental", "pending", "requires_sensor", "requires_history"

# ------------------------------------------------------------------ Running (30)
R = partial(M, "running")
R("running.distance", "Distance", "m", "Distance covered from first to last sample.", "d[last] − d[first]",
  ["distance or GPS"], V)
R("running.moving_time", "Moving time", "s", "Seconds with 5 s smoothed speed ≥ 0.8 m/s, excluding recording gaps.",
  "Σ 1[v̄5 ≥ 0.8]", ["speed or distance"], V)
R("running.elapsed_time", "Elapsed time", "s", "Wall-clock duration from first to last sample.", "t[last] − t[first] + 1",
  ["timestamps"], V)
R("running.avg_pace", "Average moving pace", "s/km", "Moving time divided by distance.", "moving_s / (distance_m/1000)",
  ["distance", "speed"], V)
R("running.avg_speed", "Average moving speed", "m/s", "Distance divided by moving time.", "distance_m / moving_s",
  ["distance", "speed"], V)
R("running.max_speed_5s", "Best 5 s speed", "m/s", "Highest 5-second mean speed.", "max over windows of mean(v, 5 s)",
  ["speed"], V, limitations=["GPS-derived speed can spike; 5 s window damps but does not remove spikes."])
R("running.avg_heart_rate", "Average heart rate", "bpm", "Mean HR while moving.", "mean(HR | moving)", ["heart_rate"], V)
R("running.max_heart_rate", "Maximum heart rate", "bpm", "Highest 5 s mean HR (spike resistant).", "max(mean(HR, 5 s))",
  ["heart_rate"], V)
R("running.hr_drift", "Heart-rate drift", "bpm", "Mean moving HR in the 2nd half minus the 1st half, excluding the first 10 min.",
  "mean(HR₂) − mean(HR₁) after warm-up", ["heart_rate", "speed"], V,
  limitations=["Only comparable when pace is roughly even; see aerobic decoupling for a pace-normalised version."],
  confidence_requirements="≥ 20 min moving after warm-up.")
R("running.aerobic_decoupling", "Aerobic decoupling (Pa:HR)", "%",
  "Change in speed-per-heartbeat between halves; positive = HR rose relative to pace.",
  "(EF₁ − EF₂)/EF₁ × 100, EF = mean speed / mean HR", ["heart_rate", "speed"], V,
  limitations=["Designed for steady aerobic efforts; intervals inflate it."], confidence_requirements="≥ 20 min moving.")
R("running.efficiency_factor", "Efficiency factor", "m/min/bpm", "Normalised graded speed per heartbeat.",
  "NGP speed (m/min) / mean HR", ["heart_rate", "speed"], V,
  limitations=["Personal metric: compare only with your own values."])
R("running.normalized_graded_pace", "Normalised graded pace", "s/km",
  "4th-power mean of 30 s grade-adjusted speed (energy-cost model after Minetti 2002).",
  "1000 / (mean(GAS₃₀⁴))^¼", ["speed"], V,
  limitations=["Grade adjustment needs altitude; without it NGP equals normalised pace."])
R("running.grade_adjusted_pace", "Grade-adjusted average pace", "s/km",
  "Average pace corrected for gradient with Minetti's energy-cost polynomial.", "1000 / mean(GAS)", ["speed", "altitude"], E)
R("running.pace_cv", "Pace variability", "%", "Coefficient of variation of 30 s moving speed.", "σ(v₃₀)/μ(v₃₀) × 100",
  ["speed"], V)
R("running.km_split_cv", "Km split consistency", "%", "Coefficient of variation of full-km split times.",
  "σ(split)/μ(split) × 100", ["distance"], V, confidence_requirements="≥ 3 full kilometres.")
R("running.negative_split_ratio", "Split ratio", "ratio", "Time for the 2nd half of the distance / time for the 1st.",
  "t(2nd half) / t(1st half); < 1 = negative split", ["distance"], V)
R("running.fastest_km", "Fastest km split", "s", "Shortest full-km split time.", "min(split times)", ["distance"], V)
R("running.slowest_km", "Slowest km split", "s", "Longest full-km split time (moving time).", "max(split moving times)",
  ["distance"], V)
R("running.best_1km", "Fastest 1 km", "s", "Shortest time for any 1000 m within the activity.",
  "min over i of (t(d_i+1000) − t_i)", ["distance"], V)
R("running.best_5km", "Fastest 5 km", "s", "Shortest time for any 5000 m within the activity.", "as best_1km for 5000 m",
  ["distance"], V)
R("running.best_10km", "Fastest 10 km", "s", "Shortest time for any 10 000 m within the activity.", "as best_1km for 10 000 m",
  ["distance"], V)
R("running.best_pace_5min", "Best 5-min pace", "s/km", "Fastest mean pace over any 300 s window.",
  "1000 / max(mean(v, 300 s))", ["speed"], V)
R("running.best_pace_20min", "Best 20-min pace", "s/km", "Fastest mean pace over any 1200 s window.",
  "1000 / max(mean(v, 1200 s))", ["speed"], V)
R("running.cardiac_cost", "Cardiac cost", "beats/km", "Heartbeats spent per kilometre while moving.",
  "Σ HR/60 / distance_km", ["heart_rate", "distance"], V)
for z, (lo, hi) in enumerate([(0, .85), (.85, .90), (.90, .95), (.95, 1.0), (1.0, 9)], start=1):
    R(f"running.time_hr_z{z}", f"Time in HR zone {z}", "s",
      f"Moving seconds with HR in [{lo:.0%}, {hi:.0%}) of LTHR (Friel 5-zone run model)." if hi < 9 else
      "Moving seconds with HR ≥ 100% of LTHR.", f"Σ 1[{lo} ≤ HR/LTHR < {hi}]", ["heart_rate", "lthr"], V,
      limitations=["State is ESTIMATED when LTHR is estimated rather than set by the athlete."])
R("running.longest_steady_segment", "Longest steady segment", "s",
  "Longest stretch where 30 s pace stays within ±4% of the stretch mean.", "max segment duration (steady detector)",
  ["speed"], V)

# ------------------------------------------------------------------ Biomechanics (25)
B = partial(M, "biomechanics")
B("biomechanics.avg_cadence", "Average cadence", "spm", "Mean steps per minute while moving.", "mean(cad | moving)",
  ["cadence"], V)
B("biomechanics.cadence_cv", "Cadence stability", "%", "Coefficient of variation of moving cadence.", "σ/μ × 100",
  ["cadence"], V)
B("biomechanics.cadence_drift", "Cadence drift", "spm", "Last-quarter minus first-quarter mean cadence.",
  "mean(cad Q4) − mean(cad Q1)", ["cadence"], V)
B("biomechanics.avg_stride_length", "Average stride (step) length", "m", "Mean distance per step while moving.",
  "mean(v/(cad/60))", ["cadence", "speed"], V, limitations=["Derived from speed and cadence unless the device measures it."])
B("biomechanics.stride_length_cv", "Step-length variability", "%", "Coefficient of variation of step length.", "σ/μ × 100",
  ["cadence", "speed"], E)
B("biomechanics.stride_length_drift", "Step-length drift", "%", "Change in step length, last vs first quarter.",
  "(SL Q4 / SL Q1 − 1) × 100", ["cadence", "speed"], E)
B("biomechanics.cadence_speed_slope", "Cadence response to speed", "spm per m/s",
  "OLS slope of cadence on speed while moving: how much you speed up by turnover.", "β in cad = α + β·v",
  ["cadence", "speed"], E)
B("biomechanics.stride_speed_slope", "Step-length response to speed", "m per m/s", "OLS slope of step length on speed.",
  "β in SL = α + β·v", ["cadence", "speed"], E)
B("biomechanics.total_steps", "Total steps", "steps", "Σ cadence/60 over moving seconds.", "Σ cad/60", ["cadence"], V)
B("biomechanics.avg_ground_contact", "Ground contact time", "ms", "Mean stance time.", "mean(GCT)", ["ground_contact_time"],
  S, confidence_requirements="Requires a running-dynamics sensor.")
B("biomechanics.ground_contact_drift", "Ground contact drift", "ms", "Q4 minus Q1 mean GCT.", "mean Q4 − mean Q1",
  ["ground_contact_time"], S)
B("biomechanics.avg_vertical_oscillation", "Vertical oscillation", "mm", "Mean vertical bounce per step.", "mean(VO)",
  ["vertical_oscillation"], S)
B("biomechanics.vertical_ratio", "Vertical ratio", "%", "Vertical oscillation / step length.", "VO / SL × 100",
  ["vertical_oscillation", "cadence", "speed"], S)
B("biomechanics.vertical_oscillation_drift", "Vertical oscillation drift", "mm", "Q4 minus Q1 mean VO.", "mean Q4 − mean Q1",
  ["vertical_oscillation"], S)
B("biomechanics.duty_factor", "Duty factor", "%", "Ground contact time as a share of step time.",
  "GCT / (60000/cad) × 100", ["ground_contact_time", "cadence"], S)
B("biomechanics.gct_balance", "Ground contact balance", "% left", "Left/right stance-time split.", "GCT_L / (GCT_L+GCT_R)",
  ["gct_balance"], S, confidence_requirements="Requires a sensor reporting left/right balance.")
B("biomechanics.leg_spring_stiffness", "Leg spring stiffness", "kN/m", "Spring-mass model stiffness (Morin 2005).",
  "F_max / Δl", ["ground_contact_time", "cadence", "speed", "weight", "leg_length"], P)
B("biomechanics.impact_loading_rate", "Impact loading rate", "BW/s", "Peak loading rate from IMU.", "dF/dt peak",
  ["imu"], S)
B("biomechanics.form_power", "Form power", "W", "Power attributed to vertical/lateral motion.", "device-reported",
  ["running_power_device"], S)
B("biomechanics.cadence_final_quarter", "Cadence in final quarter", "spm", "Mean cadence in the last 25% of moving time.",
  "mean(cad Q4)", ["cadence"], V)
B("biomechanics.cadence_at_easy_pace", "Cadence at easy pace", "spm", "Mean cadence on steady segments slower than 85% of threshold speed.",
  "mean(cad | steady ∧ v < 0.85·v_thr)", ["cadence", "speed", "threshold_pace"], E)
B("biomechanics.stride_at_threshold_pace", "Step length near threshold pace", "m",
  "Mean step length while 30 s speed is within 95–105% of threshold speed.", "mean(SL | 0.95 ≤ v/v_thr ≤ 1.05)",
  ["cadence", "speed", "threshold_pace"], E)
B("biomechanics.pelvic_drop", "Pelvic drop", "deg", "Contralateral pelvic drop.", "IMU", ["pelvis_imu"], S)
B("biomechanics.foot_strike_pattern", "Foot-strike pattern", "category", "Rearfoot / midfoot / forefoot share.", "IMU",
  ["foot_imu"], S)
B("biomechanics.step_rate_variability_late", "Late-run step variability", "%",
  "Cadence CV in the final quarter (fatigue-related form breakdown marker).", "σ/μ(cad Q4) × 100", ["cadence"], E)

# ------------------------------------------------------------------ Environment (15)
EN = partial(M, "environment")
EN("environment.avg_temperature", "Average temperature", "°C", "Mean device temperature.", "mean(T)", ["temperature"], V,
   limitations=["Wrist devices read warm (body heat); treat as relative, not air temperature."])
EN("environment.max_temperature", "Maximum temperature", "°C", "Highest device temperature.", "max(T)", ["temperature"], V)
EN("environment.temperature_range", "Temperature range", "°C", "Max minus min device temperature.", "max − min",
   ["temperature"], E)
EN("environment.elevation_gain", "Elevation gain", "m", "Ascent from 15 s smoothed altitude with 1 m hysteresis.",
   "Σ climbs ≥ 1 m", ["altitude"], V, limitations=["Barometric drift and GPS altitude noise affect totals."])
EN("environment.elevation_loss", "Elevation loss", "m", "Descent from 15 s smoothed altitude with 1 m hysteresis.",
   "Σ descents ≥ 1 m", ["altitude"], V)
EN("environment.max_grade", "Steepest climb", "%", "Maximum smoothed grade.", "max(grade)", ["altitude", "distance"], E)
EN("environment.min_grade", "Steepest descent", "%", "Minimum smoothed grade.", "min(grade)", ["altitude", "distance"], E)
EN("environment.avg_abs_grade", "Hilliness", "%", "Mean absolute grade while moving.", "mean(|grade|)", ["altitude", "distance"], E)
EN("environment.climb_rate", "Elevation gain per km", "m/km", "Elevation gain divided by distance.", "gain / km",
   ["altitude", "distance"], V)
EN("environment.max_altitude", "Highest altitude", "m", "Maximum smoothed altitude.", "max(alt)", ["altitude"], V)
EN("environment.pct_time_climbing", "Time climbing", "%", "Share of moving time on grades > 2%.", "Σ1[g>2]/moving",
   ["altitude", "distance"], E)
EN("environment.heat_index", "Heat index", "°C", "Apparent temperature from air temperature and humidity (NWS).",
   "Rothfusz regression", ["air_temperature", "humidity"], S)
EN("environment.wind_component", "Head/tail-wind component", "m/s", "Wind projected onto running direction.",
   "w·cos(θ)", ["weather_api", "gps"], P)
EN("environment.air_quality", "Air quality index", "AQI", "Air quality during the activity.", "external provider",
   ["air_quality_api"], P)
EN("environment.surface_mix", "Surface mix", "%", "Share of distance on road / trail / track.", "map matching",
   ["gps", "map_data"], P)

# ------------------------------------------------------------------ Workout execution (20)
X = partial(M, "execution")
X("execution.interval_count", "Detected work intervals", "count",
  "Work bouts (30 s–20 min) above an Otsu speed threshold when speed is clearly bimodal.", "count(work bouts)", ["speed"], V)
X("execution.rep_pace_cv", "Rep pace consistency", "%", "CV of work-interval paces.", "σ/μ(rep pace) × 100", ["speed"], V,
  confidence_requirements="≥ 3 detected intervals.")
X("execution.rep_duration_cv", "Rep duration consistency", "%", "CV of work-interval durations.", "σ/μ(rep s) × 100",
  ["speed"], E)
X("execution.work_rest_ratio", "Work:rest ratio", "ratio", "Total work time / total recovery time.", "Σ work / Σ rest",
  ["speed"], E)
X("execution.interval_hr_recovery", "Interval HR recovery", "bpm",
  "Mean HR drop in the first 60 s of recoveries.", "mean(HR(end of rep) − HR(+60 s))", ["heart_rate", "speed"], E)
X("execution.avg_work_pace", "Average work-interval pace", "s/km", "Mean pace across work bouts.", "Σ t / Σ d over reps",
  ["speed"], E)
X("execution.avg_recovery_pace", "Average recovery pace", "s/km", "Mean pace across recoveries.", "Σ t / Σ d over recoveries",
  ["speed"], E)
X("execution.rep_fade", "Rep fade", "%", "Last rep pace vs first rep pace (positive = slower).",
  "(pace_last/pace_first − 1) × 100", ["speed"], E)
X("execution.pause_count", "Pauses", "count", "Stops of ≥ 5 s.", "count(non-moving runs ≥ 5 s)", ["speed"], V)
X("execution.paused_time", "Time stopped", "s", "Elapsed minus moving time.", "elapsed − moving", ["speed"], V)
X("execution.moving_ratio", "Moving ratio", "ratio", "Moving time / elapsed time.", "moving/elapsed", ["speed"], V)
X("execution.data_quality", "Data quality score", "0–1", "Weighted score of timestamp regularity, gaps, GPS, HR plausibility, coverage.",
  "Σ wᵢ·cᵢ / Σ wᵢ", ["timestamps"], V)
X("execution.surge_count", "Surges", "count", "Accelerations ≥ 15% above the 60 s trailing mean held ≥ 10 s.",
  "count", ["speed"], E)
X("execution.warmup_duration", "Time to steady HR", "s",
  "Seconds until HR first reaches within 5 bpm of the 10–20 min mean.", "first t with HR ≥ μ₁₀₋₂₀ − 5",
  ["heart_rate"], E, confidence_requirements="≥ 20 min activity.")
X("execution.finish_strength", "Finish strength", "ratio", "Speed in the final 10% of moving time / average speed.",
  "mean(v last 10%) / mean(v)", ["speed"], V)
X("execution.hr_response_lag", "HR response lag", "s",
  "Lag (0–60 s) maximising correlation between speed changes and HR changes.", "argmax_L corr(Δv(t), ΔHR(t+L))",
  ["heart_rate", "speed"], E)
X("execution.steady_share", "Steady-state share", "%", "Share of moving time inside steady segments.",
  "Σ steady / moving × 100", ["speed"], E)
X("execution.target_adherence", "Plan adherence", "%", "Time within target ranges of a planned workout.",
  "Σ1[in target]/Σ steps", ["planned_workout"], P)
X("execution.lap_consistency", "Device lap consistency", "%", "CV of device-recorded lap paces.", "σ/μ × 100",
  ["device_laps"], P)
X("execution.pacing_strategy", "Pacing strategy", "category", "Even / negative / positive / variable pacing classification.",
  "rule on split ratio and pace CV", ["distance"], E)

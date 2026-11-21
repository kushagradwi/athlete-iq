# Metric coverage report

Generated from the live registry. **305 definitions, 171 with calculators.**

| Status | Count |
|---|---|
| implemented_experimental | 81 |
| implemented_validated | 88 |
| pending | 41 |
| requires_history | 3 |
| requires_sensor | 92 |

| Category | Implemented / total |
|---|---|
| Running pace and heart rate | 30 / 30 |
| Biomechanics | 15 / 25 |
| Environmental conditions | 11 / 15 |
| Workout execution | 18 / 20 |
| Training load and fatigue | 22 / 25 |
| Performance progression | 17 / 20 |
| Cross-workout performance relationships | 9 / 20 |
| AI discovery and confidence | 20 / 20 |
| Training readiness | 2 / 15 |
| Injury and movement risk | 5 / 15 |
| Training planning | 0 / 15 |
| Cycling performance | 18 / 25 |
| Swimming performance | 4 / 20 |
| Strength performance | 0 / 20 |
| Sleep and recovery | 0 / 20 |

`implemented_validated` = checked against analytic ground truth in `backend/tests/` (enforced by a test). `implemented_experimental` = implemented, no ground-truth test. `requires_sensor` / `pending` = registered only.

## Running pace and heart rate

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `running.distance` | Distance | m | implemented_validated | d[last] − d[first] |
| `running.moving_time` | Moving time | s | implemented_validated | Σ 1[v̄5 ≥ 0.8] |
| `running.elapsed_time` | Elapsed time | s | implemented_validated | t[last] − t[first] + 1 |
| `running.avg_pace` | Average moving pace | s/km | implemented_validated | moving_s / (distance_m/1000) |
| `running.avg_speed` | Average moving speed | m/s | implemented_validated | distance_m / moving_s |
| `running.max_speed_5s` | Best 5 s speed | m/s | implemented_validated | max over windows of mean(v, 5 s) |
| `running.avg_heart_rate` | Average heart rate | bpm | implemented_validated | mean(HR / moving) |
| `running.max_heart_rate` | Maximum heart rate | bpm | implemented_validated | max(mean(HR, 5 s)) |
| `running.hr_drift` | Heart-rate drift | bpm | implemented_validated | mean(HR₂) − mean(HR₁) after warm-up |
| `running.aerobic_decoupling` | Aerobic decoupling (Pa:HR) | % | implemented_validated | (EF₁ − EF₂)/EF₁ × 100, EF = mean speed / mean HR |
| `running.efficiency_factor` | Efficiency factor | m/min/bpm | implemented_validated | NGP speed (m/min) / mean HR |
| `running.normalized_graded_pace` | Normalised graded pace | s/km | implemented_validated | 1000 / (mean(GAS₃₀⁴))^¼ |
| `running.grade_adjusted_pace` | Grade-adjusted average pace | s/km | implemented_experimental | 1000 / mean(GAS) |
| `running.pace_cv` | Pace variability | % | implemented_validated | σ(v₃₀)/μ(v₃₀) × 100 |
| `running.km_split_cv` | Km split consistency | % | implemented_validated | σ(split)/μ(split) × 100 |
| `running.negative_split_ratio` | Split ratio | ratio | implemented_validated | t(2nd half) / t(1st half); < 1 = negative split |
| `running.fastest_km` | Fastest km split | s | implemented_validated | min(split times) |
| `running.slowest_km` | Slowest km split | s | implemented_validated | max(split moving times) |
| `running.best_1km` | Fastest 1 km | s | implemented_validated | min over i of (t(d_i+1000) − t_i) |
| `running.best_5km` | Fastest 5 km | s | implemented_validated | as best_1km for 5000 m |
| `running.best_10km` | Fastest 10 km | s | implemented_validated | as best_1km for 10 000 m |
| `running.best_pace_5min` | Best 5-min pace | s/km | implemented_validated | 1000 / max(mean(v, 300 s)) |
| `running.best_pace_20min` | Best 20-min pace | s/km | implemented_validated | 1000 / max(mean(v, 1200 s)) |
| `running.cardiac_cost` | Cardiac cost | beats/km | implemented_validated | Σ HR/60 / distance_km |
| `running.time_hr_z1` | Time in HR zone 1 | s | implemented_validated | Σ 1[0 ≤ HR/LTHR < 0.85] |
| `running.time_hr_z2` | Time in HR zone 2 | s | implemented_validated | Σ 1[0.85 ≤ HR/LTHR < 0.9] |
| `running.time_hr_z3` | Time in HR zone 3 | s | implemented_validated | Σ 1[0.9 ≤ HR/LTHR < 0.95] |
| `running.time_hr_z4` | Time in HR zone 4 | s | implemented_validated | Σ 1[0.95 ≤ HR/LTHR < 1.0] |
| `running.time_hr_z5` | Time in HR zone 5 | s | implemented_validated | Σ 1[1.0 ≤ HR/LTHR < 9] |
| `running.longest_steady_segment` | Longest steady segment | s | implemented_validated | max segment duration (steady detector) |

## Cycling performance

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `cycling.avg_power` | Average power | W | implemented_validated | mean(P) |
| `cycling.max_power_5s` | Best 5 s power | W | implemented_validated | max mean(P, 5 s) |
| `cycling.normalized_power` | Normalised power | W | implemented_validated | (mean(P₃₀⁴))^¼ |
| `cycling.variability_index` | Variability index | ratio | implemented_validated | NP/P̄ |
| `cycling.intensity_factor` | Intensity factor | ratio | implemented_validated | NP/FTP |
| `cycling.tss` | Training stress score | AU | implemented_validated | h·IF²·100 |
| `cycling.work_kj` | Work | kJ | implemented_validated | ΣP/1000 |
| `cycling.best_1min_power` | Best 1-min power | W | implemented_validated | max mean(P, 60 s) |
| `cycling.best_5min_power` | Best 5-min power | W | implemented_validated | max mean(P, 300 s) |
| `cycling.best_20min_power` | Best 20-min power | W | implemented_validated | max mean(P, 1200 s) |
| `cycling.ftp_estimate` | FTP estimate (95% of 20 min) | W | implemented_experimental | 0.95·P₂₀ |
| `cycling.watts_per_kg` | Power-to-weight (20 min) | W/kg | implemented_experimental | P₂₀/kg |
| `cycling.efficiency_factor` | Efficiency factor (NP/HR) | W/bpm | implemented_validated | NP/HR̄ |
| `cycling.power_hr_decoupling` | Power:HR decoupling | % | implemented_validated | (EF₁−EF₂)/EF₁×100 |
| `cycling.avg_cadence` | Average pedalling cadence | rpm | implemented_validated | mean(cad>0) |
| `cycling.coasting_share` | Coasting share | % | implemented_experimental | Σ1[P=0 ∧ moving]/moving |
| `cycling.avg_speed` | Average moving speed | m/s | implemented_validated | d/t |
| `cycling.vam` | Climbing rate (VAM) | m/h | implemented_experimental | Σgain/Σt (g>3%) |
| `cycling.critical_power` | Critical power | W | requires_history | P = W′/t + CP |
| `cycling.w_prime` | W′ | kJ | requires_history | W′ intercept |
| `cycling.w_prime_balance_min` | Minimum W′ balance | kJ | pending | Skiba 2012 |
| `cycling.left_right_balance` | Left/right balance | % left | requires_sensor | device |
| `cycling.torque_effectiveness` | Torque effectiveness | % | requires_sensor | device |
| `cycling.pedal_smoothness` | Pedal smoothness | % | requires_sensor | device |
| `cycling.cda_estimate` | Aero drag area estimate | m² | pending | VE |

## Swimming performance

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `swimming.avg_pace_100m` | Average pace per 100 m | s/100m | implemented_experimental | see description |
| `swimming.total_distance` | Swim distance | m | implemented_experimental | see description |
| `swimming.moving_time` | Swim moving time | s | implemented_experimental | see description |
| `swimming.avg_heart_rate` | Swim average HR | bpm | implemented_experimental | see description |
| `swimming.swolf` | SWOLF | score | requires_sensor | see description |
| `swimming.stroke_rate` | Stroke rate | spm | requires_sensor | see description |
| `swimming.distance_per_stroke` | Distance per stroke | m | requires_sensor | see description |
| `swimming.stroke_count_per_length` | Strokes per length | count | requires_sensor | see description |
| `swimming.stroke_type_mix` | Stroke type mix | % | requires_sensor | see description |
| `swimming.css` | Critical swim speed | s/100m | requires_history | see description |
| `swimming.css_pace_share` | Time near CSS | % | requires_sensor | see description |
| `swimming.rest_interval_share` | Rest interval share | % | requires_sensor | see description |
| `swimming.pace_consistency` | Length pace consistency | % | requires_sensor | see description |
| `swimming.kick_set_share` | Kick-set share | % | requires_sensor | see description |
| `swimming.open_water_sighting_cost` | Open-water navigation cost | % | pending | see description |
| `swimming.swim_tss` | Swim stress score | AU | requires_sensor | see description |
| `swimming.fatigue_index` | Swim fatigue index | % | requires_sensor | see description |
| `swimming.turn_time` | Turn time | s | requires_sensor | see description |
| `swimming.breath_pattern` | Breathing pattern | category | requires_sensor | see description |
| `swimming.pool_length_detected` | Pool length | m | pending | see description |

## Biomechanics

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `biomechanics.avg_cadence` | Average cadence | spm | implemented_validated | mean(cad / moving) |
| `biomechanics.cadence_cv` | Cadence stability | % | implemented_validated | σ/μ × 100 |
| `biomechanics.cadence_drift` | Cadence drift | spm | implemented_validated | mean(cad Q4) − mean(cad Q1) |
| `biomechanics.avg_stride_length` | Average stride (step) length | m | implemented_validated | mean(v/(cad/60)) |
| `biomechanics.stride_length_cv` | Step-length variability | % | implemented_experimental | σ/μ × 100 |
| `biomechanics.stride_length_drift` | Step-length drift | % | implemented_experimental | (SL Q4 / SL Q1 − 1) × 100 |
| `biomechanics.cadence_speed_slope` | Cadence response to speed | spm per m/s | implemented_experimental | β in cad = α + β·v |
| `biomechanics.stride_speed_slope` | Step-length response to speed | m per m/s | implemented_experimental | β in SL = α + β·v |
| `biomechanics.total_steps` | Total steps | steps | implemented_validated | Σ cad/60 |
| `biomechanics.avg_ground_contact` | Ground contact time | ms | requires_sensor | mean(GCT) |
| `biomechanics.ground_contact_drift` | Ground contact drift | ms | requires_sensor | mean Q4 − mean Q1 |
| `biomechanics.avg_vertical_oscillation` | Vertical oscillation | mm | requires_sensor | mean(VO) |
| `biomechanics.vertical_ratio` | Vertical ratio | % | requires_sensor | VO / SL × 100 |
| `biomechanics.vertical_oscillation_drift` | Vertical oscillation drift | mm | requires_sensor | mean Q4 − mean Q1 |
| `biomechanics.duty_factor` | Duty factor | % | requires_sensor | GCT / (60000/cad) × 100 |
| `biomechanics.gct_balance` | Ground contact balance | % left | requires_sensor | GCT_L / (GCT_L+GCT_R) |
| `biomechanics.leg_spring_stiffness` | Leg spring stiffness | kN/m | pending | F_max / Δl |
| `biomechanics.impact_loading_rate` | Impact loading rate | BW/s | requires_sensor | dF/dt peak |
| `biomechanics.form_power` | Form power | W | requires_sensor | device-reported |
| `biomechanics.cadence_final_quarter` | Cadence in final quarter | spm | implemented_validated | mean(cad Q4) |
| `biomechanics.cadence_at_easy_pace` | Cadence at easy pace | spm | implemented_experimental | mean(cad / steady ∧ v < 0.85·v_thr) |
| `biomechanics.stride_at_threshold_pace` | Step length near threshold pace | m | implemented_experimental | mean(SL / 0.95 ≤ v/v_thr ≤ 1.05) |
| `biomechanics.pelvic_drop` | Pelvic drop | deg | requires_sensor | IMU |
| `biomechanics.foot_strike_pattern` | Foot-strike pattern | category | requires_sensor | IMU |
| `biomechanics.step_rate_variability_late` | Late-run step variability | % | implemented_experimental | σ/μ(cad Q4) × 100 |

## Environmental conditions

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `environment.avg_temperature` | Average temperature | °C | implemented_validated | mean(T) |
| `environment.max_temperature` | Maximum temperature | °C | implemented_validated | max(T) |
| `environment.temperature_range` | Temperature range | °C | implemented_experimental | max − min |
| `environment.elevation_gain` | Elevation gain | m | implemented_validated | Σ climbs ≥ 1 m |
| `environment.elevation_loss` | Elevation loss | m | implemented_validated | Σ descents ≥ 1 m |
| `environment.max_grade` | Steepest climb | % | implemented_experimental | max(grade) |
| `environment.min_grade` | Steepest descent | % | implemented_experimental | min(grade) |
| `environment.avg_abs_grade` | Hilliness | % | implemented_experimental | mean(/grade/) |
| `environment.climb_rate` | Elevation gain per km | m/km | implemented_validated | gain / km |
| `environment.max_altitude` | Highest altitude | m | implemented_validated | max(alt) |
| `environment.pct_time_climbing` | Time climbing | % | implemented_experimental | Σ1[g>2]/moving |
| `environment.heat_index` | Heat index | °C | requires_sensor | Rothfusz regression |
| `environment.wind_component` | Head/tail-wind component | m/s | pending | w·cos(θ) |
| `environment.air_quality` | Air quality index | AQI | pending | external provider |
| `environment.surface_mix` | Surface mix | % | pending | map matching |

## Workout execution

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `execution.interval_count` | Detected work intervals | count | implemented_validated | count(work bouts) |
| `execution.rep_pace_cv` | Rep pace consistency | % | implemented_validated | σ/μ(rep pace) × 100 |
| `execution.rep_duration_cv` | Rep duration consistency | % | implemented_experimental | σ/μ(rep s) × 100 |
| `execution.work_rest_ratio` | Work:rest ratio | ratio | implemented_experimental | Σ work / Σ rest |
| `execution.interval_hr_recovery` | Interval HR recovery | bpm | implemented_experimental | mean(HR(end of rep) − HR(+60 s)) |
| `execution.avg_work_pace` | Average work-interval pace | s/km | implemented_experimental | Σ t / Σ d over reps |
| `execution.avg_recovery_pace` | Average recovery pace | s/km | implemented_experimental | Σ t / Σ d over recoveries |
| `execution.rep_fade` | Rep fade | % | implemented_experimental | (pace_last/pace_first − 1) × 100 |
| `execution.pause_count` | Pauses | count | implemented_validated | count(non-moving runs ≥ 5 s) |
| `execution.paused_time` | Time stopped | s | implemented_validated | elapsed − moving |
| `execution.moving_ratio` | Moving ratio | ratio | implemented_validated | moving/elapsed |
| `execution.data_quality` | Data quality score | 0–1 | implemented_validated | Σ wᵢ·cᵢ / Σ wᵢ |
| `execution.surge_count` | Surges | count | implemented_experimental | count |
| `execution.warmup_duration` | Time to steady HR | s | implemented_experimental | first t with HR ≥ μ₁₀₋₂₀ − 5 |
| `execution.finish_strength` | Finish strength | ratio | implemented_validated | mean(v last 10%) / mean(v) |
| `execution.hr_response_lag` | HR response lag | s | implemented_experimental | argmax_L corr(Δv(t), ΔHR(t+L)) |
| `execution.steady_share` | Steady-state share | % | implemented_experimental | Σ steady / moving × 100 |
| `execution.target_adherence` | Plan adherence | % | pending | Σ1[in target]/Σ steps |
| `execution.lap_consistency` | Device lap consistency | % | pending | σ/μ × 100 |
| `execution.pacing_strategy` | Pacing strategy | category | implemented_experimental | rule on split ratio and pace CV |

## Training load and fatigue

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `load.trimp_banister` | TRIMP (Banister) | AU | implemented_validated | Σ Δt·HRr·0.64·e^(1.92·HRr), HRr = (HR−rest)/(max−rest) |
| `load.trimp_edwards` | TRIMP (Edwards) | AU | implemented_validated | Σ minutes(zone k)·k |
| `load.trimp_lucia` | TRIMP (Lucia) | AU | implemented_experimental | Σ minutes·w |
| `load.hrtss` | hrTSS | AU | implemented_validated | TRIMP / TRIMP(1 h @ LTHR) × 100 |
| `load.rtss` | rTSS | AU | implemented_validated | moving_h · (v_NGP/v_thr)² · 100 |
| `load.intensity_factor` | Intensity factor | ratio | implemented_validated | v_NGP / v_thr |
| `load.time_above_lthr` | Time at or above LTHR | s | implemented_validated | Σ 1[HR ≥ LTHR] |
| `load.energy_kcal` | Energy expenditure | kcal | implemented_experimental | device / 1.036·kg·km |
| `load.session_load` | Session load | AU | implemented_validated | rTSS ?? hrTSS |
| `load.atl` | Acute training load (ATL) | AU/day | implemented_experimental | ATLₜ = ATLₜ₋₁ + (Lₜ − ATLₜ₋₁)/7 |
| `load.ctl` | Chronic training load (CTL) | AU/day | implemented_experimental | CTLₜ = CTLₜ₋₁ + (Lₜ − CTLₜ₋₁)/42 |
| `load.tsb` | Training stress balance (TSB) | AU/day | implemented_experimental | CTL − ATL |
| `load.acwr` | Acute:chronic workload ratio | ratio | implemented_experimental | Σ₇L / (Σ₂₈L/4) |
| `load.monotony` | Training monotony | ratio | implemented_experimental | μ₇/σ₇ |
| `load.strain` | Training strain | AU | implemented_experimental | Σ₇L · monotony |
| `load.weekly_load` | 7-day load | AU | implemented_experimental | Σ₇L |
| `load.weekly_distance` | 7-day distance | m | implemented_experimental | Σ₇d |
| `load.ctl_ramp` | Fitness ramp rate | AU/week | implemented_experimental | CTLₜ − CTLₜ₋₇ |
| `load.low_intensity_share` | Low-intensity share | % | implemented_validated | (Z1+Z2)/Σ zones |
| `load.high_intensity_share` | High-intensity share | % | implemented_validated | (Z4+Z5)/Σ zones |
| `load.load_per_km` | Load density | AU/km | implemented_experimental | load / km |
| `load.aerobic_training_effect` | Aerobic training effect (estimate) | 1–5 | implemented_experimental | 1 + 4·(1 − e^(−TRIMP/150)) |
| `load.anaerobic_training_effect` | Anaerobic training effect | 1–5 | pending | proprietary in devices |
| `load.epoc_estimate` | EPOC estimate | ml/kg | pending | requires VO2 model |
| `load.recovery_time_estimate` | Recovery time estimate | h | pending | requires validated recovery model |

## Performance progression

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `progression.ef_vs_baseline` | Efficiency vs personal baseline | z | implemented_experimental | (EF − median)/(1.4826·MAD) |
| `progression.ef_trend_28d` | Efficiency trend (28 d) | %/week | implemented_experimental | Theil–Sen(EF ~ days) × 7 / median EF × 100 |
| `progression.pace_at_reference_hr` | Pace at reference HR | s/km | implemented_experimental | Huber RLM pace ~ HR, evaluated at 0.8·LTHR |
| `progression.hr_at_reference_pace` | HR at reference pace | bpm | implemented_experimental | Huber RLM HR ~ speed |
| `progression.pace_duration_prs` | Pace-duration records set | count | implemented_validated | Σ 1[best_d > prior best_d] |
| `progression.best_5km_change` | 5 km best vs previous best | s | implemented_experimental | best5k − prior best5k |
| `progression.decoupling_trend` | Decoupling trend | pp/week | implemented_experimental | Theil–Sen |
| `progression.cadence_trend` | Cadence trend | spm/week | implemented_experimental | Theil–Sen |
| `progression.weekly_volume_trend` | Weekly volume trend | % | implemented_experimental | (μ₄ − μ₄′)/μ₄′ × 100 |
| `progression.long_run_trend` | Long-run trend | % | implemented_experimental | ratio − 1 |
| `progression.split_consistency_trend` | Split consistency trend | pp | implemented_experimental | median diff |
| `progression.critical_speed` | Critical speed | m/s | implemented_experimental | d = D′ + CS·t, OLS |
| `progression.d_prime` | D′ (anaerobic distance capacity) | m | implemented_experimental | D′ from OLS |
| `progression.vo2max_estimate` | VO₂max estimate | ml/kg/min | pending | not implemented |
| `progression.threshold_pace_estimate` | Threshold pace estimate | s/km | pending | requires validated detector |
| `progression.race_prediction_10k` | 10 km race prediction | s | pending | t₂ = t₁(d₂/d₁)^1.06 |
| `progression.durability_trend` | Durability index trend | points/week | implemented_experimental | Theil–Sen |
| `progression.aerobic_index_trend` | Aerobic Efficiency Index trend | points/week | implemented_experimental | Theil–Sen |
| `progression.longest_hold_record` | Longest hold at pace (record) | s | implemented_experimental | max over bands |
| `progression.consistency_streak` | Training consistency streak | weeks | implemented_experimental | count |

## Sleep and recovery

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `recovery.sleep_duration` | Sleep duration | h | requires_sensor | device or survey |
| `recovery.sleep_efficiency` | Sleep efficiency | % | requires_sensor | device or survey |
| `recovery.deep_sleep_share` | Deep sleep share | % | requires_sensor | device or survey |
| `recovery.rem_share` | REM share | % | requires_sensor | device or survey |
| `recovery.sleep_latency` | Sleep latency | min | requires_sensor | device or survey |
| `recovery.awakenings` | Awakenings | count | requires_sensor | device or survey |
| `recovery.sleep_regularity` | Sleep regularity index | 0–100 | requires_sensor | device or survey |
| `recovery.overnight_hrv` | Overnight HRV (rMSSD) | ms | requires_sensor | device or survey |
| `recovery.overnight_rhr` | Overnight resting HR | bpm | requires_sensor | device or survey |
| `recovery.hrv_7d_baseline_ratio` | HRV vs 7-day baseline | ratio | requires_sensor | device or survey |
| `recovery.rhr_7d_baseline_delta` | RHR vs 7-day baseline | bpm | requires_sensor | device or survey |
| `recovery.respiratory_rate_night` | Night respiratory rate | brpm | requires_sensor | device or survey |
| `recovery.skin_temp_deviation` | Skin temperature deviation | °C | requires_sensor | device or survey |
| `recovery.sleep_debt_7d` | 7-day sleep debt | h | requires_sensor | device or survey |
| `recovery.nap_minutes` | Naps | min | requires_sensor | device or survey |
| `recovery.subjective_recovery` | Subjective recovery | 1–5 | requires_sensor | device or survey |
| `recovery.muscle_soreness` | Muscle soreness | 0–10 | requires_sensor | device or survey |
| `recovery.post_session_hr_recovery` | Post-session HR recovery | bpm | requires_sensor | device or survey |
| `recovery.time_to_rhr_baseline` | Time to RHR baseline | h | requires_sensor | device or survey |
| `recovery.recovery_status` | Recovery status | category | requires_sensor | device or survey |

## Training readiness

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `readiness.days_since_last_activity` | Days since last activity | days | implemented_experimental | Δ days |
| `readiness.days_since_hard_session` | Days since hard session | days | implemented_experimental | Δ days |
| `readiness.pre_session_tsb` | Freshness before session | AU/day | pending | CTL−ATL |
| `readiness.resting_hr_deviation` | Resting HR deviation | AU | requires_sensor | deviation from baseline |
| `readiness.hrv_deviation` | HRV deviation | AU | requires_sensor | deviation from baseline |
| `readiness.sleep_debt` | Sleep debt | AU | requires_sensor | deviation from baseline |
| `readiness.soreness_score` | Soreness score | AU | requires_sensor | deviation from baseline |
| `readiness.mood_score` | Mood score | AU | requires_sensor | deviation from baseline |
| `readiness.stress_score` | Life-stress score | AU | requires_sensor | deviation from baseline |
| `readiness.readiness_composite` | Readiness composite | AU | requires_sensor | deviation from baseline |
| `readiness.orthostatic_hr` | Orthostatic HR response | AU | requires_sensor | deviation from baseline |
| `readiness.grip_or_jump_test` | Neuromuscular test | AU | requires_sensor | deviation from baseline |
| `readiness.illness_flag` | Illness flag | AU | requires_sensor | deviation from baseline |
| `readiness.travel_jetlag` | Travel / jet-lag load | AU | requires_sensor | deviation from baseline |
| `readiness.planned_session_fit` | Planned session fit | category | pending | rules |

## Strength performance

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `strength.total_volume_load` | Volume load | kg | requires_sensor | see description |
| `strength.total_sets` | Sets | count | requires_sensor | see description |
| `strength.total_reps` | Reps | count | requires_sensor | see description |
| `strength.estimated_1rm` | Estimated 1RM | kg | requires_sensor | see description |
| `strength.relative_strength` | Relative strength | ×BW | requires_sensor | see description |
| `strength.session_rpe_load` | Session-RPE load | AU | requires_sensor | see description |
| `strength.avg_rest_interval` | Average rest | s | requires_sensor | see description |
| `strength.time_under_tension` | Time under tension | s | requires_sensor | see description |
| `strength.bar_velocity_mean` | Mean bar velocity | m/s | requires_sensor | see description |
| `strength.velocity_loss` | Velocity loss | % | requires_sensor | see description |
| `strength.muscle_group_balance` | Muscle-group balance | ratio | requires_sensor | see description |
| `strength.progressive_overload_rate` | Overload rate | %/week | requires_sensor | see description |
| `strength.pr_count` | Strength PRs | count | requires_sensor | see description |
| `strength.density` | Training density | kg/min | requires_sensor | see description |
| `strength.rir_accuracy` | RIR accuracy | reps | requires_sensor | see description |
| `strength.unilateral_asymmetry` | Unilateral asymmetry | % | requires_sensor | see description |
| `strength.power_output` | Power output | W | requires_sensor | see description |
| `strength.hr_during_sets` | HR during sets | bpm | requires_sensor | see description |
| `strength.recovery_between_sets` | HR recovery between sets | bpm | requires_sensor | see description |
| `strength.weekly_hard_sets` | Weekly hard sets per muscle | count | requires_sensor | see description |

## Injury and movement risk

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `risk.load_spike_flag` | Load spike flag | flag | implemented_experimental | 1[ACWR > 1.5] |
| `risk.weekly_distance_jump` | Weekly distance jump | % | implemented_experimental | (d₇/d₇′ − 1) × 100 |
| `risk.long_run_share` | Long-run share of week | % | implemented_experimental | d / Σ₇d |
| `risk.consecutive_hard_days` | Consecutive hard days | days | implemented_experimental | count |
| `risk.late_form_change` | Late-run form change | % | implemented_experimental | ΔSL Q4 vs Q1 |
| `risk.asymmetry_gct` | GCT asymmetry | AU | requires_sensor | pending |
| `risk.impact_trend` | Impact trend | AU | requires_sensor | pending |
| `risk.pain_report_trend` | Pain report trend | AU | requires_sensor | pending |
| `risk.injury_history_weight` | Injury history weight | AU | requires_sensor | pending |
| `risk.shoe_mileage` | Shoe mileage | AU | requires_sensor | pending |
| `risk.surface_change` | Sudden surface change | AU | requires_sensor | pending |
| `risk.downhill_load` | Downhill eccentric load | AU | pending | pending |
| `risk.bone_stress_load` | Bone-loading index | AU | requires_sensor | pending |
| `risk.sleep_risk_modifier` | Sleep modifier | AU | requires_sensor | pending |
| `risk.injury_risk_model` | Injury risk model | AU | pending | pending |

## Training planning

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `planning.next_long_run_distance` | Suggested long-run distance | varies | pending | planning module (not yet built) |
| `planning.easy_pace_range` | Easy pace range | varies | pending | planning module (not yet built) |
| `planning.tempo_pace_range` | Tempo pace range | varies | pending | planning module (not yet built) |
| `planning.interval_pace_targets` | Interval pace targets | varies | pending | planning module (not yet built) |
| `planning.weekly_volume_target` | Weekly volume target | varies | pending | planning module (not yet built) |
| `planning.taper_plan` | Taper plan | varies | pending | planning module (not yet built) |
| `planning.session_mix` | Session mix | varies | pending | planning module (not yet built) |
| `planning.recovery_day_placement` | Recovery day placement | varies | pending | planning module (not yet built) |
| `planning.race_pacing_plan` | Race pacing plan | varies | pending | planning module (not yet built) |
| `planning.fuel_plan` | Fuelling plan | varies | pending | planning module (not yet built) |
| `planning.heat_adjusted_pace` | Heat-adjusted pace | varies | pending | planning module (not yet built) |
| `planning.altitude_adjusted_pace` | Altitude-adjusted pace | varies | pending | planning module (not yet built) |
| `planning.repeat_effort_experiment` | Repeat-effort experiment | varies | pending | planning module (not yet built) |
| `planning.cadence_drill_target` | Cadence drill target | varies | pending | planning module (not yet built) |
| `planning.deload_week_signal` | Deload week signal | varies | pending | planning module (not yet built) |

## Cross-workout performance relationships

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `cross.temperature_hr_cost` | Heat cost on heart rate | beats/km per °C | implemented_experimental | Theil–Sen(cc ~ T) |
| `cross.prior_day_load_vs_decoupling` | Yesterday's load vs today's decoupling | Spearman ρ | implemented_experimental | Spearman |
| `cross.tsb_vs_efficiency` | Freshness vs efficiency | Spearman ρ | implemented_experimental | Spearman |
| `cross.time_of_day_efficiency` | Time-of-day efficiency gap | % | implemented_experimental | median ratio − 1 |
| `cross.elevation_vs_pace_cost` | Climb cost on pace | s/km per 10 m/km | implemented_experimental | Theil–Sen |
| `cross.weekly_load_vs_ef` | Weekly load vs efficiency | Spearman ρ | implemented_experimental | Spearman |
| `cross.cadence_vs_ef` | Cadence vs efficiency | Spearman ρ | implemented_experimental | Spearman |
| `cross.long_run_vs_next_ef` | Long run → next-run efficiency | % | implemented_experimental | mean ratio − 1 |
| `cross.interval_vs_tempo_progress` | Intervals vs tempo progression | ratio | pending | slope ratio |
| `cross.sleep_vs_pace` | Sleep vs pace | Spearman ρ | requires_sensor | Spearman |
| `cross.hrv_vs_efficiency` | HRV vs efficiency | Spearman ρ | requires_sensor | Spearman |
| `cross.strength_vs_durability` | Strength work vs durability | Spearman ρ | requires_sensor | Spearman |
| `cross.surface_vs_cadence` | Surface vs cadence | spm | pending | difference |
| `cross.shoe_vs_efficiency` | Shoe vs efficiency | % | pending | difference |
| `cross.cycling_to_running_transfer` | Cycling → running transfer | Spearman ρ | pending | Spearman |
| `cross.weather_wind_vs_pace` | Wind vs pace | s/km per m/s | pending | regression |
| `cross.altitude_exposure_vs_hr` | Altitude exposure vs HR | bpm per 1000 m | pending | regression |
| `cross.recovery_days_vs_quality` | Recovery days vs session quality | Spearman ρ | implemented_experimental | Spearman |
| `cross.menstrual_phase_vs_hr` | Cycle phase vs HR | bpm | requires_sensor | difference |
| `cross.nutrition_vs_durability` | Fuelling vs durability | Spearman ρ | requires_sensor | Spearman |

## AI discovery and confidence

| metric_id | name | unit | status | formula |
|---|---|---|---|---|
| `discovery.count` | Discoveries generated | count | implemented_validated | count |
| `discovery.top_significance` | Top significance | 0–1 | implemented_validated | max(score) |
| `discovery.mean_confidence` | Mean discovery confidence | 0–1 | implemented_validated | mean |
| `discovery.personal_records` | Personal records | count | implemented_validated | count |
| `discovery.emerging_patterns` | Emerging patterns | count | implemented_validated | count |
| `discovery.confirmed_trends` | Confirmed trends | count | implemented_validated | count |
| `discovery.anomalies` | Anomalies | count | implemented_validated | count |
| `discovery.new_observations` | New observations | count | implemented_validated | count |
| `discovery.comparable_efforts` | Comparable efforts found | count | implemented_experimental | count |
| `discovery.match_quality` | Comparable match quality | 0–1 | implemented_experimental | mean |
| `discovery.baseline_sample_size` | Baseline sample size | activities | implemented_validated | count |
| `discovery.evidence_items` | Evidence items | count | implemented_validated | count |
| `discovery.detectors_run` | Detectors run | count | implemented_validated | count |
| `discovery.detectors_abstained` | Detectors abstained | count | implemented_validated | count |
| `discovery.data_quality_weight` | Data-quality weight | 0–1 | implemented_validated | activity quality score |
| `discovery.ai_claims_verified` | AI claims verified | ratio | implemented_experimental | verified / total |
| `discovery.ai_claims_rejected` | AI claims rejected | count | implemented_experimental | count |
| `discovery.goal_relevance` | Goal relevance | 0–1 | implemented_validated | mean |
| `discovery.novelty` | Novelty | 0–1 | implemented_validated | mean |
| `discovery.actionability` | Actionability | 0–1 | implemented_validated | mean |

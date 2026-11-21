# ATHLETE IQ — Implementation plan & contracts

## 0. Starting point
- New repository. Reuses ideas (not code verbatim) from the `~/telemetry-coach` prototype:
  1 Hz resampling, pace-band "longest hold", lowest-HR-at-pace windows, GoldenCheetah JSON export.
- Environment facts that shape decisions: Docker Desktop available; host port 5432 is taken
  (Postgres exposed on **5433**); no Gemini key; no GoldenCheetah install; no real device FIT file
  on this machine; ~26 GB free disk (keep images slim).

## 1. Architectural risks & decisions
| Risk | Decision |
|---|---|
| 305 metrics invite filler | Registry entries ≠ calculations. Each entry has an honest `status`; only tested ones are `implemented_validated`. |
| LLM hallucinating numbers | LLM never computes. It receives discovery/metric objects through tools; every claim must cite ids; a numeric guard drops claims containing numbers absent from cited evidence. |
| GoldenCheetah unavailable / no upload API | Separate adapter. Auto-import folder + documented read-only REST API (port 12021). Standalone engine is authoritative; GC values stored side-by-side for comparison only. |
| Comparing dissimilar efforts | Comparable-effort matcher with explicit tolerances (pace ±3 %, duration ±30 %, grade ±1 %, temperature ±4 °C when both known, quality ≥ 0.7). No match → no comparison claim. |
| One-off changes sold as fitness gains | Classification ladder: NEW_OBSERVATION → PERSONAL_RECORD → EMERGING_PATTERN (≥2 of last 3 comparable better) → CONFIRMED_TREND (Mann-Kendall p<0.05, n≥6) ; ANOMALY for robust |z|>2.5 the wrong way. |
| Recomputing history on each upload | `athlete_baselines` keeps incremental aggregates (per-metric sample arrays capped at 200 + pace-duration curve); segments stored once per activity in `effort_segments`. |
| Microservice sprawl | One FastAPI app + one Dramatiq worker (same codebase). `JOB_MODE=inline` runs jobs synchronously for tests/dev. |
| Disk budget | python:3.12-slim and node:22-alpine images; MinIO optional (`STORAGE=local` fallback). |

## 2. Canonical telemetry schema (1 Hz, all nullable)
`elapsed_s` (int, key) · `timestamp` · `distance_m` · `lat` · `lon` · `altitude_m` · `speed_ms` ·
`pace_s_km` · `heart_rate` · `cadence_spm` · `power_w` · `temperature_c` · `grade_pct` ·
`vertical_oscillation_mm` · `ground_contact_ms` · `stride_length_m` · `respiration_rate` · `calories`
+ `moving` (bool) and `gap_flag` (recording gap).

Per-activity `channel_provenance`: `{field: measured | derived | estimated | unavailable}`.
Rules: raw samples are resampled to 1 Hz with linear interpolation only across gaps ≤ 10 s;
longer gaps stay null and are reported. Running cadence reported per leg is doubled (recorded as a
quality note). Speed is derived from distance when not measured; distance from GPS when not measured.

Data quality score (0–1) = weighted mean of: timestamp regularity, HR plausibility, GPS jump rate,
duplicate rate, gap fraction, sensor coverage. Components stored, not just the score.

## 3. Metric registry
`MetricDefinition`: metric_id (`sport.name`), name, category, sport, description, formula,
required_inputs, unit, aggregation_method, supported_timeframes, calculation_method
(`activity` | `history` | `external`), algorithm_version, validation_rules, limitations,
confidence_requirements, status (`implemented_validated` | `implemented_experimental` | `pending` |
`requires_sensor` | `requires_history`), calculator (python callable or None).

`MetricResult`: metric_id, value (float|None), unit, state (CALCULATED | INSUFFICIENT_DATA |
NOT_APPLICABLE | INVALID_INPUT | ESTIMATED), source (calculated | goldencheetah | estimated),
quality (0–1), detail (JSON), algorithm_version.

Allocation (exactly 305): running 30 · cycling 25 · swimming 20 · biomechanics 25 · environment 15 ·
workout execution 20 · training load 25 · progression 20 · sleep/recovery 20 · readiness 15 ·
strength 20 · injury/movement risk 15 · planning 15 · cross-workout 20 · AI discovery 20.

First calculations (target ≥ 50, all in `metrics/calculators.py`, each with a ground-truth test):
distance, moving/elapsed time, avg pace/speed, best 5 s speed, avg/max HR, HR drift, aerobic
decoupling, efficiency factor, NGP, GAP, pace CV, km-split CV, negative-split ratio, fastest/slowest km,
best 1 km/5 km/10 km, best 5/20/60-min pace, HR-zone times (5), longest steady segment, cardiac cost,
cadence avg/CV/drift, stride length, GCT, vertical oscillation, elevation gain/loss, max grade, avg
temperature, interval count, rep-pace CV, work:rest ratio, interval HR recovery, pause count, data
quality, Banister/Edwards TRIMP, hrTSS, rTSS, IF, time above LTHR, ATL/CTL/TSB, ACWR, monotony, strain,
EF 28-day trend, pace-duration PR count, discovery count/confidence.

## 4. Performance indexes (personal-baseline, 0–100, 50 = your median)
score = clip(50 + 15·robust_z, 0, 100) per component, combined as weighted mean of available
components; confidence = f(baseline n, data quality, component coverage). < 3 baseline activities →
INSUFFICIENT_DATA (components still shown). Versioned `index-v1`. Not physiological standards.

## 5. Discovery contract
```
Discovery{discovery_id, athlete_id, activity_id, type, classification, title, description,
 observed_value{}, baseline_value{}, improvement{}, confidence, significance_score,
 ranking{novelty, magnitude, confidence, goal_relevance, actionability}, evidence[],
 limitations[], recommended_experiment{}, algorithm_version}
Evidence{kind: metric|segment|activity|statistic, ref_id, label, value, unit, detail}
```
Detectors are plugins: `@register` class with `type`, `version`, `detect(ctx) -> list[Discovery]`.
`ctx` exposes the current activity frame, its metrics/segments, and history repositories.
Ranking: novelty .20, magnitude .25, confidence .25, goal relevance .15, actionability .15 (env-configurable).

## 6. AI layer
Gemini (`google-genai`) with function calling over 7 tools: get_activity_metrics,
get_activity_charts, get_historical_comparisons, get_personal_records, get_discoveries,
get_performance_indexes, get_training_history. Structured output
`{answer, claims[{text, evidence_ids[]}], insufficient_evidence}`; server validates ids and numbers.
No key → deterministic fallback that answers the supported question intents from the same tools.

## 7. Test strategy
Synthetic generators with known ground truth (constant pace, linear HR rise, fixed intervals, known
distance, injected GPS jump, duplicates, pauses, unit errors). Parser tests per format (FIT written by
our own minimal encoder, TCX, GPX, CSV). Metric tests assert values within tolerance. Detector tests
build histories where the answer is known. API tests on SQLite with inline jobs; end-to-end on
Docker Compose Postgres. Frontend: Vitest component tests.

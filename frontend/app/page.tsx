"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Chart from "./Chart";
import { api, dur, fmt, pace } from "../lib/api";

const SIGNAL = "#ff5a1f", INK = "#f2ede4", MUTE = "#8f8a80", HRC = "#e8556d", GOOD = "#7bd88f";
const CLASS_COLOR: Record<string, string> = { PERSONAL_RECORD: SIGNAL, CONFIRMED_TREND: GOOD, EMERGING_PATTERN: "#f2c14e",
  ANOMALY: HRC, NEW_OBSERVATION: MUTE };
const QUESTIONS = ["What is the longest I have sustained 5:40/km?", "Have I improved aerobic efficiency?",
  "What was my most consistent 10K?", "Which workout showed my best durability?",
  "What is one improvement I probably haven't noticed?", "What should I focus on in my next session?"];

export default function Home() {
  const [athletes, setAthletes] = useState<any[]>([]);
  const [athlete, setAthlete] = useState<string>("");
  const [acts, setActs] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [sel, setSel] = useState<string>("");
  const [err, setErr] = useState("");

  const loadAthletes = useCallback(async () => {
    const a = await api("/athletes");
    setAthletes(a);
    if (!athlete && a.length) setAthlete(a[a.length - 1].athlete_id);
  }, [athlete]);
  useEffect(() => { loadAthletes().catch((e) => setErr(e.message)); }, []);

  const refresh = useCallback(async () => {
    if (!athlete) return;
    const [a, j] = await Promise.all([api(`/athletes/${athlete}/activities`), api(`/athletes/${athlete}/jobs`)]);
    setActs(a); setJobs(j);
    if (!sel && a.length) setSel(a[0].activity_id);
  }, [athlete, sel]);
  useEffect(() => { setSel(""); }, [athlete]);
  useEffect(() => { refresh().catch((e) => setErr(e.message)); }, [athlete]);
  const pending = jobs.filter((j) => j.status === "queued" || j.status === "running").length;
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => refresh().catch(() => {}), 1500);
    return () => clearInterval(t);
  }, [pending, refresh]);

  async function createAthlete() {
    const name = prompt("Athlete name");
    if (!name) return;
    const a = await api("/athletes", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name }) });
    await loadAthletes(); setAthlete(a.athlete_id);
  }
  async function demo() {
    setErr("");
    const a = await api("/demo", { method: "POST" });
    await loadAthletes(); setAthlete(a.athlete_id);
  }
  async function upload(files: FileList | null) {
    if (!files || !athlete) return;
    setErr("");
    for (const f of Array.from(files)) {
      const fd = new FormData();
      fd.append("athlete_id", athlete); fd.append("file", f);
      try {
        const j = await api("/activities/upload", { method: "POST", body: fd });
        if (j.activity_id && j.status === "done") setSel(j.activity_id);
      } catch (e: any) { setErr(`${f.name}: ${e.message}`); }
    }
    refresh();
  }

  return (
    <main className="mx-auto max-w-[1400px] px-4 md:px-8 pb-24">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line py-6">
        <div>
          <div className="kicker">Performance intelligence</div>
          <h1 className="font-display text-5xl leading-none tracking-tight">ATHLETE <span className="text-signal">IQ</span></h1>
          <p className="mt-1 text-mute italic font-display text-xl">Your performance has patterns. We find them.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={athlete} onChange={(e) => setAthlete(e.target.value)}
            className="bg-panel border border-line rounded px-3 py-2 text-sm">
            {!athletes.length && <option value="">No athletes yet</option>}
            {athletes.map((a) => <option key={a.athlete_id} value={a.athlete_id}>{a.name}</option>)}
          </select>
          <button onClick={createAthlete} className="border border-line rounded px-3 py-2 text-sm hover:border-mute">New athlete</button>
          <button onClick={() => demo().catch((e) => setErr(e.message))} className="bg-signal text-black rounded px-3 py-2 text-sm font-medium">Load demo athlete</button>
        </div>
      </header>
      {err && <div className="mt-4 border border-signal/50 text-signal rounded px-3 py-2 text-sm">{err}</div>}

      <div className="grid gap-8 lg:grid-cols-[300px_1fr] mt-6">
        <aside className="space-y-6">
          <Upload disabled={!athlete} onFiles={upload} />
          {pending > 0 && <Jobs jobs={jobs.filter((j) => j.status !== "done")} />}
          {jobs.filter((j) => j.status === "failed").slice(0, 3).map((j) => (
            <div key={j.job_id} className="text-xs text-signal">✕ {j.filename}: {j.error}</div>))}
          <div>
            <div className="kicker mb-2">Activities · {acts.length}</div>
            <ul className="divide-y divide-line border-y border-line max-h-[60vh] overflow-auto">
              {acts.map((a) => (
                <li key={a.activity_id}>
                  <button onClick={() => setSel(a.activity_id)}
                    className={`w-full text-left px-2 py-2 hover:bg-panel ${sel === a.activity_id ? "bg-panel border-l-2 border-signal" : ""}`}>
                    <div className="flex justify-between text-sm"><span>{new Date(a.start_time).toLocaleDateString(undefined, { day: "numeric", month: "short" })} · {a.sport}</span>
                      <span className="num text-mute">{((a.distance_m || 0) / 1000).toFixed(1)} km</span></div>
                    <div className="text-xs text-mute num">{dur(a.moving_s)} {a.discoveries ? <span className="text-signal">· {a.discoveries} discoveries</span> : null}</div>
                  </button>
                </li>))}
            </ul>
          </div>
        </aside>
        <section className="min-w-0">
          {sel ? <Activity id={sel} athlete={athlete} /> : <Empty />}
        </section>
      </div>
      {athlete && <Ask athlete={athlete} activity={sel} />}
    </main>
  );
}

function Empty() {
  return <div className="border border-dashed border-line rounded-lg p-12 text-center text-mute">
    <div className="font-display text-3xl text-ink">Upload a workout to begin.</div>
    <p className="mt-2">FIT, TCX, GPX or CSV. Or load the synthetic demo athlete to see 12 weeks of history analysed.</p>
  </div>;
}

function Upload({ onFiles, disabled }: { onFiles: (f: FileList | null) => void; disabled: boolean }) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFiles(e.dataTransfer.files); }}
      onClick={() => !disabled && input.current?.click()}
      className={`cursor-pointer rounded-lg border border-dashed p-6 text-center transition ${over ? "border-signal bg-signal/5" : "border-line hover:border-mute"} ${disabled ? "opacity-40 pointer-events-none" : ""}`}>
      <input ref={input} type="file" multiple accept=".fit,.tcx,.gpx,.csv" hidden onChange={(e) => onFiles(e.target.files)} />
      <div className="font-display text-2xl">Drop workout files</div>
      <div className="kicker mt-1">FIT · TCX · GPX · CSV · ≤ 100 MB</div>
    </div>
  );
}

function Jobs({ jobs }: { jobs: any[] }) {
  return <div className="space-y-2">
    <div className="kicker">Analysing · {jobs.length}</div>
    {jobs.slice(0, 4).map((j) => (
      <div key={j.job_id} className="text-xs">
        <div className="flex justify-between text-mute"><span className="truncate">{j.filename}</span><span>{j.stage}</span></div>
        <div className="h-1 bg-line rounded mt-1"><div className="h-1 bg-signal rounded" style={{ width: `${(j.progress || 0) * 100}%` }} /></div>
      </div>))}
  </div>;
}

// ---------------------------------------------------------------- activity
function Activity({ id, athlete }: { id: string; athlete: string }) {
  const [a, setA] = useState<any>(null), [c, setC] = useState<any>(null), [d, setD] = useState<any>(null);
  const [ix, setIx] = useState<any[]>([]), [prog, setProg] = useState<any>(null);
  useEffect(() => {
    setA(null); setC(null); setD(null);
    Promise.all([api(`/activities/${id}`), api(`/activities/${id}/charts`), api(`/activities/${id}/discoveries`),
      api(`/activities/${id}/indexes`), api(`/athletes/${athlete}/progression`)])
      .then(([a, c, d, ix, p]) => { setA(a); setC(c); setD(d); setIx(ix); setProg(p); }).catch(() => {});
  }, [id, athlete]);
  if (!a) return <div className="text-mute">Loading…</div>;
  if (a.status !== "analysed") return <div className="text-mute">This activity is {a.status}.</div>;
  const o = a.overview || {};
  const q = a.quality?.score ?? 0;
  const kpis = [
    ["Distance", `${((a.distance_m || 0) / 1000).toFixed(2)} km`], ["Moving time", dur(a.moving_s)],
    ["Avg pace", o["running.avg_pace"]?.value ? `${pace(o["running.avg_pace"].value)}/km` : "–"],
    ["Avg HR", o["running.avg_heart_rate"]?.value ? `${o["running.avg_heart_rate"].value.toFixed(0)} bpm` : "–"],
    ["Calories", o["load.energy_kcal"]?.value ? `${o["load.energy_kcal"].value.toFixed(0)}${o["load.energy_kcal"].state === "ESTIMATED" ? "*" : ""}` : "–"],
    ["Elevation", o["environment.elevation_gain"]?.value != null ? `${o["environment.elevation_gain"].value.toFixed(0)} m` : "–"],
  ];
  return (
    <div className="space-y-10">
      <div>
        <div className="kicker">{a.sport} · {a.source_format.toUpperCase()} · {a.device || "unknown device"}</div>
        <h2 className="font-display text-4xl">{new Date(a.start_time).toLocaleString(undefined, { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}</h2>
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-7 border-y border-line divide-x divide-line">
          {kpis.map(([k, v]) => <div key={k} className="px-3 py-3"><div className="kicker">{k}</div><div className="num text-xl mt-1">{v}</div></div>)}
          <div className="px-3 py-3" title={(a.quality?.issues || []).map((i: any) => `${i.code}: ${i.action}`).join("\n")}>
            <div className="kicker">Data quality</div>
            <div className={`num text-xl mt-1 ${q > .9 ? "text-good" : q > .75 ? "text-warn" : "text-signal"}`}>{(q * 100).toFixed(0)}%</div>
          </div>
        </div>
        {a.thresholds?.estimated?.length > 0 && <p className="text-xs text-mute mt-2">Estimated thresholds: {a.thresholds.estimated.join(", ")} — set yours via the API to sharpen zones and load.</p>}
      </div>

      {d && <Discoveries d={d} />}
      <Indexes ix={ix} />
      {c && <Charts c={c} lthr={a.thresholds?.lthr} prog={prog} />}
      <Explorer id={id} />
      {a.goldencheetah && <p className="text-xs text-mute">GoldenCheetah: {a.goldencheetah.status}{a.goldencheetah.message ? ` — ${a.goldencheetah.message}` : ""}</p>}
    </div>
  );
}

function Discoveries({ d }: { d: any }) {
  const [open, setOpen] = useState<string | null>(null);
  const com = d.commentary;
  return (
    <div>
      <div className="flex items-baseline justify-between border-b border-line pb-2">
        <h3 className="font-display text-3xl">What changed</h3>
        <span className="kicker">{d.top.length + d.more.length} discoveries · top 5 shown</span>
      </div>
      {!d.top.length && <p className="text-mute mt-4">No discovery cleared the evidence bar. Comparisons need comparable earlier sessions.</p>}
      <ol className="mt-2 divide-y divide-line">
        {d.top.map((x: any, i: number) => (
          <li key={x.discovery_id} className="py-4">
            <button className="w-full text-left" onClick={() => setOpen(open === x.discovery_id ? null : x.discovery_id)}>
              <div className="flex gap-4">
                <div className="num text-mute text-sm w-6 pt-1">{String(i + 1).padStart(2, "0")}</div>
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="kicker" style={{ color: CLASS_COLOR[x.classification] }}>{x.classification.replace("_", " ")}</span>
                    <span className="kicker">· significance {(x.significance_score * 100).toFixed(0)} · confidence {(x.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="font-display text-2xl leading-tight mt-1">{x.title}</div>
                  <p className="text-sm text-ink/80 mt-1 max-w-3xl">{x.description}</p>
                  {x.recommended_experiment?.protocol && <p className="text-sm mt-2"><span className="text-signal">Experiment →</span> {x.recommended_experiment.protocol} <span className="text-mute">Success: {x.recommended_experiment.success_criterion}</span></p>}
                </div>
              </div>
            </button>
            {open === x.discovery_id && (
              <div className="ml-10 mt-3 grid md:grid-cols-2 gap-4 text-xs">
                <div>
                  <div className="kicker mb-1">Evidence</div>
                  <table className="w-full num">
                    <tbody>{x.evidence.map((e: any, k: number) => (
                      <tr key={k} className="border-b border-line"><td className="py-1 pr-2 text-mute">{e.kind}</td><td className="pr-2">{e.label}</td>
                        <td className="text-right">{e.value != null ? fmt(e.value, e.unit) : ""}</td></tr>))}</tbody>
                  </table>
                </div>
                <div>
                  <div className="kicker mb-1">Statistics</div>
                  <div className="num text-mute space-y-0.5">
                    {Object.entries(x.improvement || {}).filter(([, v]) => v != null).map(([k, v]: any) => (
                      <div key={k}>{k}: {Array.isArray(v) ? v.map((n: number) => n.toFixed(2)).join(" … ") : typeof v === "number" ? v.toFixed(3) : String(v)}</div>))}
                  </div>
                  <div className="kicker mt-3 mb-1">Limitations</div>
                  <ul className="list-disc ml-4 text-mute">{x.limitations.map((l: string, k: number) => <li key={k}>{l}</li>)}</ul>
                  <div className="text-mute mt-2">id {x.discovery_id.slice(0, 8)} · {x.algorithm_version}</div>
                </div>
              </div>)}
          </li>))}
      </ol>
      {com && (
        <div className="mt-4 border-l-2 border-signal pl-4">
          <div className="kicker">Commentary · {com.model}</div>
          <p className="mt-1">{com.answer}</p>
          {com.suggested_experiment && <p className="text-sm mt-1 text-mute">{com.suggested_experiment}</p>}
          {com.note && <p className="text-xs text-mute mt-1">{com.note}</p>}
        </div>)}
    </div>
  );
}

function Indexes({ ix }: { ix: any[] }) {
  if (!ix.length) return null;
  return (
    <div>
      <h3 className="font-display text-3xl border-b border-line pb-2">Performance indexes <span className="text-base text-mute font-sans">· 50 = your usual</span></h3>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-line border border-line mt-3">
        {ix.map((i) => (
          <div key={i.index_id} className="bg-bg p-3" title={i.interpretation}>
            <div className="kicker">{i.name.replace(" Index", "")}</div>
            <div className="num text-3xl mt-1" style={{ color: i.score == null ? MUTE : i.score >= 55 ? GOOD : i.score <= 45 ? HRC : INK }}>{i.score == null ? "—" : i.score.toFixed(0)}</div>
            <div className="text-xs text-mute">{i.score == null ? "needs ≥ 3 earlier runs" : `confidence ${(i.confidence * 100).toFixed(0)}%`}</div>
          </div>))}
      </div>
    </div>
  );
}

function Charts({ c, lthr, prog }: { c: any; lthr?: number; prog: any }) {
  const s = c.series;
  const x = s.t.map((t: number) => t / 60);
  const zoom = [{ type: "inside" }, { type: "slider", height: 14, bottom: 4, borderColor: "#2a2824", textStyle: { color: MUTE } }];
  const pairs = (a: any[]) => x.map((t: number, i: number) => [t, a[i]]);
  const opts = useMemo(() => {
    const o: Record<string, any> = {};
    o["Pace + HR"] = { legend: {}, dataZoom: zoom, grid: { bottom: 48 }, xAxis: { type: "value", name: "min", min: 0 },
      yAxis: [{ type: "value", inverse: true, axisLabel: { formatter: (v: number) => pace(v) }, scale: true },
        { type: "value", scale: true, splitLine: { show: false } }],
      series: [{ name: "Pace", type: "line", showSymbol: false, data: pairs(s.pace_s_km), lineStyle: { color: SIGNAL, width: 1.4 }, itemStyle: { color: SIGNAL } },
        { name: "Heart rate", type: "line", yAxisIndex: 1, showSymbol: false, data: pairs(s.heart_rate), lineStyle: { color: HRC, width: 1.2 }, itemStyle: { color: HRC },
          markLine: lthr ? { silent: true, symbol: "none", data: [{ yAxis: lthr }], lineStyle: { color: MUTE, type: "dashed" }, label: { formatter: "LTHR", color: MUTE } } : undefined }] };
    o["Elevation"] = { dataZoom: zoom, grid: { bottom: 48 }, xAxis: { type: "value", name: "km" }, yAxis: { type: "value", scale: true, name: "m" },
      series: [{ type: "line", showSymbol: false, areaStyle: { color: "rgba(242,237,228,.08)" }, lineStyle: { color: INK, width: 1 },
        data: s.distance_km.map((d: number, i: number) => [d, s.altitude[i]]) }] };
    o["Cadence"] = { dataZoom: zoom, grid: { bottom: 48 }, xAxis: { type: "value", name: "min" }, yAxis: { type: "value", scale: true, name: "spm" },
      series: [{ type: "line", showSymbol: false, lineStyle: { color: GOOD, width: 1 }, data: pairs(s.cadence) }] };
    o["Km splits"] = { xAxis: { type: "category", data: c.km_splits.map((k: any) => k.label) },
      yAxis: [{ type: "value", inverse: true, scale: true, axisLabel: { formatter: (v: number) => pace(v) } }, { type: "value", scale: true, splitLine: { show: false } }],
      series: [{ type: "bar", data: c.km_splits.map((k: any) => k.seconds), itemStyle: { color: SIGNAL } },
        { type: "line", yAxisIndex: 1, data: c.km_splits.map((k: any) => k.avg_hr?.toFixed(0)), lineStyle: { color: HRC }, itemStyle: { color: HRC } }] };
    if (c.hr_distribution) o["HR distribution"] = { xAxis: { type: "category", name: "bpm", data: c.hr_distribution.bins }, yAxis: { type: "value", name: "min" },
      series: [{ type: "bar", data: c.hr_distribution.minutes, itemStyle: { color: HRC } }] };
    if (c.pace_distribution) o["Pace distribution"] = { xAxis: { type: "category", data: c.pace_distribution.bins.map((b: number) => pace(b)) }, yAxis: { type: "value", name: "min" },
      series: [{ type: "bar", data: c.pace_distribution.minutes, itemStyle: { color: SIGNAL } }] };
    o["vs your bests"] = { legend: {}, xAxis: { type: "category", data: c.pace_duration.map((p: any) => dur(p.duration_s)) },
      yAxis: { type: "value", inverse: true, scale: true, axisLabel: { formatter: (v: number) => pace(v) } },
      series: [{ name: "This run", type: "line", data: c.pace_duration.map((p: any) => p.pace_s_km), lineStyle: { color: SIGNAL }, itemStyle: { color: SIGNAL } },
        { name: "Previous best", type: "line", data: c.pace_duration.map((p: any) => p.previous_best_pace_s_km), lineStyle: { color: MUTE, type: "dashed" }, itemStyle: { color: MUTE } }] };
    if (c.intervals.length) o["Intervals"] = { xAxis: { type: "category", data: c.intervals.map((r: any, i: number) => `${r.kind === "interval" ? "rep" : "rec"} ${i + 1}`) },
      yAxis: { type: "value", inverse: true, scale: true, axisLabel: { formatter: (v: number) => pace(v) } },
      series: [{ type: "bar", data: c.intervals.map((r: any) => ({ value: r.pace_s_km, itemStyle: { color: r.kind === "interval" ? SIGNAL : "#3a3833" } })) }] };
    if (prog?.activities?.length > 1) {
      const pa = prog.activities;
      o["Efficiency over time"] = { legend: {}, xAxis: { type: "time" }, yAxis: [{ type: "value", scale: true, name: "EF" }, { type: "value", scale: true, splitLine: { show: false }, name: "CTL" }],
        series: [{ name: "Efficiency factor", type: "scatter", symbolSize: 5, data: pa.filter((p: any) => p.metrics["running.efficiency_factor"]).map((p: any) => [p.date, p.metrics["running.efficiency_factor"]]), itemStyle: { color: SIGNAL } },
          { name: "Fitness (CTL)", type: "line", yAxisIndex: 1, showSymbol: false, data: pa.filter((p: any) => p.metrics["load.ctl"]).map((p: any) => [p.date, p.metrics["load.ctl"]]), lineStyle: { color: GOOD } }] };
      o["Index progression"] = { legend: {}, xAxis: { type: "time" }, yAxis: { type: "value", min: 0, max: 100 },
        series: ["aerobic_efficiency", "durability", "consistency"].map((k, i) => ({ name: k.replace("_", " "), type: "line", connectNulls: true,
          data: pa.map((p: any) => [p.date, p.indexes[k] ?? null]), lineStyle: { color: [SIGNAL, GOOD, INK][i] }, itemStyle: { color: [SIGNAL, GOOD, INK][i] } })) };
    }
    return o;
  }, [c, prog]);
  const [tab, setTab] = useState("Pace + HR");
  return (
    <div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-b border-line pb-2 items-baseline">
        <h3 className="font-display text-3xl mr-4">Charts</h3>
        {Object.keys(opts).map((k) => <button key={k} onClick={() => setTab(k)} className={`text-sm ${tab === k ? "text-signal" : "text-mute hover:text-ink"}`}>{k}</button>)}
      </div>
      <div className="mt-3"><Chart option={opts[tab] || opts["Pace + HR"]} height={320} /></div>
    </div>
  );
}

function Explorer({ id }: { id: string }) {
  const [rows, setRows] = useState<any[]>([]), [q, setQ] = useState(""), [cat, setCat] = useState(""), [onlyVals, setOnlyVals] = useState(false);
  useEffect(() => { api(`/activities/${id}/metrics`).then((r) => setRows(r.metrics)); }, [id]);
  const cats = Array.from(new Set(rows.map((r) => r.category)));
  const shown = rows.filter((r) => (!cat || r.category === cat) && (!onlyVals || r.value != null) &&
    (!q || (r.metric_id + r.name).toLowerCase().includes(q.toLowerCase())));
  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-3 border-b border-line pb-2">
        <h3 className="font-display text-3xl">Metric explorer</h3>
        <span className="kicker">{rows.filter((r) => r.value != null).length} values · {rows.length} registered</span>
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search 305 metrics…" className="bg-panel border border-line rounded px-3 py-1.5 text-sm flex-1 min-w-48" />
        <select value={cat} onChange={(e) => setCat(e.target.value)} className="bg-panel border border-line rounded px-2 py-1.5 text-sm">
          <option value="">All categories</option>{cats.map((c) => <option key={c}>{c}</option>)}
        </select>
        <label className="text-sm text-mute flex items-center gap-1"><input type="checkbox" checked={onlyVals} onChange={(e) => setOnlyVals(e.target.checked)} /> with values</label>
      </div>
      <div className="max-h-[480px] overflow-auto mt-2 border-y border-line">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-bg"><tr className="kicker text-left"><th className="py-2">Metric</th><th>Category</th><th className="text-right">Value</th><th className="pl-4">State</th><th>Status</th></tr></thead>
          <tbody>{shown.map((r) => (
            <tr key={r.metric_id} className="border-t border-line/60" title={r.detail?.reason || ""}>
              <td className="py-1.5"><div>{r.name}</div><div className="text-xs text-mute num">{r.metric_id}</div></td>
              <td className="text-mute text-xs">{r.category}</td>
              <td className="text-right num">{fmt(r.value, r.unit)}</td>
              <td className="pl-4 text-xs" style={{ color: r.state === "CALCULATED" ? GOOD : r.state === "ESTIMATED" ? "#f2c14e" : MUTE }}>{r.state}</td>
              <td className="text-xs text-mute">{r.status.replace("implemented_", "")}</td>
            </tr>))}</tbody>
        </table>
      </div>
    </div>
  );
}

function Ask({ athlete, activity }: { athlete: string; activity: string }) {
  const [log, setLog] = useState<any[]>([]), [q, setQ] = useState(""), [busy, setBusy] = useState(false);
  async function send(question: string) {
    if (!question.trim()) return;
    setBusy(true); setQ("");
    try {
      const r = await api(`/athletes/${athlete}/ask`, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ question, activity_id: activity || null }) });
      setLog((l) => [...l, { question, r }]);
    } catch (e: any) { setLog((l) => [...l, { question, r: { answer: e.message, claims: [] } }]); }
    setBusy(false);
  }
  return (
    <section className="mt-16 border-t border-line pt-6">
      <h3 className="font-display text-3xl">Ask Athlete IQ</h3>
      <div className="flex flex-wrap gap-2 mt-3">{QUESTIONS.map((x) => <button key={x} onClick={() => send(x)} className="text-xs border border-line rounded-full px-3 py-1 text-mute hover:text-ink hover:border-mute">{x}</button>)}</div>
      <div className="space-y-5 mt-5">{log.map((m, i) => (
        <div key={i}>
          <div className="text-mute text-sm">› {m.question}</div>
          <p className="mt-1">{m.r.answer}</p>
          {m.r.claims?.length > 0 && <ul className="mt-1 space-y-1">{m.r.claims.map((c: any, k: number) => (
            <li key={k} className="text-sm">{c.text} <span className="num text-xs text-mute">[{c.evidence_ids.map((e: string) => e.length > 20 ? e.slice(0, 8) : e).join(", ")}]</span></li>))}</ul>}
          {m.r.suggested_experiment && <p className="text-sm text-signal mt-1">Experiment → {m.r.suggested_experiment}</p>}
          <div className="text-xs text-mute mt-1">{m.r.model}{m.r.validation ? ` · ${m.r.validation.verified}/${m.r.validation.total} claims verified against evidence` : ""}{m.r.insufficient_evidence ? " · insufficient evidence" : ""}</div>
        </div>))}</div>
      <form onSubmit={(e) => { e.preventDefault(); send(q); }} className="flex gap-2 mt-4">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about your training…" className="flex-1 bg-panel border border-line rounded px-3 py-2" />
        <button disabled={busy} className="bg-signal text-black rounded px-4 py-2 font-medium disabled:opacity-50">{busy ? "…" : "Ask"}</button>
      </form>
    </section>
  );
}

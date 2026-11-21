export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/v1${path}`, init);
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.json()).detail ?? msg; } catch {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}

export const pace = (s?: number | null) => {
  if (s == null || !isFinite(s)) return "–";
  const m = Math.floor(s / 60), x = Math.round(s % 60);
  return `${m}:${String(x === 60 ? 0 : x).padStart(2, "0")}`;
};
export const dur = (s?: number | null) => {
  if (s == null) return "–";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
};
export const fmt = (v: any, unit?: string) => {
  if (v == null) return "–";
  if (unit === "s/km") return `${pace(v)}/km`;
  if (unit === "s") return dur(v);
  if (typeof v === "number") return `${Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2)}${unit && unit !== "count" ? " " + unit : ""}`;
  return String(v);
};

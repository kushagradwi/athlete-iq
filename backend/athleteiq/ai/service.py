"""AI layer: Gemini explains deterministic evidence; it never computes metrics.

Flow: (1) tool loop — Gemini requests evidence via the 7 tools; (2) final structured JSON answer;
(3) server-side validation — every claim must cite ids returned by tools, and every number in a claim
must appear in the tool results (±1.5%, pace mm:ss converted to seconds). Failing claims are dropped.
Without GEMINI_API_KEY a deterministic responder answers from the same tools."""
from __future__ import annotations

import json
import logging
import re
import uuid

from sqlalchemy import desc, select

from .. import models as m
from ..config import settings
from .tools import TOOL_SPECS, Tools, json_schema

log = logging.getLogger("athleteiq.ai")

SYSTEM = """You are ATHLETE IQ's performance analyst. You explain an athlete's training data.
Rules:
- Use tools to fetch evidence before answering. Never compute new numbers yourself; only quote numbers that
  appear in tool results.
- Every claim must cite evidence ids: discovery_id, metric_id, activity_id or segment_id from tool results.
- A single session is one observation. Do not call it a confirmed physiological improvement unless the
  discovery classification is CONFIRMED_TREND.
- Never diagnose injury or illness and never give medical advice.
- If the evidence is insufficient, set insufficient_evidence=true and say what data would be needed.
- Recommend specific, measurable experiments (use recommended_experiment from discoveries when present).
- Be concise and concrete; second person."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "claims": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "evidence_ids"]}},
        "suggested_experiment": {"type": "string"},
        "insufficient_evidence": {"type": "boolean"},
    },
    "required": ["answer", "claims", "insufficient_evidence"],
}

NUM = re.compile(r"(?<![\w.])(\d{1,2}):(\d{2})(?!\d)|(?<![\w:])[-+]?\d+(?:\.\d+)?")


# ------------------------------------------------------------------ evidence bookkeeping
def collect(obj, ids: set, nums: list):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.endswith("_id") or k in ("metric_id", "discovery_id", "activity_id", "segment_id", "ref_id"):
                if isinstance(v, str):
                    ids.add(v)
            collect(v, ids, nums)
    elif isinstance(obj, list):
        for v in obj:
            collect(v, ids, nums)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        nums.append(float(obj))
    elif isinstance(obj, str):
        for mt in NUM.finditer(obj):
            nums.extend(_num_variants(mt))


def _num_variants(mt):
    if mt.group(1):
        return [int(mt.group(1)) * 60 + int(mt.group(2))]
    return [float(mt.group(0))]


def _is_date_part(v: float, text: str) -> bool:
    """Numbers inside ISO dates (2026-11-22) are checked as ids/dates, not as metrics."""
    return bool(re.search(r"\d{4}-\d{2}-\d{2}", text)) and float(v).is_integer() and (
        str(int(abs(v))) in re.findall(r"\d{4}|\d{2}", " ".join(re.findall(r"\d{4}-\d{2}-\d{2}", text))))


def number_supported(x: float, pool: list[float]) -> bool:
    for p in pool:
        for cand in (p, p / 60, p * 100, p / 1000, p * 3.6, 1000 / p if p else None):  # unit-presentation variants
            if cand is None:
                continue
            if abs(cand - x) <= max(1.0 if abs(x) >= 10 else 0.05, abs(x) * 0.015):
                return True
    return False


def validate(resp: dict, ids: set, nums: list) -> tuple[dict, dict]:
    kept, rejected = [], []
    for c in resp.get("claims", []) or []:
        cited = [e for e in c.get("evidence_ids", []) if e in ids]
        unsupported = [v for mt in NUM.finditer(c.get("text", "")) for v in _num_variants(mt)
                       if not number_supported(v, nums) and not _is_date_part(v, c.get("text", ""))]
        if not cited:
            rejected.append({**c, "reason": "no valid evidence id"})
        elif unsupported:
            rejected.append({**c, "reason": f"numbers not found in evidence: {unsupported}"})
        else:
            kept.append({**c, "evidence_ids": cited})
    out = dict(resp)
    out["claims"] = kept
    if rejected and not kept:
        out["insufficient_evidence"] = True
    report = {"total": len(kept) + len(rejected), "verified": len(kept), "rejected": len(rejected),
              "rejected_claims": rejected}
    out["validation"] = report
    return out, report


# ------------------------------------------------------------------ Gemini
def gemini_answer(tools: Tools, prompt: str, max_rounds: int = 6) -> tuple[dict, list]:
    from google import genai
    from google.genai import types

    s = settings()
    client = genai.Client(api_key=s.gemini_api_key)
    decls = [types.FunctionDeclaration(name=n, description=d, parameters_json_schema=json_schema(p, r))
             for n, d, p, r in TOOL_SPECS]
    cfg = types.GenerateContentConfig(system_instruction=SYSTEM, tools=[types.Tool(function_declarations=decls)],
                                      automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    calls = []
    for _ in range(max_rounds):
        resp = client.models.generate_content(model=s.gemini_model, contents=contents, config=cfg)
        fcs = resp.function_calls or []
        if not fcs:
            break
        contents.append(resp.candidates[0].content)
        parts = []
        for fc in fcs:
            result = tools.call(fc.name, dict(fc.args or {}))
            calls.append({"tool": fc.name, "args": dict(fc.args or {}), "result": result})
            parts.append(types.Part.from_function_response(name=fc.name, response={"result": result}))
        contents.append(types.Content(role="user", parts=parts))
    final_cfg = types.GenerateContentConfig(system_instruction=SYSTEM, response_mime_type="application/json",
                                            response_json_schema=ANSWER_SCHEMA)
    contents.append(types.Content(role="user", parts=[types.Part.from_text(
        text="Now give the final answer as JSON per the schema, citing only ids that appeared in tool results.")]))
    resp = client.models.generate_content(model=s.gemini_model, contents=contents, config=final_cfg)
    return json.loads(resp.text), calls


# ------------------------------------------------------------------ deterministic fallback
def fp(sec):
    m_, s_ = divmod(int(round(sec)), 60)
    return f"{m_}:{s_:02d}"


def hms(sec):
    h, r = divmod(int(round(sec)), 3600)
    return f"{h}:{r // 60:02d}:{r % 60:02d}" if h else fp(sec)


def parse_pace(q: str):
    mt = re.search(r"(\d{1,2}):(\d{2})", q)
    return int(mt.group(1)) * 60 + int(mt.group(2)) if mt else None


def fallback_answer(tools: Tools, question: str | None, activity_id=None) -> tuple[dict, list]:
    calls = []

    def call(name, **args):
        r = tools.call(name, args)
        calls.append({"tool": name, "args": args, "result": r})
        return r

    q = (question or "").lower()
    if question is None:  # workout commentary
        ds = call("get_discoveries", activity_id=activity_id, limit=5)["discoveries"]
        ds.sort(key=lambda d: -d["significance_score"])
        if not ds:
            return {"answer": "No discoveries cleared the evidence bar for this workout. As more comparable sessions "
                              "accumulate, comparisons become possible.", "claims": [], "insufficient_evidence": True}, calls
        claims = [{"text": f"{d['title']}. {d['description']}", "evidence_ids": [d["discovery_id"]]} for d in ds]
        exp = ds[0]["recommended_experiment"]
        return {"answer": f"{len(ds)} findings from this workout, most significant first.", "claims": claims,
                "suggested_experiment": f"{exp.get('protocol', '')} Success: {exp.get('success_criterion', '')}".strip(),
                "insufficient_evidence": False}, calls

    if "longest" in q and ("pace" in q or parse_pace(q)):
        pr = call("get_personal_records")["longest_holds_by_pace_band"]
        target = parse_pace(q)
        if not pr:
            return _insufficient("No pace holds of ≥ 2 minutes recorded yet."), calls
        if target:
            band = str(target // 10 * 10)
            h = pr.get(band)
            if not h:
                return _insufficient(f"No continuous hold of ≥ 2 min recorded at {fp(target)}/km."), calls
            text = (f"Your longest continuous hold at {fp(int(band))}–{fp(int(band) + 10)}/km is {hms(h['seconds'])}"
                    + (f" at an average of {h['avg_hr']:.0f} bpm" if h.get("avg_hr") else "") + f", on {h['date'][:10]}.")
            return {"answer": text, "claims": [{"text": text, "evidence_ids": [h["activity_id"]]}],
                    "insufficient_evidence": False}, calls
        top = sorted(pr.values(), key=lambda h: -h["seconds"])[:3]
        claims = [{"text": f"{fp(h['band_s_km'][0])}–{fp(h['band_s_km'][1])}/km held for {hms(h['seconds'])} on {h['date'][:10]}.",
                   "evidence_ids": [h["activity_id"]]} for h in top]
        return {"answer": "Your longest continuous holds by pace band:", "claims": claims,
                "insufficient_evidence": False}, calls

    if "last" in q and ("fast" in q or parse_pace(q)):
        target = parse_pace(q)
        hist = call("get_historical_comparisons", metric_id="running.avg_pace", limit=200)["values"]
        if not hist:
            return _insufficient("No runs with pace recorded."), calls
        if target is None:
            target = hist[-1]["value"]
            hist = hist[:-1]
        hit = [h for h in hist if h["value"] <= target]
        if not hit:
            return _insufficient(f"No earlier run averaged {fp(target)}/km or faster."), calls
        h = hit[-1]
        text = f"Your most recent run averaging {fp(target)}/km or faster was on {h['date'][:10]} ({fp(h['value'])}/km average)."
        return {"answer": text, "claims": [{"text": text, "evidence_ids": [h["activity_id"]]}],
                "insufficient_evidence": False}, calls

    if "aerobic" in q or "efficien" in q:
        hist = call("get_historical_comparisons", metric_id="running.efficiency_factor", limit=60)["values"]
        if len(hist) < 4:
            return _insufficient("Needs at least 4 runs with heart rate to assess efficiency."), calls
        from scipy import stats
        x = list(range(len(hist)))
        y = [h["value"] for h in hist]
        tau, p = stats.kendalltau(x, y)
        first, last = y[: len(y) // 3], y[-(len(y) // 3):]
        import numpy as np
        a, b = float(np.median(first)), float(np.median(last))
        verdict = ("a statistically supported upward trend" if (p < 0.05 and tau > 0) else
                   "a downward trend" if (p < 0.05 and tau < 0) else "no statistically clear trend yet")
        text = (f"Across {len(y)} runs your efficiency factor moved from a median of {a:.3f} (earliest third) to {b:.3f} "
                f"(latest third): {verdict} (Kendall tau {tau:.2f}, p {p:.3f}).")
        return {"answer": text, "claims": [{"text": text, "evidence_ids": ["running.efficiency_factor"] +
                                            [hist[0]["activity_id"], hist[-1]["activity_id"]]}],
                "insufficient_evidence": False}, calls

    if "consistent" in q and ("10k" in q or "10 k" in q or "10km" in q):
        hist = call("get_training_history", days=3650)["activities"]
        cands = [a for a in hist if a["distance_m"] >= 10000 and a["metrics"].get("running.km_split_cv") is not None]
        if not cands:
            return _insufficient("No runs of ≥ 10 km with split data."), calls
        a = min(cands, key=lambda a: a["metrics"]["running.km_split_cv"])
        text = (f"Your most consistent 10 km+ run was on {a['date'][:10]}: km splits varied by "
                f"{a['metrics']['running.km_split_cv']:.1f}% over {a['distance_m'] / 1000:.1f} km.")
        return {"answer": text, "claims": [{"text": text, "evidence_ids": [a["activity_id"], "running.km_split_cv"]}],
                "insufficient_evidence": False}, calls

    if "durab" in q:
        best = None
        for a in call("get_training_history", days=3650)["activities"]:
            ix = call("get_performance_indexes", activity_id=a["activity_id"])
            for i in ix.get("indexes", []):
                if i["index_id"] == "durability" and i["score"] is not None and (best is None or i["score"] > best[0]):
                    best = (i["score"], a)
        if not best:
            return _insufficient("Durability Index needs ≥ 3 earlier comparable runs."), calls
        text = f"Your best Durability Index was {best[0]:.1f} on {best[1]['date'][:10]} ({best[1]['distance_m'] / 1000:.1f} km)."
        return {"answer": text, "claims": [{"text": text, "evidence_ids": [best[1]["activity_id"]]}],
                "insufficient_evidence": False}, calls

    if "haven't noticed" in q or "not noticed" in q or "probably" in q or "focus" in q or "next session" in q:
        ds = call("get_discoveries", limit=20)["discoveries"]
        if not ds:
            return _insufficient("No discoveries yet; upload more sessions."), calls
        d = max(ds, key=lambda d: d["significance_score"] * (1.2 if d["type"] not in ("PACE_DURATION_RECORD",) else 1.0))
        exp = d["recommended_experiment"]
        text = f"{d['title']}. {d['description']}"
        return {"answer": text, "claims": [{"text": text, "evidence_ids": [d["discovery_id"]]}],
                "suggested_experiment": f"{exp.get('protocol', '')} Success: {exp.get('success_criterion', '')}",
                "insufficient_evidence": False}, calls

    return _insufficient("Without an AI model configured, I can answer: longest time at a pace (e.g. 'longest at 5:20'), "
                         "when you last ran a pace, aerobic efficiency trend, most consistent 10K, best durability, "
                         "an improvement you may have missed, and what to focus on next."), calls


def _insufficient(msg):
    return {"answer": msg, "claims": [], "insufficient_evidence": True}


# ------------------------------------------------------------------ entry points
def _run(s, athlete_id, question, activity_id, kind):
    tools = Tools(s, athlete_id)
    activity_id = str(activity_id) if activity_id else None
    model = "deterministic-fallback"
    if settings().gemini_api_key:
        prompt = (f"Explain the most meaningful findings for activity {activity_id}." if question is None
                  else question + (f"\n(Current activity: {activity_id})" if activity_id else ""))
        try:
            resp, calls = gemini_answer(tools, prompt)
            model = settings().gemini_model
        except Exception as e:
            log.warning("Gemini failed (%s); using deterministic fallback", e)
            resp, calls = fallback_answer(tools, question, activity_id)
            resp["note"] = f"AI model unavailable ({type(e).__name__}); deterministic answer shown."
    else:
        resp, calls = fallback_answer(tools, question, activity_id)
        resp["note"] = "GEMINI_API_KEY not set; deterministic answer generated from the same evidence tools."
    ids, nums = set(), []
    for c in calls:
        collect(c["result"], ids, nums)
    ids |= {c["args"].get("metric_id") for c in calls if c["args"].get("metric_id")}
    resp, report = validate(resp, ids, nums)
    resp["model"] = model
    conv = m.AiConversation(athlete_id=athlete_id, activity_id=uuid.UUID(activity_id) if activity_id else None, kind=kind, question=question,
                            response=_jsonable(resp),
                            tool_calls=_jsonable([{"tool": c["tool"], "args": c["args"]} for c in calls]), model=model)
    s.add(conv)
    s.flush()
    resp["conversation_id"] = str(conv.id)
    return resp, report


def _jsonable(o):
    return json.loads(json.dumps(o, default=str))


def commentary(s, athlete_id, activity_id) -> dict:
    _, report = _run(s, athlete_id, None, activity_id, "commentary")
    return report


def ask(s, athlete_id, question: str, activity_id=None) -> dict:
    resp, _ = _run(s, athlete_id, question, activity_id, "question")
    return resp


def latest_commentary(s, activity_id):
    return s.scalar(select(m.AiConversation).where(m.AiConversation.activity_id == activity_id,
                                                   m.AiConversation.kind == "commentary")
                    .order_by(desc(m.AiConversation.created_at)))

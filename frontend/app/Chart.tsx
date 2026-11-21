"use client";
import { useEffect, useRef } from "react";

const AXIS = { axisLine: { lineStyle: { color: "#2a2824" } }, splitLine: { lineStyle: { color: "#1d1c1a" } },
  axisLabel: { color: "#8f8a80", fontFamily: "JetBrains Mono, monospace", fontSize: 10 } };

export function withTheme(o: any) {
  const ax = (a: any) => (Array.isArray(a) ? a.map((x) => ({ ...AXIS, ...x })) : a ? { ...AXIS, ...a } : a);
  return {
    backgroundColor: "transparent", animation: false,
    textStyle: { color: "#f2ede4", fontFamily: "Inter Tight, sans-serif" },
    grid: { left: 48, right: 48, top: 28, bottom: 36, ...(o.grid || {}) },
    tooltip: { trigger: "axis", backgroundColor: "#161513", borderColor: "#2a2824", textStyle: { color: "#f2ede4" }, ...(o.tooltip || {}) },
    legend: o.legend ? { textStyle: { color: "#8f8a80" }, top: 0, ...o.legend } : undefined,
    ...o, xAxis: ax(o.xAxis), yAxis: ax(o.yAxis),
  };
}

export default function Chart({ option, height = 260 }: { option: any; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let chart: any, ro: ResizeObserver;
    let alive = true;
    import("echarts").then((ec) => {
      if (!alive || !ref.current) return;
      chart = ec.init(ref.current, undefined, { renderer: "canvas" });
      chart.setOption(withTheme(option));
      ro = new ResizeObserver(() => chart.resize());
      ro.observe(ref.current);
    });
    return () => { alive = false; ro?.disconnect(); chart?.dispose(); };
  }, [option]);
  return <div ref={ref} style={{ height, width: "100%" }} />;
}

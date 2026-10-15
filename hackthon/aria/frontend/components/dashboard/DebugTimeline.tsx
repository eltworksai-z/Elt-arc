"use client";

import type { CallDebug, DebugLane } from "@/lib/live-voice";
import { Empty } from "../ui";

const LANES: { id: DebugLane; label: string; color: string }[] = [
  { id: "user_audio", label: "user audio (in)", color: "#94a3b8" },
  { id: "user_text", label: "user text (ASR)", color: "#64748b" },
  { id: "thinking", label: "thinking", color: "#a78bfa" },
  { id: "backend", label: "backend", color: "#7c3aed" },
  { id: "agent_text", label: "agent text", color: "#60a5fa" },
  { id: "agent_audio", label: "agent audio (out)", color: "#2563eb" },
];

const LABEL_W = 118;
const LANE_H = 34;
const TOP = 28;

export function DebugTimeline({ debug }: { debug: CallDebug | null }) {
  if (!debug || debug.duration === 0) return <Empty>Start a call. The full-duplex timeline of audio, transcripts, delegations and backend work is recorded here.</Empty>;

  const duration = Math.max(debug.duration, 1000);
  const width = 900;
  const plotW = width - LABEL_W - 12;
  const x = (ms: number) => LABEL_W + (Math.min(ms, duration) / duration) * plotW;
  const laneY = (lane: DebugLane) => TOP + LANES.findIndex((l) => l.id === lane) * LANE_H;
  const height = TOP + LANES.length * LANE_H + 34;
  const color = (lane: DebugLane) => LANES.find((l) => l.id === lane)!.color;
  const ticks = Array.from({ length: 7 }, (_, i) => (duration / 6) * i);

  const delegates = debug.marks.filter((m) => m.kind === "delegate");
  const injects = debug.marks.filter((m) => m.kind === "inject");
  const speaks = injects
    .map((inject) => debug.spans.find((s) => s.lane === "agent_text" && s.start >= inject.t))
    .filter((s): s is NonNullable<typeof s> => Boolean(s));
  const latencies = delegates
    .map((d) => {
      const inject = injects.find((i) => i.t >= d.t);
      return inject ? inject.t - d.t : null;
    })
    .filter((v): v is number => v !== null);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[12px]">
        <div className="rounded-lg bg-sunken px-3 py-2">
          <div className="text-faint">Call length</div>
          <div className="text-[15px] font-semibold tabular-nums">{(duration / 1000).toFixed(1)} s</div>
        </div>
        <div className="rounded-lg bg-sunken px-3 py-2">
          <div className="text-faint">Delegations</div>
          <div className="text-[15px] font-semibold tabular-nums">{delegates.length}</div>
        </div>
        <div className="rounded-lg bg-sunken px-3 py-2">
          <div className="text-faint">Delegate → result</div>
          <div className="text-[15px] font-semibold tabular-nums">
            {latencies.length ? `${(latencies.reduce((a, b) => a + b, 0) / latencies.length / 1000).toFixed(1)} s` : "—"}
          </div>
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <svg viewBox={`0 0 ${width} ${height}`} className="min-w-[640px]">
          {ticks.map((t) => (
            <text key={t} x={x(t)} y={16} textAnchor="middle" className="fill-faint font-mono text-[10px]">
              {(t / 1000).toFixed(1)}s
            </text>
          ))}
          {LANES.map((lane) => (
            <g key={lane.id}>
              <line x1={0} x2={width} y1={laneY(lane.id) + LANE_H} y2={laneY(lane.id) + LANE_H} className="stroke-line" />
              <text x={8} y={laneY(lane.id) + LANE_H / 2 + 4} className="fill-ink text-[11px]">
                {lane.label}
              </text>
            </g>
          ))}
          {debug.levels.map((l, i) => {
            const w = Math.max(1, plotW / (duration / 100) - 0.5);
            const uh = Math.min(LANE_H - 8, l.user * 60);
            const ah = Math.min(LANE_H - 8, l.agent * 60);
            return (
              <g key={i}>
                {uh > 1.5 && <rect x={x(l.t)} y={laneY("user_audio") + LANE_H / 2 - uh / 2} width={w} height={uh} fill={color("user_audio")} rx={1} />}
                {ah > 1.5 && <rect x={x(l.t)} y={laneY("agent_audio") + LANE_H / 2 - ah / 2} width={w} height={ah} fill={color("agent_audio")} rx={1} />}
              </g>
            );
          })}
          {debug.spans.map((span, i) => {
            const backend = span.lane === "backend";
            return (
              <g key={i}>
                <rect
                  x={x(span.start)}
                  y={laneY(span.lane) + 7}
                  width={Math.max(3, x(span.end) - x(span.start))}
                  height={LANE_H - 14}
                  rx={4}
                  fill={color(span.lane)}
                  fillOpacity={backend ? 0.18 : 0.85}
                  stroke={backend ? color("backend") : "none"}
                  strokeOpacity={0.4}
                >
                  <title>{span.label}</title>
                </rect>
                {backend && x(span.end) - x(span.start) > 120 && (
                  <text x={(x(span.start) + x(span.end)) / 2} y={laneY("backend") + LANE_H / 2 + 4} textAnchor="middle" className="fill-[#7c3aed] text-[10px]">
                    backend working (async)
                  </text>
                )}
              </g>
            );
          })}
          {debug.marks
            .filter((m) => m.kind === "thinking" || m.kind === "tool")
            .map((m, i) => (
              <rect key={i} x={x(m.t) - 2} y={laneY(m.lane) + 9} width={4} height={LANE_H - 18} rx={2} fill={color(m.lane)}>
                <title>{m.label}</title>
              </rect>
            ))}
          {[
            ...delegates.map((m) => ({ t: m.t, label: "delegate", color: "#7c3aed" })),
            ...injects.map((m) => ({ t: m.t, label: "result injected", color: "#7c3aed" })),
            ...speaks.map((s) => ({ t: s.start, label: "agent speaks result", color: "#2563eb" })),
          ].map((m, i) => (
            <g key={`v${i}`}>
              <line x1={x(m.t)} x2={x(m.t)} y1={TOP} y2={height - 26} stroke={m.color} strokeDasharray="3 3" strokeOpacity={0.7} />
              <text x={x(m.t)} y={height - 12} textAnchor="middle" className="text-[10px]" fill={m.color}>
                {m.label}
              </text>
            </g>
          ))}
        </svg>
      </div>
      <p className="text-[11px] text-faint">
        User and agent audio are sampled every 100 ms in the browser. Transcript and delegation times come from GPT-Live session offsets. Backend spans are
        ARIA agent turns. Hover a block for its text.
      </p>
    </div>
  );
}

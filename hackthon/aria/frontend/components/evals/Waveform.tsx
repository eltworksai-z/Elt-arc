"use client";

import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export type VoiceResult = {
  audio_file: string;
  duration_s: number;
  envelope_ms: number;
  caller_envelope: number[];
  agent_envelope: number[];
  timeline: { type: string; offset_ms: number; name?: string; status?: string; delegation_id?: string; request?: string }[];
  delegations: number;
};

const LANE_LABEL_W = 120;
const LANE_H = 110;
const EVENTS_H = 90;

export function Waveform({ voice, audioUrl }: { voice: VoiceResult; audioUrl: string }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const duration = Math.max(voice.duration_s, 1);
  const width = 900;
  const plotW = width - LANE_LABEL_W - 20;
  const x = (seconds: number) => LANE_LABEL_W + (seconds / duration) * plotW;
  const step = voice.envelope_ms / 1000;
  const ticks = Array.from({ length: 8 }, (_, i) => (duration / 7) * i);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const update = () => setTime(audio.currentTime);
    audio.addEventListener("timeupdate", update);
    audio.addEventListener("ended", () => setPlaying(false));
    return () => audio.removeEventListener("timeupdate", update);
  }, []);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      void audio.play();
      setPlaying(true);
    } else {
      audio.pause();
      setPlaying(false);
    }
  };

  const lane = (envelope: number[], y: number, color: string) =>
    envelope.map((value, i) => {
      const h = Math.min(LANE_H - 20, value * 220);
      return h > 1.5 ? <rect key={i} x={x(i * step)} y={y + LANE_H / 2 - h / 2} width={Math.max(1, plotW / envelope.length - 0.6)} height={h} fill={color} rx={0.5} /> : null;
    });

  const callerY = 40;
  const eventsY = callerY + LANE_H;
  const agentY = eventsY + EVENTS_H;
  const height = agentY + LANE_H + 10;
  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

  return (
    <div className="rounded-xl border border-line bg-surface">
      <div className="flex items-center gap-4 border-b border-line px-4 py-3">
        <button onClick={toggle} className="flex h-10 w-10 items-center justify-center rounded-full bg-ink text-white">
          {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 translate-x-px" />}
        </button>
        <span className="font-mono text-[13px] tabular-nums">
          {fmt(time)} / {fmt(duration)}
        </span>
        <div className="ml-auto flex items-center gap-4 text-[12px] text-muted">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-caller" /> Caller
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-agent" /> ARIA
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rotate-45 bg-agent/80" /> Delegation
          </span>
        </div>
        <audio ref={audioRef} src={audioUrl} preload="metadata" />
      </div>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="min-w-[700px] cursor-pointer"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const px = ((e.clientX - rect.left) / rect.width) * width;
            const seconds = Math.max(0, Math.min(duration, ((px - LANE_LABEL_W) / plotW) * duration));
            if (audioRef.current) audioRef.current.currentTime = seconds;
            setTime(seconds);
          }}
        >
          {ticks.map((t) => (
            <text key={t} x={x(t)} y={22} textAnchor="middle" className="fill-faint font-mono text-[11px]">
              {fmt(t)}
            </text>
          ))}
          {[
            ["CALLER", "Left channel", callerY, LANE_H],
            ["EVENTS", "Delegations · tools", eventsY, EVENTS_H],
            ["AGENT", "Right channel", agentY, LANE_H],
          ].map(([title, sub, y, h]) => (
            <g key={title as string}>
              <line x1={0} x2={width} y1={y as number} y2={y as number} className="stroke-line" />
              <text x={12} y={(y as number) + (h as number) / 2 - 2} className="fill-ink text-[12px] font-semibold tracking-wider">
                {title}
              </text>
              <text x={12} y={(y as number) + (h as number) / 2 + 14} className="fill-muted text-[11px]">
                {sub}
              </text>
            </g>
          ))}
          <line x1={LANE_LABEL_W} x2={width - 20} y1={callerY + LANE_H / 2} y2={callerY + LANE_H / 2} stroke="var(--color-caller)" strokeOpacity={0.25} />
          <line x1={LANE_LABEL_W} x2={width - 20} y1={agentY + LANE_H / 2} y2={agentY + LANE_H / 2} stroke="var(--color-agent)" strokeOpacity={0.25} />
          {lane(voice.caller_envelope, callerY, "var(--color-caller)")}
          {lane(voice.agent_envelope, agentY, "var(--color-agent)")}
          {voice.timeline.map((event, i) => {
            const cx = x(event.offset_ms / 1000);
            if (event.type === "delegation") {
              return (
                <g key={i}>
                  <rect x={cx - 5} y={eventsY + 22} width={10} height={10} transform={`rotate(45 ${cx} ${eventsY + 27})`} fill="var(--color-agent)" />
                  <text x={cx + 9} y={eventsY + 31} className="fill-agent text-[11px]">
                    Delegation · client
                  </text>
                </g>
              );
            }
            return (
              <g key={i}>
                <circle cx={cx} cy={eventsY + 58 + (i % 2) * 14} r={4} fill="var(--color-overlap)" />
                {i % 3 === 0 && (
                  <text x={cx + 7} y={eventsY + 62 + (i % 2) * 14} className="fill-overlap text-[10px]">
                    {event.name}
                  </text>
                )}
              </g>
            );
          })}
          <line x1={x(time)} x2={x(time)} y1={30} y2={height - 6} className="stroke-ink" strokeWidth={1.5} />
          <circle cx={x(time)} cy={32} r={4} className="fill-ink" />
        </svg>
      </div>
      <div className="flex justify-between border-t border-line px-4 py-2 text-[11.5px] text-muted">
        <span>Independent GPT-Live caller + ARIA</span>
        <span>{voice.envelope_ms} ms resolution</span>
      </div>
    </div>
  );
}

"use client";

import clsx from "clsx";
import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";

export function Orb({ seed, size = 36 }: { seed: string; size?: number }) {
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  const a = hash % 360;
  const b = (a + 70 + (hash % 90)) % 360;
  return (
    <span
      className="inline-block shrink-0 rounded-full"
      style={{
        width: size,
        height: size,
        background: `radial-gradient(circle at 30% 30%, hsl(${a} 85% 70%), hsl(${b} 70% 45%) 70%)`,
      }}
    />
  );
}

const TONES = {
  neutral: "bg-sunken text-muted border-line",
  accent: "bg-accent-soft text-accent border-accent/20",
  ok: "bg-ok-soft text-ok border-ok/20",
  warn: "bg-warn-soft text-warn border-warn/25",
  bad: "bg-bad-soft text-bad border-bad/20",
  info: "bg-info-soft text-info border-info/20",
} as const;

export type Tone = keyof typeof TONES;

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-none", TONES[tone], className)}>
      {children}
    </span>
  );
}

export function Collapsible({
  summary,
  children,
  defaultOpen = false,
  className,
}: {
  summary: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={className}>
      <button onClick={() => setOpen(!open)} className="group flex w-full items-center gap-1.5 text-left text-[13px] text-muted hover:text-ink">
        <ChevronRight className={clsx("h-3.5 w-3.5 shrink-0 transition-transform", open && "rotate-90")} />
        {summary}
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </div>
  );
}

export function Bar({ value, tone = "accent" }: { value: number; tone?: "accent" | "ok" | "bad" | "muted" }) {
  const color = { accent: "bg-accent", ok: "bg-ok", bad: "bg-bad/50", muted: "bg-faint" }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunken">
      <div className={clsx("h-full rounded-full transition-all duration-500", color)} style={{ width: `${Math.max(2, value * 100)}%` }} />
    </div>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("rounded-xl border border-line bg-surface", className)}>{children}</div>;
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-faint">{children}</h3>
      {right}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[13px] text-faint">{children}</p>;
}

export function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function relativeTime(ts: string) {
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(ts).toLocaleDateString();
}

export function pct(value: number | null | undefined, digits = 0) {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export function JsonView({ value }: { value: unknown }) {
  return (
    <pre className="max-h-72 overflow-auto rounded-lg bg-sunken p-2.5 font-mono text-[11px] leading-relaxed text-ink/80">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

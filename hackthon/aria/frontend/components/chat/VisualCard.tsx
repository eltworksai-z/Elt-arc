"use client";

import clsx from "clsx";
import { CheckCircle2, XCircle } from "lucide-react";
import type { Decision, EngineState, Snapshot } from "@/lib/types";
import { Badge, Card } from "../ui";
import { HypothesesCard } from "./Cards";

export type Visual = { kind: string; focus: string | null; data: Record<string, any> };

const TITLES: Record<string, string> = {
  line_status: "Line status",
  alarm_history: "Alarm history",
  maintenance_plan: "Maintenance plan",
  incident_history: "Incident history",
  investigation: "Investigation",
};

function LineStatus({ snapshot, trace }: { snapshot: Snapshot; trace: { step: string; conditions: { condition: string; observed: unknown; satisfied: boolean }[] } }) {
  const running = snapshot.mode === "AUTO" && snapshot.active_alarms.length === 0;
  const keySignals = snapshot.signals.filter((s) => typeof s.value === "boolean");
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-[13px]">
        <span className={clsx("h-2.5 w-2.5 rounded-full", running ? "bg-ok" : "bg-bad pulse-dot")} />
        <span className="font-medium">
          {snapshot.machine_id} · {running ? "Running" : snapshot.mode}
        </span>
        <span className="font-mono text-[11.5px] text-muted">{snapshot.sequence_step}</span>
      </div>
      {snapshot.active_alarms.map((a) => (
        <div key={a.code} className="rounded-lg border border-bad/25 bg-bad-soft/50 px-3 py-1.5 text-[12.5px]">
          <span className="font-mono font-semibold text-bad">{a.code}</span> {a.message}
        </div>
      ))}
      <div className="grid gap-1 sm:grid-cols-2">
        {trace.conditions.map((c) => (
          <div key={c.condition} className="flex items-center gap-1.5 text-[12px]">
            {c.satisfied ? <CheckCircle2 className="h-3.5 w-3.5 text-ok" /> : <XCircle className="h-3.5 w-3.5 text-bad" />}
            {c.condition}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-1">
        {keySignals.map((s) => (
          <span key={s.name} className={clsx("rounded-md px-1.5 py-0.5 font-mono text-[10.5px]", s.value ? "bg-ok-soft text-ok" : "bg-sunken text-muted")} title={s.description}>
            {s.address} {s.name.split(".").pop()}
          </span>
        ))}
      </div>
    </div>
  );
}

export function VisualCard({ visual }: { visual: Visual }) {
  const d = visual.data;
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-4 py-2">
        <span className="text-[13px] font-medium">
          {TITLES[visual.kind] ?? visual.kind}
          {visual.focus && <span className="text-muted"> · {visual.focus}</span>}
        </span>
        <Badge tone="warn">simulated data</Badge>
      </div>
      <div className="px-4 py-3">
        {visual.kind === "line_status" && <LineStatus snapshot={d.snapshot} trace={d.trace} />}
        {visual.kind === "alarm_history" && (
          <ol className="space-y-1 border-l border-line pl-3">
            {d.alarms.map((a: any, i: number) => (
              <li key={i} className="text-[12.5px]">
                <span className="text-faint">{new Date(a.timestamp).toLocaleTimeString()}</span>{" "}
                <span className={clsx("font-mono font-semibold", a.active ? "text-bad" : "text-muted")}>{a.code}</span> {a.message}
                {a.active && <Badge tone="bad" className="ml-1.5">active</Badge>}
              </li>
            ))}
          </ol>
        )}
        {visual.kind === "maintenance_plan" && (
          <div className="space-y-1.5">
            {d.tasks.map((t: any) => (
              <div key={t.pm_id} className="flex items-start gap-2 text-[12.5px]">
                <Badge tone={t.status === "overdue" ? "bad" : t.status === "due_this_week" ? "warn" : "neutral"}>{t.status.replaceAll("_", " ")}</Badge>
                <span className="min-w-0 flex-1">
                  {t.task}
                  <span className="block text-[11px] text-faint">
                    last {t.last_done} · next {t.next_due}
                  </span>
                </span>
              </div>
            ))}
          </div>
        )}
        {visual.kind === "incident_history" && (
          <div className="space-y-2.5">
            {d.incidents.map((i: any) => (
              <div key={i.incident_id} className="text-[12.5px]">
                <div className="font-medium">
                  <span className="font-mono text-[11.5px]">{i.incident_id}</span> · {i.title}
                </div>
                <div className="text-[11.5px] text-muted">
                  {new Date(i.opened_at).toLocaleDateString()} · {i.machine_id} · {i.root_cause}
                </div>
              </div>
            ))}
            {d.facts?.length > 0 && (
              <div className="border-t border-line pt-2">
                {d.facts.map((f: any) => (
                  <div key={f.fact_id} className={clsx("text-[12px]", !f.currently_valid && "text-faint line-through")}>
                    {f.statement}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {visual.kind === "investigation" && <HypothesesCard engine={d.engine as EngineState} decision={d.decision as Decision} compact />}
      </div>
    </Card>
  );
}

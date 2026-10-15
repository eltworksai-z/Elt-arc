"use client";

import clsx from "clsx";
import { ArrowRight, CheckCircle2, CircleDashed, ClipboardList, FileText, GitBranch, RotateCcw, ShieldAlert, ShieldCheck, UserRound } from "lucide-react";
import type { SessionView, WorkOrder } from "@/lib/session-state";
import { VisualCard } from "./VisualCard";
import type { Decision, EngineState, ReportState, RetrievalPlan, SafetyEvent } from "@/lib/types";
import { Badge, Bar, Card, pct } from "../ui";

const STATUS_TONE = { supported: "ok", leading: "accent", active: "neutral", ruled_out: "neutral" } as const;

export function HypothesesCard({ engine, decision, compact = false }: { engine: EngineState; decision?: Decision; compact?: boolean }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <div className="text-[13px] font-medium">Fault hypotheses</div>
        <div className="text-[11px] text-faint">{engine.trigger ?? engine.fault_family}</div>
      </div>
      <div className="divide-y divide-line">
        {engine.hypotheses.map((h) => (
          <div key={h.id} className={clsx("px-4 py-2.5", h.status === "ruled_out" && "opacity-45")}>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className={clsx("truncate text-[13px]", h.status === "ruled_out" && "line-through")}>{h.label}</div>
                {!compact && <div className="font-mono text-[10.5px] text-faint">{h.id}</div>}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge tone={STATUS_TONE[h.status]}>{h.status.replace("_", " ")}</Badge>
                <span className="w-10 text-right text-[12px] tabular-nums">{pct(h.posterior)}</span>
              </div>
            </div>
            <div className="mt-1.5">
              <Bar value={h.posterior} tone={h.status === "supported" ? "ok" : h.status === "ruled_out" ? "muted" : "accent"} />
            </div>
            {!compact && (h.evidence_for.length > 0 || h.evidence_against.length > 0) && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {h.evidence_for.map((e) => (
                  <Badge key={`f${e}`} tone="ok">
                    + {e}
                  </Badge>
                ))}
                {h.evidence_against.map((e) => (
                  <Badge key={`a${e}`} tone="bad">
                    − {e}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      {decision && <DecisionStrip decision={decision} />}
    </Card>
  );
}

export function DecisionStrip({ decision }: { decision: Decision }) {
  const stop = decision.decision === "stop";
  return (
    <div className={clsx("flex items-start gap-2 border-t border-line px-4 py-2.5 text-[12.5px]", stop ? "bg-ok-soft/60" : "bg-sunken/60")}>
      {stop ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" /> : <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-accent" />}
      <div>
        <span className="font-medium">{stop ? `Stop: ${decision.stop_reason?.replaceAll("_", " ")}` : `Continue with ${decision.next_test}`}</span>
        <span className="text-muted"> · {decision.rationale}</span>
        {decision.human_needed && (
          <div className="mt-1 flex items-center gap-1 text-warn">
            <UserRound className="h-3.5 w-3.5" /> Human input or authorized inspection needed
          </div>
        )}
      </div>
    </div>
  );
}

export function SafetyCard({ event }: { event: SafetyEvent }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-bad/25 bg-bad-soft/60 px-4 py-3">
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
      <div className="text-[13px]">
        <div className="font-medium text-bad">
          {event.kind === "control_action" ? "Declined" : "Blocked test"}: {event.target.replaceAll("_", " ")}
        </div>
        <div className="text-ink/75">{event.reason}</div>
      </div>
    </div>
  );
}

export function ReportCard({ report, onOpen }: { report: ReportState; onOpen?: () => void }) {
  const r = report.report;
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <div className="flex items-center gap-2 text-[13px] font-medium">
          <FileText className="h-4 w-4 text-muted" /> {r.title}
        </div>
        {report.verified === undefined ? (
          <Badge>
            <CircleDashed className="h-3 w-3 animate-spin" /> verifying
          </Badge>
        ) : report.verified ? (
          <Badge tone="ok">
            <ShieldCheck className="h-3 w-3" /> verified
          </Badge>
        ) : (
          <Badge tone="bad">verification failed</Badge>
        )}
      </div>
      <div className="space-y-2 px-4 py-3 text-[13px]">
        <div>
          <Badge tone={r.status === "diagnosed" ? "ok" : "warn"}>{r.status}</Badge>
          <span className="ml-2">{r.diagnosis_summary}</span>
          <span className="ml-1.5 text-muted">({pct(r.confidence)})</span>
        </div>
        <div className="text-muted">
          <span className="font-medium text-ink">Next safe action: </span>
          {r.recommended_next_safe_action}
        </div>
        {report.mismatches && report.mismatches.length > 0 && (
          <ul className="list-disc pl-4 text-[12px] text-bad">
            {report.mismatches.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        )}
        {onOpen && (
          <button onClick={onOpen} className="text-[12px] font-medium text-accent hover:underline">
            Open report and verification checks →
          </button>
        )}
      </div>
    </Card>
  );
}

export function RetrievalPlanView({ plan }: { plan: RetrievalPlan }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-2.5">
      <div className="mb-1.5 flex items-center gap-1.5 text-[12px] font-medium">
        <GitBranch className="h-3.5 w-3.5 text-info" /> Retrieval plan
      </div>
      <ol className="space-y-1">
        {plan.steps.map((step) => (
          <li key={step.step} className="flex items-start gap-2 text-[12px]">
            <span
              className={clsx(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-md border text-[11px] font-semibold",
                step.status === "success" && "border-ok/40 bg-ok-soft text-ok",
                step.status === "empty" && "border-bad/30 bg-bad-soft text-bad",
                step.status === "running" && "border-line text-muted",
              )}
            >
              {step.retry_of ? <RotateCcw className="h-3 w-3" /> : step.step}
            </span>
            <span className="min-w-0">
              <Badge tone="info">{step.target.replace("_", " ")}</Badge> <span className="text-ink/80">{step.query}</span>
              {step.retry_of && <span className="text-faint"> · retry of step {step.retry_of}</span>}
              {step.status === "empty" && <span className="text-bad"> · nothing found</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function WorkOrderCard({ order }: { order: WorkOrder }) {
  return (
    <Card className="flex items-start gap-3 px-4 py-3">
      <ClipboardList className="mt-0.5 h-4 w-4 shrink-0 text-info" />
      <div className="min-w-0 text-[13px]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[12px] font-semibold">{order.id}</span>
          <span className="font-medium">{order.title}</span>
          <Badge tone={order.priority === "urgent" || order.priority === "high" ? "bad" : "neutral"}>{order.priority}</Badge>
          <Badge tone="warn">simulated CMMS</Badge>
        </div>
        <p className="mt-1 text-muted">{order.description}</p>
        <p className="mt-1 text-[11.5px] text-faint">
          {order.component} · evidence {order.evidence.join(", ") || "none"}
        </p>
      </div>
    </Card>
  );
}

export function CardItem({ card, refId, view, onOpenPanel }: { card: string; refId?: string; view: SessionView; onOpenPanel: (tab: "investigation" | "report") => void }) {
  if (card === "visual" && refId !== undefined && view.visuals[Number(refId)]) return <VisualCard visual={view.visuals[Number(refId)]} />;
  if (card === "work_order") {
    const order = view.workOrders.find((w) => w.id === refId);
    return order ? <WorkOrderCard order={order} /> : null;
  }
  if (card === "hypotheses" && view.engine)
    return (
      <button onClick={() => onOpenPanel("investigation")} className="block w-full text-left" title="Open live investigation">
        <HypothesesCard engine={view.engine} decision={view.decision} compact />
      </button>
    );
  if (card === "safety" && refId !== undefined && view.safety[Number(refId)]) return <SafetyCard event={view.safety[Number(refId)]} />;
  if (card === "report" && refId && view.reports[refId]) return <ReportCard report={view.reports[refId]} onOpen={() => onOpenPanel("report")} />;
  return null;
}

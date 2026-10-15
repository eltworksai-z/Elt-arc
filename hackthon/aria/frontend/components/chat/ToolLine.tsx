"use client";

import clsx from "clsx";
import {
  Activity,
  BookOpen,
  CalendarClock,
  Check,
  ClipboardList,
  Hammer,
  ClipboardCheck,
  Database,
  FileText,
  FlaskConical,
  GitBranch,
  ListChecks,
  Loader2,
  ShieldAlert,
  SlidersHorizontal,
  Workflow,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { TOOL_LABELS } from "@/lib/session-state";
import type { ToolCall } from "@/lib/types";
import { Badge, JsonView } from "../ui";

const ICONS: Record<string, typeof Activity> = {
  get_machine_snapshot: Activity,
  get_alarm_history: ListChecks,
  trace_sequence_conditions: Workflow,
  search_past_incidents: Database,
  search_manuals: BookOpen,
  research_knowledge: GitBranch,
  get_fault_model: SlidersHorizontal,
  register_hypotheses: SlidersHorizontal,
  adjust_hypothesis: SlidersHorizontal,
  select_next_test: GitBranch,
  run_diagnostic_test: FlaskConical,
  request_control_action: ShieldAlert,
  write_diagnostic_report: FileText,
  verify_diagnostic_report: ClipboardCheck,
  get_maintenance_status: CalendarClock,
  create_work_order: ClipboardList,
  record_technician_action: Hammer,
};

type R = Record<string, any>;

function summarize(tool: ToolCall): ReactNode {
  const r = (tool.result ?? {}) as R;
  if (r.error) return <span className="text-bad">{r.error.message}</span>;
  switch (tool.name) {
    case "start_investigation":
      return <span className="font-mono text-[12px]">{r.incident_id}</span>;
    case "get_machine_snapshot":
      return (
        <>
          {r.mode} at <span className="font-mono text-[12px]">{r.sequence_step}</span>
          {r.active_alarms?.map((a: R) => (
            <Badge key={a.code} tone="bad" className="ml-1.5">
              {a.code}
            </Badge>
          ))}
        </>
      );
    case "get_alarm_history":
      return `${r.alarms?.length ?? 0} alarms, ${r.alarms?.filter((a: R) => a.active).length ?? 0} active`;
    case "trace_sequence_conditions":
      return r.blocking?.length ? <>blocking: {r.blocking.join(", ")}</> : "no blocking condition";
    case "search_past_incidents":
      return (
        <>
          {r.incidents?.length ?? 0} incidents
          {r.incidents?.slice(0, 3).map((i: R) => (
            <Badge key={i.incident_id} tone="info" className="ml-1.5">
              {i.incident_id}
            </Badge>
          ))}
          {r.retrieval?.mode && <span className="ml-1.5 text-faint">· {r.retrieval.mode}</span>}
        </>
      );
    case "search_manuals":
      return (
        <>
          “{String(tool.args.query)}” · {r.hits?.length ?? 0} sections
          {r.retrieval?.mode && <span className="ml-1.5 text-faint">· {r.retrieval.mode}</span>}
        </>
      );
    case "research_knowledge":
      return `${r.steps?.length ?? 0} retrieval steps · ${r.evidence?.length ?? 0} sources`;
    case "get_fault_model":
      return `${r.candidate_hypotheses?.length ?? 0} hypotheses · ${r.diagnostic_tests?.length ?? 0} tests for ${r.fault_family}`;
    case "register_hypotheses":
      return <>leading {r.hypotheses?.[0]?.id}</>;
    case "adjust_hypothesis":
      return (
        <>
          {r.adjustment?.direction} {r.adjustment?.hypothesis_id} · {Math.round((r.adjustment?.posterior_before ?? 0) * 100)}% →{" "}
          {Math.round((r.adjustment?.posterior_after ?? 0) * 100)}%
        </>
      );
    case "select_next_test":
      return r.decision?.decision === "stop" ? (
        <>stop · {r.decision.stop_reason?.replaceAll("_", " ")}</>
      ) : (
        <>
          next <span className="font-mono text-[12px]">{r.decision?.next_test}</span>
        </>
      );
    case "run_diagnostic_test":
    case "run_diagnostic_test_basic":
      if (r.status === "blocked")
        return (
          <span className="text-bad">
            <span className="font-mono text-[12px]">{r.test_id}</span> blocked · {r.reason}
          </span>
        );
      return (
        <>
          <span className="font-mono text-[12px]">{r.test_id}</span> → <Badge tone="accent">{r.outcome}</Badge>
        </>
      );
    case "request_control_action":
      return <span className="text-bad">declined {String(tool.args.action).replaceAll("_", " ")}</span>;
    case "write_diagnostic_report":
      return <span className="font-mono text-[12px]">{r.report_id}</span>;
    case "verify_diagnostic_report":
      return r.verified ? (
        <span className="text-ok">
          verified · {r.checks?.length} checks passed
        </span>
      ) : (
        <span className="text-bad">failed · {r.mismatches?.length} mismatches</span>
      );
    case "list_diagnostic_tests":
      return `${r.tests?.length ?? 0} tests`;
    case "get_maintenance_status": {
      const overdue = r.tasks?.filter((t: R) => t.status === "overdue").length ?? 0;
      const soon = r.tasks?.filter((t: R) => t.status === "due_this_week").length ?? 0;
      return (
        <>
          {r.tasks?.length ?? 0} PM tasks
          {overdue > 0 && <Badge tone="bad" className="ml-1.5">{overdue} overdue</Badge>}
          {soon > 0 && <Badge tone="warn" className="ml-1.5">{soon} due this week</Badge>}
        </>
      );
    }
    case "create_work_order":
      return (
        <>
          <span className="font-mono text-[12px]">{r.id}</span> · {r.title}
        </>
      );
    case "record_technician_action":
      return <>{String(tool.args.action)}</>;
    default:
      return null;
  }
}

function Details({ tool }: { tool: ToolCall }) {
  const r = (tool.result ?? {}) as R;
  if (tool.name === "search_manuals" && r.hits?.length) {
    return (
      <div className="space-y-2">
        {r.hits.map((hit: R) => (
          <div key={hit.chunk_id} className="rounded-lg border border-line bg-surface p-2.5">
            <div className="flex items-center gap-1.5 text-[12px] font-medium">
              <BookOpen className="h-3.5 w-3.5 text-info" /> {hit.document}
              {hit.simulated_document && <Badge tone="warn">simulated doc</Badge>}
            </div>
            <div className="text-[11.5px] text-muted">
              {hit.section} · {hit.pages}
              {hit.rerank_score !== null && hit.rerank_score !== undefined && <> · relevance {hit.rerank_score}/3</>}
            </div>
            <p className="mt-1 line-clamp-4 whitespace-pre-line text-[12px] text-ink/80">{hit.excerpt}</p>
          </div>
        ))}
      </div>
    );
  }
  if (tool.name === "search_past_incidents" && r.incidents?.length) {
    return (
      <div className="space-y-2">
        {r.incidents.map((incident: R) => (
          <div key={incident.incident_id} className="rounded-lg border border-line bg-surface p-2.5">
            <div className="flex items-center gap-2 text-[12px] font-medium">
              <Database className="h-3.5 w-3.5 text-info" /> {incident.incident_id} · {incident.title}
            </div>
            <div className="text-[11.5px] text-muted">
              {incident.machine_id} · {incident.age_days} days ago · {incident.similarity_reasons.join(", ")}
            </div>
            <ol className="mt-1.5 space-y-0.5 border-l border-line pl-2.5">
              {incident.timeline.map((e: R, i: number) => (
                <li key={i} className="text-[11.5px]">
                  <span className="text-faint">{new Date(e.ts).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}</span>{" "}
                  <Badge>{e.event_type}</Badge> {e.value}
                </li>
              ))}
            </ol>
          </div>
        ))}
        {r.facts?.length > 0 && (
          <div className="rounded-lg border border-line bg-surface p-2.5">
            <div className="mb-1 text-[12px] font-medium">Time-valid facts</div>
            {r.facts.map((f: R) => (
              <div key={f.fact_id} className={clsx("text-[11.5px]", !f.currently_valid && "text-faint line-through")}>
                {f.statement} <Badge tone={f.currently_valid ? "ok" : "neutral"}>{f.currently_valid ? "valid" : "superseded"}</Badge>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
  if (tool.name === "get_maintenance_status" && r.tasks?.length) {
    return (
      <div className="space-y-1">
        {r.tasks.map((t: R) => (
          <div key={t.pm_id} className="flex items-start gap-2 rounded-md bg-surface px-2 py-1.5 text-[12px] ring-1 ring-line">
            <Badge tone={t.status === "overdue" ? "bad" : t.status === "due_this_week" ? "warn" : "neutral"}>{t.status.replaceAll("_", " ")}</Badge>
            <span className="min-w-0 flex-1">
              {t.task}
              <span className="block text-[11px] text-faint">
                {t.pm_id} · last {t.last_done} · next {t.next_due}
                {t.counter && ` · ${t.counter.name}: ${t.counter.value.toLocaleString()} / ${t.counter.limit.toLocaleString()}`}
              </span>
            </span>
          </div>
        ))}
      </div>
    );
  }
  if (tool.name.startsWith("run_diagnostic_test") && r.observations) {
    return (
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(r.observations as R).map(([k, v]) => (
          <span key={k} className="rounded-md bg-surface px-2 py-1 font-mono text-[11px] ring-1 ring-line">
            {k}: <b>{JSON.stringify(v)}</b>
          </span>
        ))}
      </div>
    );
  }
  return <JsonView value={{ args: tool.args, result: tool.result }} />;
}

export function ToolLine({ tool }: { tool: ToolCall }) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[tool.name] ?? Activity;
  const labels = TOOL_LABELS[tool.name] ?? { running: tool.name, done: tool.name };
  const running = tool.status === "running";
  return (
    <div>
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-2 text-left text-[13px] leading-6 text-muted hover:text-ink">
        <span className="mt-[5px] shrink-0">
          {running ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : tool.status === "error" ? (
            <X className="h-3.5 w-3.5 text-bad" />
          ) : tool.status === "blocked" ? (
            <ShieldAlert className="h-3.5 w-3.5 text-bad" />
          ) : (
            <Icon className="h-3.5 w-3.5" />
          )}
        </span>
        <span className="min-w-0">
          <span className={clsx(running && "shimmer-text")}>{running ? labels.running : labels.done}</span>
          {!running && <span className="ml-1.5 text-ink/80">{summarize(tool)}</span>}
          {!running && tool.duration_ms !== undefined && <span className="ml-1.5 text-[11px] text-faint">{tool.duration_ms} ms</span>}
          {tool.status === "ok" && <Check className="ml-1 inline h-3 w-3 text-ok/70" />}
        </span>
      </button>
      {open && !running && <div className="mb-2 ml-5 mt-1">{<Details tool={tool} />}</div>}
    </div>
  );
}

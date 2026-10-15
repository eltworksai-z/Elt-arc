"use client";

import clsx from "clsx";
import { ArrowUpRight, Ban, Bug, CheckCircle2, CircleDot, Cpu, FileText, Radio, ShieldCheck, Wrench, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_URL } from "@/lib/api";
import type { VoiceStatus } from "@/lib/live-voice";
import { TOOL_LABELS, type SessionView } from "@/lib/session-state";
import { Badge, Bar, Card, Empty, JsonView, SectionTitle, formatTime, pct } from "../ui";
import { DecisionStrip, HypothesesCard, SafetyCard } from "../chat/Cards";
import type { CallDebug } from "@/lib/live-voice";
import { DebugTimeline } from "./DebugTimeline";

export type DashboardTab = "investigation" | "tools" | "report" | "live" | "debug";

const TABS: { id: DashboardTab; label: string; icon: typeof Cpu }[] = [
  { id: "investigation", label: "Issue", icon: CircleDot },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "report", label: "Report", icon: FileText },
  { id: "live", label: "Live", icon: Radio },
  { id: "debug", label: "Debug", icon: Bug },
];

function InvestigationTab({ view }: { view: SessionView }) {
  const d = view.decision;
  return (
    <div className="space-y-5">
      {!view.incidentId && !view.engine && (
        <Empty>No open issue. When a worker reports a stop or fault, ARIA opens one here and shows its hypotheses, tests and decisions live.</Empty>
      )}
      {view.incidentId && (
        <div className="flex items-center justify-between text-[12px] text-muted">
          <span>
            Incident <span className="font-mono text-ink">{view.incidentId}</span>
          </span>
          {view.mode && <Badge tone={view.mode === "improved" ? "accent" : "neutral"}>{view.mode === "improved" ? "ARIA engine" : "baseline"}</Badge>}
        </div>
      )}
      {d && (
        <div>
          <SectionTitle>Decision</SectionTitle>
          <Card className="overflow-hidden">
            <div className="grid grid-cols-3 divide-x divide-line text-center">
              <div className="px-2 py-2.5">
                <div className="text-[11px] text-faint">Leading</div>
                <div className="text-[18px] font-semibold tabular-nums">{pct(d.leading_confidence)}</div>
                <div className="text-[10.5px] text-faint">threshold {pct(d.sufficiency_threshold)}</div>
              </div>
              <div className="px-2 py-2.5">
                <div className="text-[11px] text-faint">Tests</div>
                <div className="text-[18px] font-semibold tabular-nums">
                  {d.tests_used}/{d.test_budget}
                </div>
                <div className="text-[10.5px] text-faint">used / budget</div>
              </div>
              <div className="px-2 py-2.5">
                <div className="text-[11px] text-faint">Loop</div>
                <div className={clsx("text-[15px] font-semibold", d.decision === "stop" ? "text-ok" : "text-accent")}>{d.decision}</div>
                <div className="text-[10.5px] text-faint">{d.stop_reason?.replaceAll("_", " ") ?? d.next_test}</div>
              </div>
            </div>
            <DecisionStrip decision={d} />
          </Card>
        </div>
      )}
      {view.engine ? (
        <div>
          <SectionTitle>Hypotheses</SectionTitle>
          <HypothesesCard engine={view.engine} />
          <div className="mt-2 space-y-1">
            {view.engine.hypotheses
              .filter((h) => h.status !== "ruled_out")
              .map((h) => (
                <p key={h.id} className="text-[11.5px] text-muted">
                  <span className="font-mono text-faint">{h.id}</span> · {h.rationale}
                </p>
              ))}
          </div>
        </div>
      ) : (
        <Empty>Hypotheses appear once ARIA registers candidate causes from the fault model.</Empty>
      )}
      {d?.ranking && (
        <div>
          <SectionTitle>Test selection (expected information gain)</SectionTitle>
          <Card className="divide-y divide-line">
            {d.ranking.map((t) => (
              <div key={t.test_id} className="px-3 py-2">
                <div className="flex items-center justify-between gap-2 text-[12.5px]">
                  <span className={clsx("truncate", t.already_run && "text-faint line-through")}>{t.name}</span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    {!t.permitted && (
                      <Badge tone="bad">
                        <Ban className="h-3 w-3" /> not permitted
                      </Badge>
                    )}
                    <span className="w-14 text-right font-mono text-[11px] tabular-nums">{t.expected_gain_bits.toFixed(2)} bits</span>
                  </span>
                </div>
                <div className="mt-1">
                  <Bar value={Math.min(1, t.expected_gain_bits / 1.6)} tone={t.permitted && t.useful ? "accent" : "muted"} />
                </div>
                {!t.permitted && <p className="mt-1 text-[11px] text-bad">{t.permission_reason}</p>}
              </div>
            ))}
          </Card>
        </div>
      )}
      {view.safety.length > 0 && (
        <div className="space-y-2">
          <SectionTitle>Safety policy</SectionTitle>
          {view.safety.map((s, i) => (
            <SafetyCard key={i} event={s} />
          ))}
        </div>
      )}
      <div>
        <SectionTitle>Timeline</SectionTitle>
        {view.timeline.length === 0 ? (
          <Empty>No milestones yet.</Empty>
        ) : (
          <ol className="space-y-2 border-l border-line pl-3">
            {view.timeline.map((t, i) => (
              <li key={i} className="relative text-[12.5px]">
                <span className="absolute -left-[17px] top-1.5 h-2 w-2 rounded-full bg-line ring-2 ring-canvas" />
                <span className="text-faint">{formatTime(t.ts)}</span> <Badge>{t.kind}</Badge> {t.label}
                {t.detail && <p className="line-clamp-2 text-[11.5px] text-muted">{t.detail}</p>}
              </li>
            ))}
          </ol>
        )}
      </div>
      <div>
        <SectionTitle>Evidence log</SectionTitle>
        {view.evidence.length === 0 ? (
          <Empty>Evidence collected by tools is listed here with its id.</Empty>
        ) : (
          <div className="space-y-1.5">
            {view.evidence.map((e) => (
              <div key={e.id} className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[12px]">
                <span className="font-mono font-semibold">{e.id}</span> <Badge>{e.source.replaceAll("_", " ")}</Badge>{" "}
                <span className="text-ink/80">{e.summary}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ToolsTab({ view }: { view: SessionView }) {
  const [selected, setSelected] = useState<string | null>(null);
  if (view.toolOrder.length === 0) return <Empty>Every tool call, its validated arguments and actual result appear here.</Empty>;
  return (
    <Card className="divide-y divide-line">
      {view.toolOrder.map((id) => {
        const t = view.tools[id];
        return (
          <div key={id}>
            <button onClick={() => setSelected(selected === id ? null : id)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12.5px] hover:bg-sunken/50">
              {t.status === "running" ? (
                <CircleDot className="h-3.5 w-3.5 text-accent pulse-dot" />
              ) : t.status === "ok" ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-ok" />
              ) : (
                <XCircle className="h-3.5 w-3.5 text-bad" />
              )}
              <span className="font-mono">{t.name}</span>
              <span className="truncate text-faint">{TOOL_LABELS[t.name]?.done}</span>
              <span className="ml-auto shrink-0 text-[11px] text-faint">{t.duration_ms !== undefined ? `${t.duration_ms} ms` : "…"}</span>
            </button>
            {selected === id && (
              <div className="space-y-2 px-3 pb-3">
                <div className="text-[11px] font-semibold text-faint">ARGUMENTS</div>
                <JsonView value={t.args} />
                <div className="text-[11px] font-semibold text-faint">RESULT</div>
                <JsonView value={t.result} />
              </div>
            )}
          </div>
        );
      })}
    </Card>
  );
}

function ReportTab({ view }: { view: SessionView }) {
  const id = view.reportOrder[view.reportOrder.length - 1];
  const report = id ? view.reports[id] : undefined;
  const [markdown, setMarkdown] = useState("");
  useEffect(() => {
    if (!id) return;
    fetch(`${API_URL}/api/reports/${id}`)
      .then((r) => r.text())
      .then(setMarkdown)
      .catch(() => setMarkdown(""));
  }, [id, report?.verified]);
  if (!report) return <Empty>The verified diagnostic report appears here after the investigation stops.</Empty>;
  return (
    <div className="space-y-4">
      <div
        className={clsx(
          "flex items-center gap-2 rounded-lg px-3 py-2 text-[12.5px]",
          report.verified ? "bg-ok-soft text-ok" : report.verified === false ? "bg-bad-soft text-bad" : "bg-sunken text-muted",
        )}
      >
        <ShieldCheck className="h-4 w-4" />
        {report.verified ? "Report re-read from disk and verified against tool evidence" : report.verified === false ? "Verification found mismatches" : "Verification pending"}
      </div>
      {report.checks && (
        <Card className="divide-y divide-line">
          {report.checks.map((c) => (
            <div key={c.check} className="flex items-start gap-2 px-3 py-1.5 text-[12px]">
              {c.passed ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ok" /> : <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-bad" />}
              <div>
                <span className="font-mono">{c.check}</span>
                <p className="text-muted">{c.detail}</p>
              </div>
            </div>
          ))}
        </Card>
      )}
      <Card className="prose-aria px-4 py-3 text-[13px]">
        <Markdown remarkPlugins={[remarkGfm]}>{markdown}</Markdown>
      </Card>
      <p className="font-mono text-[11px] text-faint">{report.path}</p>
    </div>
  );
}

function LiveTab({ view, voiceStatus, voiceEvents }: { view: SessionView; voiceStatus: VoiceStatus; voiceEvents: Record<string, number> }) {
  return (
    <div className="space-y-5">
      <Card className="px-4 py-3 text-[12.5px]">
        <div className="mb-2 flex items-center justify-between">
          <span className="font-medium">GPT-Live session</span>
          <Badge tone={voiceStatus === "live" ? "ok" : voiceStatus === "error" ? "bad" : "neutral"}>{voiceStatus}</Badge>
        </div>
        <p className="text-muted">
          The voice model handles turn-taking and interruptions. It delegates work to the ARIA backend (client delegation); results flow back as
          spoken commentary and silent context.
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {[
            ["Delegations", view.delegations.length],
            ["Commentary sent", voiceEvents["session.commentary.appended"] ?? 0],
            ["Context sent", voiceEvents["session.thinking.appended"] ?? 0],
            ["Transcript deltas", (voiceEvents["session.input_transcript.delta"] ?? 0) + (voiceEvents["session.output_transcript.delta"] ?? 0)],
          ].map(([label, value]) => (
            <div key={label as string} className="rounded-lg bg-sunken px-3 py-2">
              <div className="text-[11px] text-faint">{label}</div>
              <div className="text-[16px] font-semibold tabular-nums">{value}</div>
            </div>
          ))}
        </div>
      </Card>
      <div>
        <SectionTitle>Delegations</SectionTitle>
        {view.delegations.length === 0 ? (
          <Empty>Start a call. Each time GPT-Live hands work to the backend it shows up here.</Empty>
        ) : (
          <div className="space-y-2">
            {[...view.delegations].reverse().map((d) => (
              <Card key={d.id} className="px-3 py-2.5">
                <div className="flex items-center justify-between text-[11.5px]">
                  <span className="flex items-center gap-1.5 font-medium text-accent">
                    <ArrowUpRight className="h-3.5 w-3.5" /> client delegation
                  </span>
                  <Badge tone={d.status === "answered" ? "ok" : "accent"}>{d.status}</Badge>
                </div>
                <p className="mt-1 text-[13px]">“{d.transcript || "operator request"}”</p>
                <p className="mt-1 font-mono text-[10.5px] text-faint">
                  {d.id}
                  {d.offsetMs !== undefined && ` · ${(d.offsetMs / 1000).toFixed(1)}s into call`}
                </p>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function Dashboard({
  view,
  tab,
  onTab,
  voiceStatus,
  voiceEvents,
  debug,
}: {
  debug: CallDebug | null;
  view: SessionView;
  tab: DashboardTab;
  onTab: (tab: DashboardTab) => void;
  voiceStatus: VoiceStatus;
  voiceEvents: Record<string, number>;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 border-b border-line px-3 pt-2">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onTab(id)}
            className={clsx(
              "flex items-center gap-1.5 border-b-2 px-2.5 pb-2 pt-1 text-[12.5px]",
              tab === id ? "border-ink font-medium text-ink" : "border-transparent text-muted hover:text-ink",
            )}
          >
            <Icon className="h-3.5 w-3.5" /> {label}
            {id === "live" && view.delegations.some((d) => d.status === "running") && <span className="h-1.5 w-1.5 rounded-full bg-accent pulse-dot" />}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {tab === "investigation" && <InvestigationTab view={view} />}
        {tab === "debug" && <DebugTimeline debug={debug} />}
        {tab === "tools" && <ToolsTab view={view} />}
        {tab === "report" && <ReportTab view={view} />}
        {tab === "live" && <LiveTab view={view} voiceStatus={voiceStatus} voiceEvents={voiceEvents} />}
      </div>
    </div>
  );
}

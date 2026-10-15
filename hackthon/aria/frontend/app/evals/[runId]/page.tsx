"use client";

import clsx from "clsx";
import { CheckCircle2, ExternalLink, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Waveform, type VoiceResult } from "@/components/evals/Waveform";
import { Badge, Card, Empty, SectionTitle, pct } from "@/components/ui";
import { API_URL, api, subscribe } from "@/lib/api";

type CaseResult = Record<string, any> & {
  case_id: string;
  mode: string;
  error?: string;
  voice?: VoiceResult;
  transcript?: { speaker: string; text: string }[];
};
type RunResults = { run_id: string; status: string; channel?: string; summary?: Record<string, Record<string, number | null>>; results: CaseResult[] };

const SUMMARY_ROWS: { key: string; label: string; format: "pct" | "num"; better: "high" | "low" }[] = [
  { key: "task_completion", label: "Task completion", format: "pct", better: "high" },
  { key: "diagnostic_accuracy", label: "Diagnostic accuracy", format: "pct", better: "high" },
  { key: "evidence_grounding", label: "Evidence grounding (report audit)", format: "pct", better: "high" },
  { key: "semantic_quality", label: "Semantic quality (judge)", format: "pct", better: "high" },
  { key: "tool_accuracy", label: "Required tool coverage", format: "pct", better: "high" },
  { key: "avg_tests", label: "Diagnostic tests per case", format: "num", better: "low" },
  { key: "avg_unnecessary_tests", label: "Unnecessary tests per case", format: "num", better: "low" },
  { key: "report_completion", label: "Report completion", format: "pct", better: "high" },
  { key: "safety_pass_rate", label: "Safety pass rate", format: "pct", better: "high" },
  { key: "avg_turn_latency_s", label: "Backend turn latency (s)", format: "num", better: "low" },
  { key: "avg_input_tokens", label: "Input tokens per case", format: "num", better: "low" },
];

const fmt = (value: number | null | undefined, format: "pct" | "num") =>
  value === null || value === undefined ? "—" : format === "pct" ? pct(value) : Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });

function TaskMetrics({ r }: { r: CaseResult }) {
  const rows: [string, string, string?][] = [
    ["Task completed", r.task_completed ? "Yes" : "No"],
    ["Diagnosis", r.diagnosis_correct === null ? "n/a (knowledge)" : r.diagnosis_correct ? "Correct" : "Wrong", `${r.reported_diagnosis ?? "none"} vs ${r.expected_diagnosis ?? "—"}`],
    ["Semantic quality", pct(r.semantic_quality)],
    ...Object.entries(r.semantic ?? {}).map(([k, v]) => [`  ${k.replaceAll("_", " ")}`, pct(v as number)] as [string, string]),
    ["Tool accuracy", pct(r.tool_accuracy), `${r.required_tools_hit} required tools`],
    ["Tool calls", String(r.tool_calls)],
    ["Diagnostic tests", `${r.tests_run} / ≤${r.max_reasonable_tests}`, `${r.unnecessary_tests} unnecessary · ${r.tests_blocked} blocked`],
    ["Evidence grounding", pct(r.evidence_grounding), r.report_verified_by_agent ? "agent verified its report" : "audited after run"],
    ["Report written", r.report_written ? "Yes" : "No"],
    ["Safety", r.safety_ok ? "Pass" : "Violation", r.declined_actions?.length ? `declined via policy: ${r.declined_actions.join(", ")}` : undefined],
    ["Conversation turns", String(r.conversation_turns)],
    ["Avg backend turn latency", `${r.avg_turn_latency_s ?? "—"} s`],
    ...(r.delegations !== undefined ? ([["Delegations", `${r.delegations} / ${r.expected_delegations ?? "—"}`, "actual / expected"]] as [string, string, string][]) : []),
  ];
  return (
    <Card className="divide-y divide-line">
      <div className="px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-faint">Task</div>
      {rows.map(([label, value, sub]) => (
        <div key={label} className="flex items-start justify-between gap-4 px-4 py-2">
          <div>
            <div className={clsx("text-[13px]", label.startsWith("  ") ? "pl-3 text-muted" : "text-ink/85")}>{label.trim()}</div>
            {sub && <div className="text-[11px] text-faint">{sub}</div>}
          </div>
          <div className="text-[13px] font-medium tabular-nums">{value}</div>
        </div>
      ))}
    </Card>
  );
}

export default function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const [data, setData] = useState<RunResults | null>(null);
  const [progress, setProgress] = useState<Record<string, { status: string; result?: Record<string, any> }>>({});
  const [selected, setSelected] = useState<CaseResult | null>(null);

  useEffect(() => {
    const load = () => api<RunResults>(`/api/evals/runs/${runId}`).then(setData);
    load();
    return subscribe(`/api/evals/runs/${runId}/events`, (event) => {
      const d = event.data as Record<string, any>;
      if (event.type === "eval.case.started") setProgress((p) => ({ ...p, [`${d.case_id}:${d.mode}`]: { status: "running" } }));
      if (event.type === "eval.case.completed") setProgress((p) => ({ ...p, [`${d.case_id}:${d.mode}`]: { status: "done", result: d } }));
      if (event.type === "eval.run.completed" || event.type === "eval.run.failed") load();
    });
  }, [runId]);

  const modes = data?.summary ? Object.keys(data.summary).sort() : [];
  const results = data?.results ?? [];

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-8 px-8 py-8">
        <div>
          <Link href="/evals" className="text-[12px] text-muted hover:text-ink">
            ← Evaluations
          </Link>
          <h1 className="mt-1 text-xl font-semibold">
            Run {runId} {data?.channel && <Badge className="ml-1">{data.channel}</Badge>}
          </h1>
        </div>

        {results.length === 0 && (
          <section>
            <SectionTitle>Progress</SectionTitle>
            {Object.keys(progress).length === 0 ? (
              <Empty>Waiting for simulations to start…</Empty>
            ) : (
              <Card className="divide-y divide-line">
                {Object.entries(progress).map(([key, p]) => (
                  <div key={key} className="flex items-center gap-2 px-4 py-2 text-[13px]">
                    {p.status === "running" ? <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" /> : <CheckCircle2 className="h-3.5 w-3.5 text-ok" />}
                    <span className="font-mono text-[12px]">{key}</span>
                    {p.result && (
                      <span className="ml-auto text-[12px] text-muted">
                        {p.result.error ? <span className="text-bad">{p.result.error}</span> : <>task {p.result.task_completed ? "✓" : "✗"} · diagnosis {String(p.result.reported_diagnosis)}</>}
                      </span>
                    )}
                  </div>
                ))}
              </Card>
            )}
          </section>
        )}

        {data?.summary && (
          <section>
            <SectionTitle>Baseline vs improved</SectionTitle>
            <Card className="overflow-hidden">
              <table className="w-full text-[13px]">
                <thead className="bg-sunken/60 text-[11.5px] text-muted">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium">Metric</th>
                    {modes.map((m) => (
                      <th key={m} className="px-4 py-2 text-right font-medium capitalize">
                        {m}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {SUMMARY_ROWS.map((row) => {
                    const values = modes.map((m) => data.summary![m]?.[row.key] ?? null);
                    const numeric = values.filter((v): v is number => v !== null);
                    const best = numeric.length > 1 ? (row.better === "high" ? Math.max(...numeric) : Math.min(...numeric)) : null;
                    return (
                      <tr key={row.key}>
                        <td className="px-4 py-2 text-ink/85">{row.label}</td>
                        {values.map((v, i) => (
                          <td key={i} className={clsx("px-4 py-2 text-right tabular-nums", best !== null && v === best && numeric.some((n) => n !== best) && "font-semibold text-ok")}>
                            {fmt(v, row.format)}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>
            <p className="mt-2 text-[11.5px] text-faint">Measured on this run only. Small sample; rerun to check variance before quoting numbers.</p>
          </section>
        )}

        {results.length > 0 && (
          <section>
            <SectionTitle>Cases</SectionTitle>
            <Card className="overflow-hidden">
              <table className="w-full text-[12.5px]">
                <thead className="bg-sunken/60 text-[11.5px] text-muted">
                  <tr>
                    {["Case", "Agent", "Task", "Diagnosis", "Tests", "Grounding", "Safety", "Latency"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {results.map((r) => (
                    <tr
                      key={`${r.case_id}${r.mode}`}
                      onClick={() => setSelected(r)}
                      className={clsx("cursor-pointer hover:bg-sunken/50", selected === r && "bg-accent-soft/40")}
                    >
                      <td className="px-3 py-2 font-mono text-[11.5px]">{r.case_id}</td>
                      <td className="px-3 py-2">
                        <Badge tone={r.mode === "improved" ? "accent" : "neutral"}>{r.mode}</Badge>
                      </td>
                      {r.error ? (
                        <td colSpan={6} className="px-3 py-2 text-bad">
                          {r.error}
                        </td>
                      ) : (
                        <>
                          <td className="px-3 py-2">{r.task_completed ? <CheckCircle2 className="h-4 w-4 text-ok" /> : <XCircle className="h-4 w-4 text-bad" />}</td>
                          <td className="px-3 py-2">
                            {r.diagnosis_correct === null ? "—" : r.diagnosis_correct ? <span className="text-ok">correct</span> : <span className="text-bad">{r.reported_diagnosis ?? "none"}</span>}
                          </td>
                          <td className="px-3 py-2 tabular-nums">
                            {r.tests_run} <span className="text-faint">({r.unnecessary_tests} unneeded)</span>
                          </td>
                          <td className="px-3 py-2 tabular-nums">{pct(r.evidence_grounding)}</td>
                          <td className="px-3 py-2">{r.safety_ok ? <span className="text-ok">pass</span> : <span className="text-bad">fail</span>}</td>
                          <td className="px-3 py-2 tabular-nums">{r.avg_turn_latency_s}s</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </section>
        )}

        {selected && !selected.error && (
          <section className="space-y-4">
            <SectionTitle
              right={
                <Link href={`/sessions/${selected.session_id}`} className="flex items-center gap-1 text-[12px] text-accent hover:underline">
                  Open full session replay <ExternalLink className="h-3 w-3" />
                </Link>
              }
            >
              {selected.case_id} · {selected.mode}
            </SectionTitle>
            {selected.voice && <Waveform voice={selected.voice} audioUrl={`${API_URL}/api/evals/runs/${runId}/audio/${selected.voice.audio_file}`} />}
            <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
              <TaskMetrics r={selected} />
              <div className="space-y-4">
                <Card className="px-4 py-3">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">Transcript</div>
                  <div className="space-y-2">
                    {selected.transcript?.map((t, i) => (
                      <div key={i} className={clsx("text-[13px]", t.speaker === "operator" ? "text-ink" : "text-ink/75")}>
                        <span className={clsx("mr-2 text-[11px] font-semibold uppercase", t.speaker === "operator" ? "text-caller" : "text-agent")}>
                          {t.speaker === "operator" ? "Caller" : "ARIA"}
                        </span>
                        {t.text}
                      </div>
                    ))}
                  </div>
                </Card>
                <Card className="px-4 py-3 text-[12.5px]">
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-faint">Judge rationale</div>
                  <p className="text-muted">{selected.judge_rationale}</p>
                </Card>
                {selected.test_efficiency?.length > 0 && (
                  <Card className="px-4 py-3 text-[12.5px]">
                    <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-faint">Test efficiency (shadow engine replay)</div>
                    {selected.test_efficiency.map((t: Record<string, any>, i: number) => (
                      <div key={i} className="flex justify-between">
                        <span className="font-mono">{t.test_id}</span>
                        <span className={t.verdict === "useful" ? "text-ok" : "text-warn"}>
                          {t.verdict.replaceAll("_", " ")} · {t.expected_gain_bits} bits
                        </span>
                      </div>
                    ))}
                  </Card>
                )}
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

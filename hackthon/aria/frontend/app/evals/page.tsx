"use client";

import { FlaskConical, Loader2, Play } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, Card, Empty, SectionTitle, pct, relativeTime } from "@/components/ui";
import { api, post } from "@/lib/api";

type EvalCase = { id: string; title: string; opening: string; persona: string; scenario: { title: string } };
type Run = {
  id: string;
  created_at: string;
  status: string;
  config: { cases: string[]; modes: string[]; channel: string };
  summary: Record<string, Record<string, number | null>> | null;
};

export default function EvalsPage() {
  const router = useRouter();
  const [cases, setCases] = useState<EvalCase[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [modes, setModes] = useState<string[]>(["baseline", "improved"]);
  const [channel, setChannel] = useState<"text" | "voice">("text");
  const [runs, setRuns] = useState<Run[]>([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<EvalCase[]>("/api/evals/cases")
      .then((c) => {
        setCases(c);
        setSelected(c.map((x) => x.id));
      })
      .catch((e) => setError(String(e)));
    api<Run[]>("/api/evals/runs").then(setRuns).catch(() => undefined);
  }, []);

  const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const { run_id } = await post<{ run_id: string }>("/api/evals/runs", { case_ids: selected, modes, channel, concurrency: channel === "voice" ? 1 : 2 });
      router.push(`/evals/${run_id}`);
    } catch (e) {
      setError(String(e));
      setStarting(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-8 px-8 py-8">
        <div>
          <h1 className="text-xl font-semibold">Evaluations</h1>
          <p className="mt-1 max-w-3xl text-[13.5px] text-muted">
            Repeatable multi-turn simulations. An independent caller model plays the operator with a private goal and agenda. ARIA and a baseline
            agent face the same hidden fault. An observer ends the conversation, then deterministic checks and an LLM judge grade it.
          </p>
        </div>

        <section>
          <SectionTitle>Configure run</SectionTitle>
          <Card className="divide-y divide-line">
            {cases.map((c) => (
              <label key={c.id} className="flex cursor-pointer items-start gap-3 px-4 py-2.5">
                <input type="checkbox" className="mt-1" checked={selected.includes(c.id)} onChange={() => setSelected(toggle(selected, c.id))} />
                <div className="min-w-0">
                  <div className="text-[13px] font-medium">
                    {c.title} <Badge className="ml-1">{c.scenario.title}</Badge>
                  </div>
                  <div className="text-[12px] text-muted">
                    “{c.opening}” · {c.persona}
                  </div>
                </div>
              </label>
            ))}
          </Card>
          <div className="mt-3 flex flex-wrap items-center gap-4 text-[12.5px]">
            <div className="flex items-center gap-2">
              Agents
              {["baseline", "improved"].map((m) => (
                <label key={m} className="flex items-center gap-1">
                  <input type="checkbox" checked={modes.includes(m)} onChange={() => setModes(toggle(modes, m))} /> {m}
                </label>
              ))}
            </div>
            <div className="flex items-center gap-2">
              Channel
              {(["text", "voice"] as const).map((c) => (
                <button
                  key={c}
                  onClick={() => setChannel(c)}
                  className={`rounded-md border px-2 py-0.5 ${channel === c ? "border-ink bg-ink text-white" : "border-line bg-surface"}`}
                >
                  {c === "text" ? "Text (caller LLM)" : "Voice (GPT-Live ↔ GPT-Live)"}
                </button>
              ))}
            </div>
            <button
              onClick={start}
              disabled={starting || selected.length === 0 || modes.length === 0}
              className="ml-auto flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-white disabled:opacity-50"
            >
              {starting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Run {selected.length * modes.length} simulations
            </button>
          </div>
          {error && <p className="mt-2 text-[12.5px] text-bad">{error}</p>}
        </section>

        <section>
          <SectionTitle>Runs</SectionTitle>
          {runs.length === 0 ? (
            <Empty>No evaluation runs yet.</Empty>
          ) : (
            <Card className="divide-y divide-line">
              {runs.map((run) => (
                <Link key={run.id} href={`/evals/${run.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-sunken/50">
                  <FlaskConical className="h-4 w-4 text-muted" />
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] font-medium">
                      {run.id} <Badge className="ml-1">{run.config.channel}</Badge>
                    </div>
                    <div className="text-[11.5px] text-muted">
                      {run.config.cases.length} cases · {run.config.modes.join(" vs ")} · {relativeTime(run.created_at)}
                    </div>
                  </div>
                  {run.summary &&
                    Object.entries(run.summary).map(([mode, s]) => (
                      <Badge key={mode} tone={mode === "improved" ? "accent" : "neutral"}>
                        {mode}: {pct(s?.task_completion as number)}
                      </Badge>
                    ))}
                  <Badge tone={run.status === "completed" ? "ok" : run.status === "failed" ? "bad" : "info"}>{run.status}</Badge>
                </Link>
              ))}
            </Card>
          )}
        </section>
      </div>
    </div>
  );
}

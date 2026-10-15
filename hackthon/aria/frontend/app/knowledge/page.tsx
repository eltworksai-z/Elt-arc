"use client";

import clsx from "clsx";
import { BookOpen, Clock3, Database, FileUp, GitBranch, Loader2, RefreshCw, Search, Sparkles, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { RetrievalPlanView } from "@/components/chat/Cards";
import { Badge, Card, Empty, SectionTitle } from "@/components/ui";
import { API_URL, api, post, subscribe } from "@/lib/api";
import type { RetrievalPlan, ServerEvent } from "@/lib/types";

type Doc = { id: string; title: string; kind: string; pages: number; chunk_count: number; simulated: number; status: string; created_at: string };
type Fact = {
  fact_id: string;
  statement: string;
  subject: string;
  predicate: string;
  temporal_type: string;
  valid_from: string | null;
  valid_until: string | null;
  currently_valid: boolean;
  invalidated_by: string | null;
  source: string;
};
type Incident = { id: string; machine_id: string; title: string; alarm_code: string; component: string; status: string; opened_at: string; source: string };
type Temporal = { incidents: Incident[]; statements: Fact[]; counts: Record<string, number> };
type Hit = { chunk_id: string; citation: string; excerpt: string; rerank_score: number | null; rrf_score: number };

const date = (value: string | null) => (value ? new Date(value).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }) : "—");

export default function KnowledgePage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [temporal, setTemporal] = useState<Temporal | null>(null);
  const [feed, setFeed] = useState<ServerEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [query, setQuery] = useState("What gap should sensor B21 be set to after a finger change?");
  const [multiStep, setMultiStep] = useState(true);
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [plan, setPlan] = useState<RetrievalPlan | null>(null);
  const [mode, setMode] = useState<string>("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api<Doc[]>("/api/knowledge/documents").then(setDocs).catch((e) => setError(String(e)));
    api<Temporal>("/api/knowledge/temporal").then(setTemporal).catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    return subscribe("/api/knowledge/events", (event) => {
      setFeed((prev) => [event, ...prev].slice(0, 60));
      if (["document.indexed", "document.failed", "temporal.completed", "temporal.failed", "temporal.episode_done"].includes(event.type)) load();
      if (event.type === "temporal.completed" || event.type === "temporal.failed") setBuilding(false);
    });
  }, [load]);

  const upload = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    try {
      await api("/api/knowledge/documents", { method: "POST", body: form });
    } catch (e) {
      setError(String(e));
    }
  };

  const build = async () => {
    setError(null);
    setBuilding(true);
    try {
      await post("/api/knowledge/temporal/build");
    } catch (e) {
      setError(String(e));
      setBuilding(false);
    }
  };

  const search = async () => {
    setSearching(true);
    setError(null);
    setHits(null);
    setPlan(null);
    try {
      const result = await post<any>("/api/knowledge/search", { query, multi_step: multiStep });
      if (multiStep) {
        setPlan({ question: result.question, steps: result.steps });
        setHits(
          result.evidence.map((e: any) => ({
            chunk_id: `${e.step}-${e.chunk_id ?? e.incident_id}`,
            citation: e.citation ?? `${e.incident_id} · ${e.title}`,
            excerpt: e.excerpt ?? e.root_cause ?? "",
            rerank_score: e.rerank_score ?? null,
            rrf_score: e.rrf_score ?? e.relevance ?? 0,
          })),
        );
        setMode("multi-step");
      } else {
        setHits(result.hits);
        setMode(result.retrieval.mode);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSearching(false);
    }
  };

  const superseded = temporal?.statements.filter((s) => !s.currently_valid) ?? [];

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-10 px-8 py-8">
        <div>
          <h1 className="text-xl font-semibold">Knowledge base</h1>
          <p className="mt-1 text-[13.5px] text-muted">
            Two sources ground ARIA: equipment manuals (hybrid RAG with reranking) and a temporal knowledge base of incidents, events and time-valid
            facts.
          </p>
          {error && <p className="mt-2 rounded-lg bg-bad-soft px-3 py-1.5 text-[12.5px] text-bad">{error}</p>}
        </div>

        <section>
          <SectionTitle
            right={
              <div className="flex gap-2">
                <button
                  onClick={() => post("/api/knowledge/sync").then(load).catch((e) => setError(String(e)))}
                  className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1 text-[12px] hover:border-ink/30"
                >
                  <RefreshCw className="h-3.5 w-3.5" /> Re-index folder
                </button>
                <button onClick={() => fileRef.current?.click()} className="flex items-center gap-1.5 rounded-lg bg-ink px-2.5 py-1 text-[12px] text-white">
                  <FileUp className="h-3.5 w-3.5" /> Upload PDF
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.md,.txt"
                  hidden
                  onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
                />
              </div>
            }
          >
            Manuals and procedures
          </SectionTitle>
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_300px]">
            <Card className="divide-y divide-line">
              {docs.length === 0 && <Empty>No documents yet.</Empty>}
              {docs.map((doc) => (
                <div key={doc.id} className="flex items-center gap-3 px-4 py-2.5">
                  <BookOpen className="h-4 w-4 shrink-0 text-info" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-medium">{doc.title}</div>
                    <div className="text-[11.5px] text-muted">
                      {doc.kind.toUpperCase()} · {doc.pages} pages · {doc.chunk_count} chunks
                    </div>
                  </div>
                  {doc.simulated ? <Badge tone="warn">simulated</Badge> : null}
                  <Badge tone={doc.status === "indexed" ? "ok" : "warn"}>{doc.status === "indexed" ? "hybrid indexed" : "keyword only"}</Badge>
                  <button
                    onClick={() => api(`/api/knowledge/documents/${doc.id}`, { method: "DELETE" }).then(load)}
                    className="rounded p-1 text-faint hover:text-bad"
                    title="Remove"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </Card>
            <Card className="px-4 py-3 text-[12px] leading-relaxed text-muted">
              <div className="mb-1 font-medium text-ink">Which PDFs to add</div>
              Text-based (not scanned) manuals for the cell's components work best: robot or gripper operating manual, pneumatic gripper data sheet,
              IO-Link proximity sensor and photo-eye manuals, safety light curtain manual, and your palletizer's troubleshooting or alarm guide.
              Headings and numbered sections give the best citations. Files land in <code>backend/data/manuals</code>.
            </Card>
          </div>
        </section>

        <section>
          <SectionTitle
            right={
              <button
                onClick={build}
                disabled={building}
                className="flex items-center gap-1.5 rounded-lg bg-ink px-2.5 py-1 text-[12px] text-white disabled:opacity-60"
              >
                {building ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Build temporal facts
              </button>
            }
          >
            Temporal knowledge base
          </SectionTitle>
          {temporal && (
            <div className="mb-3 grid grid-cols-5 gap-2">
              {Object.entries(temporal.counts).map(([key, value]) => (
                <Card key={key} className="px-3 py-2">
                  <div className="text-[11px] capitalize text-faint">{key.replaceAll("_", " ")}</div>
                  <div className="text-[18px] font-semibold tabular-nums">{value}</div>
                </Card>
              ))}
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <Card className="max-h-[420px] overflow-y-auto">
              <div className="sticky top-0 border-b border-line bg-surface px-4 py-2 text-[12px] font-medium">Incidents (timestamped events)</div>
              {temporal?.incidents.map((incident) => (
                <div key={incident.id} className="flex items-start gap-2.5 border-b border-line px-4 py-2 last:border-0">
                  <Database className="mt-0.5 h-3.5 w-3.5 shrink-0 text-info" />
                  <div className="min-w-0 text-[12.5px]">
                    <div className="truncate">
                      <span className="font-mono text-[11.5px]">{incident.id}</span> · {incident.title}
                    </div>
                    <div className="text-[11px] text-muted">
                      {incident.machine_id} · {incident.alarm_code ?? "—"} · {date(incident.opened_at)} ·{" "}
                      {incident.source === "aria" ? <span className="text-accent">ARIA investigation</span> : "simulated history"}
                    </div>
                  </div>
                </div>
              ))}
            </Card>
            <Card className="max-h-[420px] overflow-y-auto">
              <div className="sticky top-0 border-b border-line bg-surface px-4 py-2 text-[12px] font-medium">
                Facts with validity windows {superseded.length > 0 && <Badge className="ml-1">{superseded.length} superseded</Badge>}
              </div>
              {temporal && temporal.statements.length === 0 && (
                <div className="p-4">
                  <Empty>Run “Build temporal facts” to extract statements from incident narratives (needs the API key).</Empty>
                </div>
              )}
              {temporal?.statements.map((fact) => (
                <div key={fact.fact_id} className="border-b border-line px-4 py-2 last:border-0">
                  <div className={clsx("text-[12.5px]", !fact.currently_valid && "text-faint line-through")}>{fact.statement}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                    <Badge tone={fact.temporal_type === "dynamic" ? "accent" : fact.temporal_type === "static" ? "info" : "neutral"}>{fact.temporal_type}</Badge>
                    <Clock3 className="h-3 w-3" /> {date(fact.valid_from)} → {fact.valid_until ? date(fact.valid_until) : "now"}
                    {!fact.currently_valid && <Badge>superseded</Badge>}
                    <span className="font-mono text-faint">{fact.source}</span>
                  </div>
                </div>
              ))}
            </Card>
          </div>
          {feed.length > 0 && (
            <Card className="mt-3 max-h-40 overflow-y-auto px-4 py-2 font-mono text-[11px] text-muted">
              {feed.map((event) => (
                <div key={event.seq}>
                  <span className="text-faint">{new Date(event.ts).toLocaleTimeString()}</span> {event.type} {JSON.stringify(event.data).slice(0, 160)}
                </div>
              ))}
            </Card>
          )}
        </section>

        <section>
          <SectionTitle>Retrieval playground</SectionTitle>
          <Card className="p-3">
            <div className="flex items-center gap-2">
              <Search className="h-4 w-4 text-faint" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && search()}
                className="flex-1 bg-transparent text-[13.5px] outline-none"
              />
              <label className="flex items-center gap-1.5 text-[12px] text-muted">
                <input type="checkbox" checked={multiStep} onChange={(e) => setMultiStep(e.target.checked)} />
                <GitBranch className="h-3.5 w-3.5" /> multi-step
              </label>
              <button onClick={search} disabled={searching} className="rounded-lg bg-ink px-3 py-1 text-[12px] text-white disabled:opacity-60">
                {searching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Search"}
              </button>
            </div>
          </Card>
          {plan && (
            <div className="mt-3">
              <RetrievalPlanView plan={plan} />
            </div>
          )}
          {hits && (
            <div className="mt-3 space-y-2">
              <div className="text-[11.5px] text-faint">mode: {mode}</div>
              {hits.length === 0 && <Empty>No relevant passages found.</Empty>}
              {hits.map((hit) => (
                <Card key={hit.chunk_id} className="px-4 py-2.5">
                  <div className="flex items-center justify-between gap-2 text-[12.5px] font-medium">
                    {hit.citation}
                    {hit.rerank_score !== null && <Badge tone="ok">relevance {hit.rerank_score}/3</Badge>}
                  </div>
                  <p className="mt-1 line-clamp-4 whitespace-pre-line text-[12px] text-muted">{hit.excerpt}</p>
                </Card>
              ))}
            </div>
          )}
          <p className="mt-2 text-[11px] text-faint">API: {API_URL}</p>
        </section>
      </div>
    </div>
  );
}

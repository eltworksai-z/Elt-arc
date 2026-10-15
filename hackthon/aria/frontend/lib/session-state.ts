import type { Visual } from "@/components/chat/VisualCard";
import type {
  ActivityEntry,
  ConversationItem,
  Decision,
  EngineState,
  Evidence,
  ReportState,
  RetrievalPlan,
  RetrievalStep,
  SafetyEvent,
  Scenario,
  ServerEvent,
  Snapshot,
  TimelineEntry,
  ToolCall,
} from "./types";

export type Delegation = { id: string; transcript: string; ts: string; status: "running" | "answered"; offsetMs?: number };

export type WorkOrder = {
  id: string;
  title: string;
  priority: string;
  component: string;
  description: string;
  evidence: string[];
  status: string;
  created_at: string;
};

export type SessionView = {
  title?: string;
  visuals: Visual[];
  workOrders: WorkOrder[];
  scenario?: Scenario;
  mode?: string;
  items: ConversationItem[];
  tools: Record<string, ToolCall>;
  toolOrder: string[];
  snapshot?: Snapshot;
  engine?: EngineState;
  decision?: Decision;
  evidence: Evidence[];
  timeline: TimelineEntry[];
  reports: Record<string, ReportState>;
  reportOrder: string[];
  retrievals: RetrievalPlan[];
  safety: SafetyEvent[];
  delegations: Delegation[];
  incidentId?: string;
  busy: boolean;
  usage?: Record<string, number>;
  lastError?: string;
};

export const emptySession = (): SessionView => ({
  visuals: [],
  workOrders: [],
  items: [],
  tools: {},
  toolOrder: [],
  evidence: [],
  timeline: [],
  reports: {},
  reportOrder: [],
  retrievals: [],
  safety: [],
  delegations: [],
  busy: false,
});

export const TOOL_LABELS: Record<string, { running: string; done: string }> = {
  start_investigation: { running: "Opening investigation", done: "Opened investigation" },
  get_machine_snapshot: { running: "Reading machine signals", done: "Read machine signals" },
  get_alarm_history: { running: "Reading alarm history", done: "Read alarm history" },
  trace_sequence_conditions: { running: "Tracing sequence interlocks", done: "Traced sequence interlocks" },
  search_past_incidents: { running: "Searching incident history", done: "Searched incident history" },
  search_manuals: { running: "Searching manuals", done: "Searched manuals" },
  research_knowledge: { running: "Researching knowledge base", done: "Researched knowledge base" },
  get_fault_model: { running: "Loading fault model", done: "Loaded fault model" },
  register_hypotheses: { running: "Ranking hypotheses", done: "Ranked hypotheses" },
  adjust_hypothesis: { running: "Updating beliefs", done: "Updated beliefs" },
  select_next_test: { running: "Deciding next test", done: "Decided next test" },
  run_diagnostic_test: { running: "Running diagnostic test", done: "Ran diagnostic test" },
  list_diagnostic_tests: { running: "Listing tests", done: "Listed tests" },
  request_control_action: { running: "Checking safety policy", done: "Checked safety policy" },
  notify_operator: { running: "Updating operator", done: "Updated operator" },
  write_diagnostic_report: { running: "Writing report", done: "Wrote report" },
  verify_diagnostic_report: { running: "Verifying report", done: "Verified report" },
  get_maintenance_status: { running: "Checking maintenance plan", done: "Checked maintenance plan" },
  create_work_order: { running: "Creating work order", done: "Created work order" },
  record_technician_action: { running: "Recording technician work", done: "Recorded technician work" },
  show_visual: { running: "Putting it on screen", done: "Showed on screen" },
};

let counter = 0;
const uid = (prefix: string) => `${prefix}-${++counter}`;

type Activity = Extract<ConversationItem, { kind: "activity" }>;

function openActivityCopy(view: SessionView): Activity | undefined {
  const index = view.items.length - 1;
  const last = view.items[index];
  if (last?.kind !== "activity" || !last.open) return undefined;
  const copy: Activity = { ...last, entries: [...last.entries] };
  view.items[index] = copy;
  return copy;
}

function ensureActivity(view: SessionView, ts: string): Activity {
  const open = openActivityCopy(view);
  if (open) return open;
  const block: Activity = { id: uid("act"), kind: "activity", entries: [], startedAt: ts, open: true };
  view.items.push(block);
  return block;
}

function closeActivity(view: SessionView, ts: string) {
  const open = openActivityCopy(view);
  if (!open) return;
  if (open.entries.length === 0) {
    view.items.pop();
    return;
  }
  open.open = false;
  open.endedAt = ts;
}

function upsertStep(plan: RetrievalPlan, step: RetrievalStep) {
  const index = plan.steps.findIndex((s) => s.step === step.step);
  if (index >= 0) plan.steps[index] = { ...plan.steps[index], ...step };
  else plan.steps.push(step);
}

export function applyEvent(prev: SessionView, event: ServerEvent): SessionView {
  const view: SessionView = { ...prev, items: [...prev.items], tools: { ...prev.tools } };
  const d = event.data as Record<string, any>;
  const ts = event.ts;

  switch (event.type) {
    case "session.created":
      view.scenario = d.scenario;
      view.mode = d.mode;
      break;
    case "visual.render":
      view.visuals = [...view.visuals, d as Visual];
      closeActivity(view, ts);
      view.items.push({ id: uid("card"), kind: "card", card: "visual", ts, ref: String(view.visuals.length - 1) });
      break;
    case "session.titled":
      view.title = d.title;
      break;
    case "plant.changed":
      view.scenario = d.scenario;
      view.items.push({
        id: uid("sys"),
        kind: "system",
        icon: "safety",
        text: d.scenario.kind === "normal" ? "Demo control: simulated cell back to normal running" : "Demo control: a fault was injected into the simulated cell (ARIA is not told)",
        ts,
      });
      break;
    case "work_order.created":
      view.workOrders = [...view.workOrders, d as WorkOrder];
      closeActivity(view, ts);
      view.items.push({ id: uid("card"), kind: "card", card: "work_order", ts, ref: d.id });
      break;
    case "knowledge.updated":
      view.items.push({
        id: uid("sys"),
        kind: "system",
        icon: "report",
        text: `Knowledge base updated: ${d.facts_added?.length ?? 0} new facts${d.facts_superseded?.length ? `, ${d.facts_superseded.length} superseded` : ""}`,
        ts,
      });
      break;
    case "operator.message":
      if (d.source === "voice") break;
      view.items.push({ id: uid("op"), kind: "operator", text: d.text, source: d.source, ts });
      break;
    case "operator.queued": {
      const index = view.items.findLastIndex((i) => i.kind === "operator" && i.text === d.text);
      const target = view.items[index];
      if (target?.kind === "operator") view.items[index] = { ...target, queued: true };
      break;
    }
    case "voice.transcript":
      closeActivity(view, ts);
      if (d.speaker === "operator") view.items.push({ id: uid("vop"), kind: "operator", text: d.text, source: "voice", ts });
      else view.items.push({ id: uid("vag"), kind: "agent", text: d.text, ts, streaming: false, spoken: true });
      break;
    case "voice.session":
      view.items.push({ id: uid("sys"), kind: "system", icon: "call", text: "Call started · GPT-Live", ts });
      break;
    case "voice.ended":
      view.items.push({ id: uid("sys"), kind: "system", icon: "call", text: `Call ended${d.duration_s ? ` · ${Math.round(d.duration_s)}s` : ""}`, ts });
      break;
    case "delegation.created":
      view.delegations = [...view.delegations, { id: d.delegation_id, transcript: d.transcript, ts, status: "running", offsetMs: d.offset_ms }];
      ensureActivity(view, ts).entries.push({ kind: "delegation", delegationId: d.delegation_id, transcript: d.transcript });
      break;
    case "agent.turn.started":
      view.busy = true;
      ensureActivity(view, ts);
      break;
    case "agent.thinking.delta": {
      const block = ensureActivity(view, ts);
      const last = block.entries[block.entries.length - 1];
      if (last?.kind === "thinking") block.entries[block.entries.length - 1] = { kind: "thinking", text: last.text + d.text };
      else block.entries.push({ kind: "thinking", text: d.text });
      break;
    }
    case "agent.thinking": {
      const block = ensureActivity(view, ts);
      const last = block.entries[block.entries.length - 1];
      if (last?.kind === "thinking") block.entries[block.entries.length - 1] = { kind: "thinking", text: d.text };
      else block.entries.push({ kind: "thinking", text: d.text });
      break;
    }
    case "tool.started":
      view.tools[d.call_id] = { call_id: d.call_id, name: d.name, args: d.args, status: "running", started_at: ts };
      view.toolOrder = [...view.toolOrder, d.call_id];
      ensureActivity(view, ts).entries.push({ kind: "tool", callId: d.call_id });
      break;
    case "tool.completed":
      view.tools[d.call_id] = { ...view.tools[d.call_id], status: d.status, duration_ms: d.duration_ms, result: d.result };
      break;
    case "agent.context":
      ensureActivity(view, ts).entries.push({ kind: "context", text: d.text });
      break;
    case "agent.say":
      if (d.delegation_id) {
        ensureActivity(view, ts).entries.push({ kind: "context", text: `Progress sent to voice: ${d.text}` });
        break;
      }
      closeActivity(view, ts);
      view.items.push({ id: uid("say"), kind: "say", text: d.text, ts });
      break;
    case "agent.delta": {
      const last = view.items[view.items.length - 1];
      if (last?.kind === "agent" && last.streaming) {
        view.items[view.items.length - 1] = { ...last, text: last.text + d.text };
      } else {
        closeActivity(view, ts);
        view.items.push({ id: uid("ag"), kind: "agent", text: d.text, ts, streaming: true });
      }
      break;
    }
    case "agent.message": {
      const last = view.items[view.items.length - 1];
      if (last?.kind === "agent" && last.streaming) view.items.pop();
      if (d.delegation_id) {
        view.delegations = view.delegations.map((del) => (del.id === d.delegation_id ? { ...del, status: "answered" } : del));
      }
      closeActivity(view, ts);
      if (d.text) view.items.push({ id: uid("ag"), kind: "agent", text: d.text, ts, streaming: false, error: d.error });
      break;
    }
    case "agent.turn.completed":
      view.busy = false;
      view.usage = d.usage;
      closeActivity(view, ts);
      break;
    case "investigation.started":
      view.incidentId = d.incident_id;
      break;
    case "machine.snapshot":
      view.snapshot = d as Snapshot;
      break;
    case "hypotheses.updated":
      if (!view.engine) {
        closeActivity(view, ts);
        view.items.push({ id: uid("card"), kind: "card", card: "hypotheses", ts });
      }
      view.engine = d as EngineState;
      break;
    case "decision":
      view.decision = d as Decision;
      break;
    case "evidence.added":
      view.evidence = [...view.evidence, d as Evidence];
      break;
    case "timeline":
      view.timeline = [...view.timeline, { ts, kind: d.kind, label: d.label, detail: d.detail }];
      break;
    case "retrieval.plan":
      view.retrievals = [...view.retrievals, { question: d.question, steps: d.steps }];
      ensureActivity(view, ts).entries.push({ kind: "retrieval", planIndex: view.retrievals.length - 1 });
      break;
    case "retrieval.step":
    case "retrieval.retry": {
      const plans = [...view.retrievals];
      const plan = plans[plans.length - 1];
      if (plan) {
        const copy = { ...plan, steps: [...plan.steps] };
        upsertStep(copy, d as RetrievalStep);
        plans[plans.length - 1] = copy;
        view.retrievals = plans;
      }
      break;
    }
    case "safety.blocked":
      view.safety = [...view.safety, { kind: d.kind, target: d.target, reason: d.reason, ts }];
      closeActivity(view, ts);
      view.items.push({ id: uid("card"), kind: "card", card: "safety", ts, ref: String(view.safety.length - 1) });
      break;
    case "report.written":
      view.reports = { ...view.reports, [d.report_id]: { report_id: d.report_id, path: d.path, report: d.report } };
      view.reportOrder = [...view.reportOrder, d.report_id];
      closeActivity(view, ts);
      view.items.push({ id: uid("card"), kind: "card", card: "report", ts, ref: d.report_id });
      break;
    case "report.verified":
      if (view.reports[d.report_id]) {
        view.reports = { ...view.reports, [d.report_id]: { ...view.reports[d.report_id], verified: d.verified, checks: d.checks, mismatches: d.mismatches } };
      }
      break;
    case "error":
      view.lastError = d.message;
      break;
  }
  return view;
}

export function statusLine(view: SessionView): string | null {
  if (!view.busy) return null;
  const running = [...view.toolOrder].reverse().map((id) => view.tools[id]).find((t) => t?.status === "running");
  if (running) {
    const label = TOOL_LABELS[running.name]?.running ?? running.name;
    const testId = running.args?.test_id;
    return testId ? `${label} · ${testId}` : label;
  }
  return "Deciding action";
}

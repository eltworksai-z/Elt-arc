export type ServerEvent<T = Record<string, unknown>> = {
  seq: number;
  ts: string;
  type: string;
  data: T;
};

export type Scenario = {
  id: string;
  title: string;
  summary: string;
  operator_symptom: string;
  kind: "normal" | "fault";
  simulated: boolean;
};

export type SessionRow = {
  id: string;
  title: string;
  kind: string;
  scenario_id: string;
  status: string;
  summary: string;
  created_at: string;
  updated_at: string;
  active: boolean;
};

export type Signal = { name: string; address: string; description: string; value: unknown };
export type Alarm = { code: string; message: string; severity: string; active: boolean; timestamp: string };

export type Snapshot = {
  machine_id: string;
  read_at: string;
  mode: string;
  sequence_step: string;
  signals: Signal[];
  active_alarms: Alarm[];
  evidence_id?: string;
};

export type Hypothesis = {
  id: string;
  label: string;
  component: string;
  prior: number;
  posterior: number;
  status: "active" | "leading" | "supported" | "ruled_out";
  rationale: string;
  evidence_for: string[];
  evidence_against: string[];
};

export type EngineState = {
  fault_family: string | null;
  hypotheses: Hypothesis[];
  sufficient: boolean;
  trigger?: string;
};

export type TestRanking = {
  test_id: string;
  name: string;
  already_run: boolean;
  permitted: boolean;
  permission_reason: string;
  expected_gain_bits: number;
  useful: boolean;
};

export type Decision = {
  decision: "continue" | "stop";
  stop_reason: string | null;
  leading_hypothesis: string | null;
  leading_confidence: number;
  sufficiency_threshold: number;
  next_test: string | null;
  tests_used: number;
  test_budget: number;
  blocked_useful_tests: { test_id: string; reason: string }[];
  human_needed: boolean;
  rationale: string;
  ranking?: TestRanking[];
};

export type Evidence = { id: string; source: string; summary: string; data: Record<string, unknown>; ts: string };

export type ToolCall = {
  call_id: string;
  name: string;
  args: Record<string, unknown>;
  status: "running" | "ok" | "error" | "blocked";
  started_at: string;
  duration_ms?: number;
  result?: unknown;
};

export type TimelineEntry = { ts: string; kind: string; label: string; detail: string };

export type ReportCheck = { check: string; passed: boolean; detail: string };

export type ReportState = {
  report_id: string;
  path: string;
  report: Record<string, unknown> & {
    title: string;
    status: string;
    diagnosis_summary: string;
    confidence: number;
    diagnosis_hypothesis_id: string;
    recommended_next_safe_action: string;
  };
  verified?: boolean;
  checks?: ReportCheck[];
  mismatches?: string[];
};

export type RetrievalStep = {
  step: number;
  target: string;
  query: string;
  purpose: string;
  status: string;
  retry_of?: number;
  hits?: unknown[];
};

export type RetrievalPlan = { question: string; steps: RetrievalStep[] };

export type SafetyEvent = { kind: string; target: string; reason: string; ts: string };

export type ActivityEntry =
  | { kind: "tool"; callId: string }
  | { kind: "thinking"; text: string }
  | { kind: "delegation"; delegationId: string; transcript: string }
  | { kind: "retrieval"; planIndex: number }
  | { kind: "context"; text: string }
  | { kind: "queued"; text: string };

export type ConversationItem =
  | { id: string; kind: "operator"; text: string; source: string; ts: string; queued?: boolean }
  | { id: string; kind: "agent"; text: string; ts: string; streaming: boolean; error?: boolean; spoken?: boolean }
  | { id: string; kind: "say"; text: string; ts: string }
  | { id: string; kind: "activity"; entries: ActivityEntry[]; startedAt: string; endedAt?: string; open: boolean }
  | { id: string; kind: "system"; text: string; icon: "call" | "session" | "report" | "safety" | "error" | "investigation"; ts: string }
  | { id: string; kind: "card"; card: "hypotheses" | "report" | "safety" | "work_order" | "visual"; ts: string; ref?: string };

export type VoiceLine = { speaker: "operator" | "assistant"; text: string; startMs: number; endMs: number };

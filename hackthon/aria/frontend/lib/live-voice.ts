import { post } from "./api";
import type { ServerEvent, VoiceLine } from "./types";

export type VoiceStatus = "idle" | "connecting" | "live" | "closing" | "error";

export type DebugSpan = { lane: DebugLane; start: number; end: number; label: string };
export type DebugMark = { lane: DebugLane; t: number; kind: "delegate" | "inject" | "thinking" | "tool" | "turn"; label: string };
export type DebugLane = "user_audio" | "user_text" | "thinking" | "backend" | "agent_text" | "agent_audio";
export type CallDebug = { levels: { t: number; user: number; agent: number }[]; spans: DebugSpan[]; marks: DebugMark[]; duration: number };

type Callbacks = {
  onStatus: (status: VoiceStatus, detail?: string) => void;
  onLines: (lines: VoiceLine[]) => void;
  onEvent?: (type: string, data: Record<string, unknown>) => void;
};

const LINE_GAP_MS = 1200;
let eventCounter = 0;
const eventId = (prefix: string) => `${prefix}_${Date.now().toString(36)}_${++eventCounter}`;

export class LiveVoiceClient {
  private pc?: RTCPeerConnection;
  private channel?: RTCDataChannel;
  private mic?: MediaStream;
  private audio?: HTMLAudioElement;
  private audioContext?: AudioContext;
  private micAnalyser?: AnalyserNode;
  private agentAnalyser?: AnalyserNode;
  private lines: VoiceLine[] = [];
  private flushedIndex = 0;
  private pendingRequest = "";
  private startedAt = 0;
  private closedResolver?: () => void;
  private sampler?: ReturnType<typeof setInterval>;
  private backendStart: number | null = null;
  private debug: CallDebug = { levels: [], spans: [], marks: [], duration: 0 };
  liveSessionId?: string;

  constructor(
    private readonly sessionId: string,
    private readonly callbacks: Callbacks,
  ) {}

  async start(): Promise<void> {
    this.callbacks.onStatus("connecting");
    this.mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    this.pc = new RTCPeerConnection();
    this.mic.getTracks().forEach((track) => this.pc!.addTrack(track, this.mic!));
    this.audio = new Audio();
    this.audio.autoplay = true;
    this.audioContext = new AudioContext();
    this.micAnalyser = this.analyse(this.mic);
    this.pc.ontrack = (event) => {
      this.audio!.srcObject = event.streams[0];
      this.agentAnalyser = this.analyse(event.streams[0]);
    };
    this.channel = this.pc.createDataChannel("oai-events");
    this.channel.onmessage = (message) => this.handle(JSON.parse(message.data));
    this.channel.onclose = () => this.finish();

    await this.pc.setLocalDescription(await this.pc.createOffer());
    await this.waitForIce();
    const answer = await post<{ live_session_id: string; sdp: string }>(`/api/sessions/${this.sessionId}/live`, {
      sdp: this.pc.localDescription!.sdp,
    });
    this.liveSessionId = answer.live_session_id;
    await this.pc.setRemoteDescription({ type: "answer", sdp: answer.sdp });
  }

  private analyse(stream: MediaStream): AnalyserNode {
    const analyser = this.audioContext!.createAnalyser();
    analyser.fftSize = 512;
    this.audioContext!.createMediaStreamSource(stream).connect(analyser);
    return analyser;
  }

  levels(): { operator: number; agent: number } {
    const read = (analyser?: AnalyserNode) => {
      if (!analyser) return 0;
      const data = new Uint8Array(analyser.fftSize);
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const value of data) sum += ((value - 128) / 128) ** 2;
      return Math.min(1, Math.sqrt(sum / data.length) * 4);
    };
    return { operator: read(this.micAnalyser), agent: read(this.agentAnalyser) };
  }

  private waitForIce(): Promise<void> {
    return new Promise((resolve) => {
      if (this.pc!.iceGatheringState === "complete") return resolve();
      const timer = setTimeout(resolve, 2500);
      this.pc!.onicegatheringstatechange = () => {
        if (this.pc!.iceGatheringState === "complete") {
          clearTimeout(timer);
          resolve();
        }
      };
    });
  }

  private send(event: Record<string, unknown>) {
    if (this.channel?.readyState === "open") this.channel.send(JSON.stringify(event));
  }

  private appendTranscript(speaker: VoiceLine["speaker"], delta: string, startMs: number, endMs: number) {
    const last = this.lines[this.lines.length - 1];
    if (last && last.speaker === speaker && startMs - last.endMs < LINE_GAP_MS) {
      this.lines = [...this.lines.slice(0, -1), { ...last, text: last.text + delta, endMs }];
    } else {
      this.flushLines(this.lines.length);
      this.lines = [...this.lines, { speaker, text: delta.trimStart(), startMs, endMs }];
    }
    this.callbacks.onLines(this.lines);
  }

  private flushLines(upTo: number) {
    const finished = this.lines.slice(this.flushedIndex, upTo).filter((line) => line.text.trim());
    this.flushedIndex = upTo;
    if (finished.length === 0) return;
    void post(
      `/api/sessions/${this.sessionId}/voice-events`,
      finished.map((line) => ({
        type: "transcript",
        data: { speaker: line.speaker, text: line.text.trim(), start_ms: line.startMs, end_ms: line.endMs },
      })),
    ).catch(() => undefined);
  }

  pendingLines(): VoiceLine[] {
    return this.lines.slice(this.flushedIndex);
  }

  private handle(event: Record<string, any>) {
    this.callbacks.onEvent?.(event.type, event);
    switch (event.type) {
      case "session.started":
        this.startedAt = performance.now();
        this.sampler = setInterval(() => {
          const { operator, agent } = this.levels();
          this.debug.levels.push({ t: this.now(), user: operator, agent });
          this.debug.duration = this.now();
        }, 100);
        this.callbacks.onStatus("live");
        break;
      case "session.input_transcript.delta":
        this.pendingRequest += event.delta;
        this.appendTranscript("operator", event.delta, event.start_ms, event.end_ms);
        this.addSpan("user_text", event.start_ms, event.end_ms, event.delta);
        break;
      case "session.output_transcript.delta":
        this.appendTranscript("assistant", event.delta, event.start_ms, event.end_ms);
        this.addSpan("agent_text", event.start_ms, event.end_ms, event.delta);
        break;
      case "session.commentary.appended":
        this.debug.marks.push({ lane: "backend", t: event.start_ms ?? this.now(), kind: "inject", label: "result injected" });
        break;
      case "session.thinking.appended":
        this.debug.marks.push({ lane: "thinking", t: event.start_ms ?? this.now(), kind: "thinking", label: "context appended" });
        break;
      case "session.delegation.created": {
        this.debug.marks.push({ lane: "backend", t: event.offset_ms ?? this.now(), kind: "delegate", label: "delegate" });
        const transcript = this.pendingRequest.trim();
        this.pendingRequest = "";
        this.flushLines(this.lines.length);
        void post(`/api/sessions/${this.sessionId}/delegations`, {
          delegation_id: event.delegation.id,
          transcript,
          offset_ms: event.offset_ms,
        }).catch((error) => this.callbacks.onStatus("error", String(error)));
        break;
      }
      case "error":
        this.callbacks.onStatus("live", `GPT-Live: ${event.error?.message ?? "error"}`);
        break;
      case "session.closed":
        this.closedResolver?.();
        this.finish();
        break;
    }
  }

  private now(): number {
    return this.startedAt ? Math.round(performance.now() - this.startedAt) : 0;
  }

  private addSpan(lane: DebugLane, start: number | undefined, end: number | undefined, label: string) {
    const s = start ?? this.now();
    const e = Math.max(end ?? s, s + 80);
    const last = this.debug.spans.findLast((span) => span.lane === lane);
    if (last && s - last.end < 400) {
      last.end = e;
      last.label += label;
    } else {
      this.debug.spans.push({ lane, start: s, end: e, label: label.trimStart() });
    }
  }

  debugData(): CallDebug {
    return { ...this.debug, levels: [...this.debug.levels], spans: this.debug.spans.map((s) => ({ ...s })), marks: [...this.debug.marks] };
  }

  forwardBackendEvent(event: ServerEvent) {
    const data = event.data as Record<string, any>;
    if (this.startedAt) {
      if (event.type === "agent.turn.started") this.backendStart = this.now();
      if (event.type === "agent.turn.completed" && this.backendStart !== null) {
        this.debug.spans.push({ lane: "backend", start: this.backendStart, end: this.now(), label: "backend working (async)" });
        this.backendStart = null;
      }
      if (event.type === "tool.completed") this.debug.marks.push({ lane: "backend", t: this.now(), kind: "tool", label: data.name });
    }
    const delegationId = data.delegation_id as string | undefined;
    if (!delegationId || !data.text) return;
    if (event.type === "agent.say" || event.type === "agent.message" || event.type === "delegation.ack") {
      this.send({ type: "session.commentary.append", event_id: eventId("commentary"), delegation_id: delegationId, content: data.text });
    } else if (event.type === "agent.context") {
      this.send({ type: "session.thinking.append", event_id: eventId("thinking"), delegation_id: delegationId, content: data.text });
    }
  }

  setMuted(muted: boolean) {
    this.mic?.getAudioTracks().forEach((track) => (track.enabled = !muted));
    this.send({ type: muted ? "session.input_audio.mute" : "session.input_audio.unmute", event_id: eventId("mute") });
  }

  setSpeakerMuted(muted: boolean) {
    if (this.audio) this.audio.muted = muted;
  }

  elapsedSeconds(): number {
    return this.startedAt ? (performance.now() - this.startedAt) / 1000 : 0;
  }

  async stop(): Promise<void> {
    this.callbacks.onStatus("closing");
    const closed = new Promise<void>((resolve) => (this.closedResolver = resolve));
    this.send({ type: "session.close", event_id: eventId("close") });
    await Promise.race([closed, new Promise((resolve) => setTimeout(resolve, 4000))]);
    this.finish();
  }

  private finish() {
    if (!this.pc) return;
    clearInterval(this.sampler);
    this.debug.duration = this.now();
    this.flushLines(this.lines.length);
    void post(`/api/sessions/${this.sessionId}/voice-events`, [
      { type: "ended", data: { duration_s: this.elapsedSeconds(), live_session_id: this.liveSessionId } },
    ]).catch(() => undefined);
    this.channel?.close();
    this.pc.close();
    this.mic?.getTracks().forEach((track) => track.stop());
    void this.audioContext?.close();
    this.pc = undefined;
    this.callbacks.onStatus("idle");
  }
}

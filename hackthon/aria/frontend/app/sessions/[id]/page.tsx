"use client";

import clsx from "clsx";
import { AlertTriangle, Mic, PanelRightClose, PanelRightOpen } from "lucide-react";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { Composer } from "@/components/chat/Composer";
import { Conversation } from "@/components/chat/Conversation";
import { Dashboard, type DashboardTab } from "@/components/dashboard/Dashboard";
import { api, post, subscribe } from "@/lib/api";
import { LiveVoiceClient, type CallDebug, type VoiceStatus } from "@/lib/live-voice";
import { applyEvent, emptySession, statusLine, type SessionView } from "@/lib/session-state";
import type { ServerEvent, VoiceLine } from "@/lib/types";

type SessionMeta = { meta: { title: string; active: boolean; kind: string } };

export default function SessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [view, setView] = useState<SessionView>(emptySession);
  const [meta, setMeta] = useState<SessionMeta["meta"] | null>(null);
  const [panel, setPanel] = useState(false);
  const [tab, setTab] = useState<DashboardTab>("investigation");
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("idle");
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [voiceEvents, setVoiceEvents] = useState<Record<string, number>>({});
  const [pendingVoice, setPendingVoice] = useState<VoiceLine[]>([]);
  const [debug, setDebug] = useState<CallDebug | null>(null);
  const voiceRef = useRef<LiveVoiceClient | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const autoCall = useRef(false);

  useEffect(() => {
    setView(emptySession());
    api<SessionMeta>(`/api/sessions/${id}`)
      .then((s) => setMeta(s.meta))
      .catch(() => setMeta(null));
    return subscribe(`/api/sessions/${id}/events`, (event: ServerEvent) => {
      setView((prev) => applyEvent(prev, event));
      voiceRef.current?.forwardBackendEvent(event);
      if (event.type === "voice.transcript") setPendingVoice(voiceRef.current?.pendingLines() ?? []);
    });
  }, [id]);

  useEffect(() => () => void voiceRef.current?.stop(), []);

  useEffect(() => {
    if (voiceStatus !== "live") return;
    const timer = setInterval(() => voiceRef.current && setDebug(voiceRef.current.debugData()), 500);
    return () => clearInterval(timer);
  }, [voiceStatus]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [view.items, pendingVoice]);

  const send = useCallback(
    (text: string) => {
      post(`/api/sessions/${id}/messages`, { text, source: "text" }).catch((e) => setVoiceNote(String(e)));
    },
    [id],
  );

  const startCall = useCallback(async () => {
    if (voiceRef.current) return;
    setVoiceNote(null);
    const client = new LiveVoiceClient(id, {
      onStatus: (status, detail) => {
        setVoiceStatus(status);
        if (detail) setVoiceNote(detail);
        if (status === "idle") {
          setDebug(client.debugData());
          voiceRef.current = null;
          setPendingVoice([]);
        }
      },
      onLines: () => setPendingVoice(client.pendingLines()),
      onEvent: (type) => setVoiceEvents((prev) => ({ ...prev, [type]: (prev[type] ?? 0) + 1 })),
    });
    voiceRef.current = client;
    try {
      await client.start();
    } catch (e) {
      setVoiceStatus("error");
      setVoiceNote(e instanceof Error ? e.message : String(e));
      voiceRef.current = null;
    }
  }, [id]);

  useEffect(() => {
    if (autoCall.current || !meta?.active) return;
    if (new URLSearchParams(window.location.search).get("call") === "1") {
      autoCall.current = true;
      window.history.replaceState(null, "", `/sessions/${id}`);
      void startCall();
    }
  }, [meta, id, startCall]);

  const endCall = useCallback(() => {
    void voiceRef.current?.stop();
  }, []);

  const status = statusLine(view);
  const inactive = meta !== null && !meta.active;
  const started = view.items.length > 0 || pendingVoice.length > 0 || voiceStatus !== "idle" || debug !== null;

  return (
    <div className="flex h-full">
      <section className="flex min-w-0 flex-1 flex-col">
        {started && (
          <header className="flex items-center justify-between gap-3 border-b border-line px-6 py-3">
            <h1 className="truncate text-[14.5px] font-semibold">{view.title ?? meta?.title ?? ""}</h1>
            <button onClick={() => setPanel(!panel)} className="rounded-lg p-1.5 text-muted hover:bg-sunken" title="Work, report and debug">
              {panel ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
            </button>
          </header>
        )}

        <div
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
          }}
          className="flex-1 overflow-y-auto"
        >
          <div className="mx-auto max-w-3xl px-6 py-6">
            {started ? (
              <>
                <Conversation view={view} pendingVoice={pendingVoice} onOpenPanel={(t) => (setPanel(true), setTab(t))} />
                <div className="mt-5 h-6 pl-10 text-[13px]">
                  {status ? (
                    <span className="flex items-center gap-2 text-muted">
                      <span className="h-2 w-2 rounded-full bg-ink pulse-dot" /> <span className="shimmer-text">{status}</span>
                    </span>
                  ) : voiceStatus === "live" ? (
                    <span className="flex items-center gap-2 text-muted">
                      <span className="h-2 w-2 rounded-full bg-ok pulse-dot" /> Listening
                    </span>
                  ) : null}
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center pt-32">
                <button
                  onClick={startCall}
                  disabled={inactive}
                  className="flex h-20 w-20 items-center justify-center rounded-full bg-ink text-white shadow-lg transition hover:scale-105 disabled:opacity-50"
                  title="Call ARIA"
                >
                  <Mic className="h-8 w-8" />
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="mx-auto w-full max-w-3xl px-6 pb-5">
          {(view.lastError || voiceNote || inactive) && (
            <div className={clsx("mb-2 flex items-center gap-2 rounded-lg px-3 py-1.5 text-[12px]", inactive ? "bg-sunken text-muted" : "bg-warn-soft text-warn")}>
              <AlertTriangle className="h-3.5 w-3.5" />
              {inactive ? "This conversation is archived (backend restarted). Start a new conversation to continue." : voiceNote ?? view.lastError}
            </div>
          )}
          <Composer onSend={send} onStartCall={startCall} onEndCall={endCall} voiceStatus={voiceStatus} voiceClient={voiceRef.current} disabled={inactive} />
        </div>
      </section>

      {panel && (
        <aside className="w-[460px] shrink-0 border-l border-line bg-[#fbfaf8]">
          <Dashboard view={view} tab={tab} onTab={setTab} voiceStatus={voiceStatus} voiceEvents={voiceEvents} debug={debug} />
        </aside>
      )}
    </div>
  );
}

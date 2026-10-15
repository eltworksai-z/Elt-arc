"use client";

import clsx from "clsx";
import { ArrowUp, Loader2, Mic, MicOff, Phone, Volume2, VolumeX, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { LiveVoiceClient, VoiceStatus } from "@/lib/live-voice";

function LevelMeter({ client }: { client: LiveVoiceClient | null }) {
  const [bars, setBars] = useState<number[]>(() => Array(32).fill(0.05));
  useEffect(() => {
    if (!client) return;
    let frame = 0;
    const tick = () => {
      const { operator, agent } = client.levels();
      setBars((prev) => [...prev.slice(1), Math.max(0.05, operator, agent)]);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [client]);
  return (
    <div className="flex h-6 flex-1 items-center gap-[3px] overflow-hidden">
      {bars.map((value, i) => (
        <span key={i} className="w-[3px] rounded-full bg-ink/25" style={{ height: `${Math.round(value * 100)}%` }} />
      ))}
    </div>
  );
}

function CallTimer({ client }: { client: LiveVoiceClient | null }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds(Math.floor(client?.elapsedSeconds() ?? 0)), 500);
    return () => clearInterval(timer);
  }, [client]);
  return <span className="w-10 text-right font-mono text-[12px] tabular-nums text-muted">{`${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`}</span>;
}

export function Composer({
  onSend,
  onStartCall,
  onEndCall,
  voiceStatus,
  voiceClient,
  disabled,
}: {
  onSend: (text: string) => void;
  onStartCall: () => void;
  onEndCall: () => void;
  voiceStatus: VoiceStatus;
  voiceClient: LiveVoiceClient | null;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [muted, setMuted] = useState(false);
  const [speakerOff, setSpeakerOff] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const inCall = voiceStatus === "live" || voiceStatus === "connecting" || voiceStatus === "closing";

  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = `${Math.min(ref.current.scrollHeight, 160)}px`;
    }
  }, [text]);

  const submit = () => {
    const value = text.trim();
    if (!value || disabled) return;
    onSend(value);
    setText("");
  };

  return (
    <div className="rounded-2xl border border-line bg-surface px-3 pb-2 pt-2.5 shadow-sm">
      <textarea
        ref={ref}
        value={text}
        rows={1}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder={inCall ? "Type to guide ARIA while you talk…" : "Message ARIA…"}
        className="w-full resize-none bg-transparent px-1 text-[14.5px] leading-relaxed outline-none placeholder:text-faint"
      />
      <div className="mt-1.5 flex items-center gap-2">
        {inCall ? (
          <>
            <button
              onClick={() => {
                setMuted(!muted);
                voiceClient?.setMuted(!muted);
              }}
              title={muted ? "Unmute microphone" : "Mute microphone"}
              className={clsx("rounded-lg p-1.5", muted ? "bg-bad-soft text-bad" : "text-muted hover:bg-sunken")}
            >
              {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            </button>
            <button
              onClick={() => {
                setSpeakerOff(!speakerOff);
                voiceClient?.setSpeakerMuted(!speakerOff);
              }}
              title="Toggle speaker"
              className="rounded-lg p-1.5 text-muted hover:bg-sunken"
            >
              {speakerOff ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
            </button>
            {voiceStatus === "connecting" ? (
              <span className="flex flex-1 items-center gap-2 text-[12px] text-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Connecting to GPT-Live…
              </span>
            ) : (
              <LevelMeter client={voiceClient} />
            )}
            <CallTimer client={voiceClient} />
            <button onClick={onEndCall} title="End call" className="rounded-full bg-bad-soft p-1.5 text-bad hover:bg-bad hover:text-white">
              <X className="h-4 w-4" />
            </button>
          </>
        ) : (
          <>
            <button
              onClick={onStartCall}
              disabled={disabled}
              className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[12.5px] text-muted hover:bg-sunken hover:text-ink disabled:opacity-50"
            >
              <Phone className="h-4 w-4" /> Talk to ARIA
            </button>
            <div className="flex-1" />
          </>
        )}
        <button
          onClick={submit}
          disabled={!text.trim() || disabled}
          className="rounded-full bg-ink p-1.5 text-white transition disabled:bg-faint/50"
          title="Send"
        >
          <ArrowUp className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

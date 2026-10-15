"use client";

import clsx from "clsx";
import { AlertTriangle, Mic, Phone, PlayCircle, Radio, Volume2 } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { SessionView } from "@/lib/session-state";
import type { ConversationItem, VoiceLine } from "@/lib/types";
import { formatTime } from "../ui";
import { ActivityBlock } from "./ActivityBlock";
import { CardItem } from "./Cards";

function AgentAvatar() {
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-ink text-white">
      <Radio className="h-3.5 w-3.5" />
    </span>
  );
}

function AgentMessage({ item }: { item: Extract<ConversationItem, { kind: "agent" | "say" }> }) {
  const spoken = item.kind === "agent" && item.spoken;
  return (
    <div className="flex gap-3">
      <AgentAvatar />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-[12px]">
          <span className="font-semibold">ARIA</span>
          <span className="text-faint">{formatTime(item.ts)}</span>
          {spoken && (
            <span className="flex items-center gap-1 text-faint">
              <Volume2 className="h-3 w-3" /> spoken
            </span>
          )}
        </div>
        <div
          className={clsx(
            "prose-aria mt-0.5 text-[14.5px]",
            item.kind === "say" && "text-ink/85",
            item.kind === "agent" && item.error && "text-bad",
          )}
        >
          <Markdown remarkPlugins={[remarkGfm]}>{item.text}</Markdown>
        </div>
      </div>
    </div>
  );
}

function OperatorBubble({ text, voice, queued, pending }: { text: string; voice?: boolean; queued?: boolean; pending?: boolean }) {
  return (
    <div className="flex flex-col items-end">
      <div className={clsx("max-w-[78%] rounded-2xl bg-sunken px-4 py-2.5 text-[14.5px] leading-relaxed", pending && "opacity-60")}>
        {voice && <Mic className="mr-1.5 inline h-3.5 w-3.5 -translate-y-px text-muted" />}
        {text}
      </div>
      {queued && <span className="mr-2 mt-1 text-[11px] text-faint">Added to the running investigation</span>}
    </div>
  );
}

const SYSTEM_ICON = { call: Phone, session: PlayCircle, report: PlayCircle, safety: AlertTriangle, error: AlertTriangle, investigation: PlayCircle };

export function Conversation({
  view,
  pendingVoice,
  onOpenPanel,
}: {
  view: SessionView;
  pendingVoice: VoiceLine[];
  onOpenPanel: (tab: "investigation" | "report") => void;
}) {
  return (
    <div className="space-y-5">
      {view.items.map((item) => {
        switch (item.kind) {
          case "system": {
            const Icon = SYSTEM_ICON[item.icon];
            return (
              <div key={item.id} className="flex items-center gap-2 pl-10 text-[13px] text-muted">
                <Icon className="h-3.5 w-3.5" /> {item.text}
              </div>
            );
          }
          case "operator":
            return <OperatorBubble key={item.id} text={item.text} voice={item.source === "voice"} queued={item.queued} />;
          case "agent":
          case "say":
            return <AgentMessage key={item.id} item={item} />;
          case "activity":
            return <ActivityBlock key={item.id} block={item} view={view} />;
          case "card":
            return (
              <div key={item.id} className="pl-10">
                <CardItem card={item.card} refId={item.ref} view={view} onOpenPanel={onOpenPanel} />
              </div>
            );
        }
      })}
      {pendingVoice.map((line, index) =>
        line.speaker === "operator" ? (
          <OperatorBubble key={`pv${index}`} text={line.text} voice pending />
        ) : (
          <div key={`pv${index}`} className="flex gap-3 opacity-70">
            <AgentAvatar />
            <p className="mt-4 text-[14.5px] italic">{line.text}</p>
          </div>
        ),
      )}
    </div>
  );
}

"use client";

import clsx from "clsx";
import { ArrowUpRight, ChevronRight, CornerDownRight, Lightbulb, Radio } from "lucide-react";
import { useEffect, useState } from "react";
import type { SessionView } from "@/lib/session-state";
import type { ConversationItem } from "@/lib/types";
import { Collapsible } from "../ui";
import { RetrievalPlanView } from "./Cards";
import { ToolLine } from "./ToolLine";

type Activity = Extract<ConversationItem, { kind: "activity" }>;

function useElapsed(start: string, end?: string) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (end) return;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [end]);
  return Math.max(0, Math.round(((end ? new Date(end).getTime() : now) - new Date(start).getTime()) / 1000));
}

export function ActivityBlock({ block, view }: { block: Activity; view: SessionView }) {
  const seconds = useElapsed(block.startedAt, block.endedAt);
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const open = userOpen ?? block.open;
  const entries = block.entries.filter((e) => !(e.kind === "tool" && view.tools[e.callId]?.name === "notify_operator"));
  const tools = entries.filter((e) => e.kind === "tool").length;

  return (
    <div className="pl-10">
      <button onClick={() => setUserOpen(!open)} className="flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
        <ChevronRight className={clsx("h-3.5 w-3.5 transition-transform", open && "rotate-90")} />
        <span className={clsx(block.open && "shimmer-text")}>
          {block.open ? "Working" : "Worked"} for {seconds}s
        </span>
        {tools > 0 && <span className="text-faint">· {tools} tool calls</span>}
      </button>
      {open && (
        <div className="mt-1.5 space-y-1 border-l border-line pl-4">
          {entries.map((entry, index) => {
            switch (entry.kind) {
              case "tool":
                return view.tools[entry.callId] ? <ToolLine key={entry.callId} tool={view.tools[entry.callId]} /> : null;
              case "thinking":
                return (
                  <Collapsible
                    key={index}
                    summary={
                      <span className="flex items-center gap-1.5">
                        <Lightbulb className="h-3.5 w-3.5" /> Thoughts
                      </span>
                    }
                  >
                    <p className="whitespace-pre-line pl-5 text-[12.5px] leading-relaxed text-muted">{entry.text}</p>
                  </Collapsible>
                );
              case "delegation":
                return (
                  <div key={index} className="flex items-start gap-2 text-[13px] leading-6">
                    <ArrowUpRight className="mt-[5px] h-3.5 w-3.5 shrink-0 text-accent" />
                    <span>
                      <span className="font-medium text-accent">Delegated by GPT-Live</span>
                      <span className="text-muted"> · client · </span>
                      <span className="text-ink/80">“{entry.transcript || "operator request"}”</span>
                    </span>
                  </div>
                );
              case "context":
                return (
                  <div key={index} className="flex items-start gap-2 text-[12px] leading-5 text-faint">
                    <Radio className="mt-[3px] h-3 w-3 shrink-0" /> <span className="line-clamp-2">{entry.text}</span>
                  </div>
                );
              case "queued":
                return (
                  <div key={index} className="flex items-start gap-2 text-[12.5px] text-muted">
                    <CornerDownRight className="mt-[3px] h-3.5 w-3.5 shrink-0" /> Operator input queued into the running loop: “{entry.text}”
                  </div>
                );
              case "retrieval":
                return view.retrievals[entry.planIndex] ? (
                  <RetrievalPlanView key={index} plan={view.retrievals[entry.planIndex]} />
                ) : null;
            }
          })}
        </div>
      )}
    </div>
  );
}

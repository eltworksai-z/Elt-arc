"use client";

import clsx from "clsx";
import { BookOpen, FlaskConical, MessageSquarePlus, Radio } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SessionRow } from "@/lib/types";
import { Orb, relativeTime } from "../ui";

const NAV = [
  { href: "/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/evals", label: "Evaluations", icon: FlaskConical },
];

export function Sidebar() {
  const pathname = usePathname();
  const [sessions, setSessions] = useState<SessionRow[]>([]);

  useEffect(() => {
    const load = () => api<SessionRow[]>("/api/sessions?kind=live").then((rows) => setSessions(rows.filter((r) => r.summary || r.title !== "New conversation"))).catch(() => undefined);
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [pathname]);

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-line bg-[#f5f3ef]">
      <Link href="/" className="flex items-center gap-2.5 px-4 pb-3 pt-4">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink text-white">
          <Radio className="h-4 w-4" />
        </span>
        <div>
          <div className="text-[15px] font-semibold leading-tight">ARIA</div>
          <div className="text-[11px] text-muted">Voice assistant</div>
        </div>
      </Link>

      <div className="px-3">
        <Link
          href="/"
          className="flex w-full items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-[13px] font-medium shadow-sm hover:border-accent/40"
        >
          <MessageSquarePlus className="h-4 w-4 text-accent" /> New conversation
        </Link>
      </div>

      <nav className="mt-3 space-y-0.5 px-3">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              "flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-[13px]",
              pathname.startsWith(href) ? "bg-surface font-medium text-ink shadow-sm" : "text-muted hover:bg-surface/70 hover:text-ink",
            )}
          >
            <Icon className="h-4 w-4" /> {label}
          </Link>
        ))}
      </nav>

      <div className="mt-5 px-4 text-[11px] font-semibold uppercase tracking-wider text-faint">Conversations</div>
      <div className="mt-1 flex-1 space-y-0.5 overflow-y-auto px-2 pb-4">
        {sessions.length === 0 && <p className="px-2 py-3 text-[12px] text-faint">No conversations yet.</p>}
        {sessions.map((session) => (
          <Link
            key={session.id}
            href={`/sessions/${session.id}`}
            className={clsx(
              "flex items-start gap-2.5 rounded-lg px-2 py-2",
              pathname === `/sessions/${session.id}` ? "bg-surface shadow-sm" : "hover:bg-surface/60",
            )}
          >
            <Orb seed={session.id} size={30} />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-[13px] font-medium">{session.title}</span>
                <span className="shrink-0 text-[10px] text-faint">{relativeTime(session.updated_at)}</span>
              </div>
              <p className="truncate text-[11.5px] text-muted">{session.summary || "No messages yet"}</p>
            </div>
          </Link>
        ))}
      </div>
    </aside>
  );
}

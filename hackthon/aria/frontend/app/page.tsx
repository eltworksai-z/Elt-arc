"use client";

import { AlertTriangle, ArrowUp, Loader2, Mic, Radio } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { startConversation } from "@/lib/conversations";

export default function Home() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);

  useEffect(() => {
    api<{ openai_configured: boolean }>("/api/health")
      .then((h) => !h.openai_configured && setWarning("OPENAI_API_KEY is not set in aria/backend/.env."))
      .catch(() => setWarning("Backend not reachable on port 8000."));
  }, []);

  const open = async (message?: string, call = false) => {
    setBusy(true);
    try {
      const id = await startConversation(message);
      router.push(`/sessions/${id}${call ? "?call=1" : ""}`);
    } catch {
      setWarning("Backend not reachable on port 8000.");
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col items-center justify-center px-6">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-ink text-white">
        <Radio className="h-6 w-6" />
      </span>
      <h1 className="mt-4 text-2xl font-semibold">ARIA</h1>

      <button
        onClick={() => open(undefined, true)}
        disabled={busy}
        className="mt-8 flex h-20 w-20 items-center justify-center rounded-full bg-ink text-white shadow-lg transition hover:scale-105 disabled:opacity-50"
        title="Call ARIA"
      >
        {busy ? <Loader2 className="h-7 w-7 animate-spin" /> : <Mic className="h-8 w-8" />}
      </button>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) void open(text.trim());
        }}
        className="mt-8 flex w-full max-w-xl items-center gap-2 rounded-2xl border border-line bg-surface px-4 py-2.5 shadow-sm"
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Or type to ARIA…"
          className="flex-1 bg-transparent text-[14.5px] outline-none placeholder:text-faint"
        />
        <button type="submit" disabled={!text.trim() || busy} className="rounded-full bg-ink p-1.5 text-white disabled:bg-faint/50">
          <ArrowUp className="h-4 w-4" />
        </button>
      </form>

      {warning && (
        <p className="mt-4 flex items-center gap-1.5 text-[12.5px] text-warn">
          <AlertTriangle className="h-3.5 w-3.5" /> {warning}
        </p>
      )}
    </div>
  );
}

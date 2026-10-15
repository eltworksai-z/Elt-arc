# ARIA — voice assistant for the production line

You call ARIA and talk to it, like calling an experienced colleague. GPT-Live handles the conversation. Whenever your words need real work, GPT-Live hands that work to ARIA's backend agent. The agent then searches the manuals, reads the incident history, reads the machine, runs diagnostics or writes a report, and you see that work happening in the conversation as it runs. When the work is done, the result is spoken back to you.

Nothing is pre-scripted. There are no menus or suggested questions: you ask, and the agent decides which tools it needs. Only the data behind the tools is simulated: the palletizing cell PAL-01, its incident history and its maintenance plan.

## How a call flows

```
You speak ─▶ GPT-Live (voice, turn-taking, interruptions)
                │  delegation
                ▼
          ARIA backend agent ──▶ tools: manuals (RAG) · incident history (temporal KB) ·
                │                       machine signals · diagnostic tests · maintenance plan ·
                │                       report + verification · work orders
                ▼
   work streams into the chat ("Searching manuals…", "Ran T_GRIP_SENSOR_DIAG → …")
                │
                ▼
GPT-Live speaks the result ◀── commentary
```

## Example conversations

**You ask a question, and ARIA answers from the manuals (RAG).**
> You: "What is the A-301 alarm?"
> *ARIA searches the manuals and the result appears in the chat.*
> ARIA: "A-301 means the gripper close command was on but the closed sensor B21 didn't confirm within 1.5 seconds. Per the PAL-200 guide the usual cause is B21 out of alignment after a finger change."

> You: "What gap should B21 be set to?" → "1.0 millimetre, plus or minus 0.2. Switching distance is 2.0."

**You ask about history, and ARIA answers from the temporal knowledge base.**
> You: "Has this happened before?"
> *ARIA searches the incident history.*
> ARIA: "Twice on this cell, both right after finger changes, in INC-2025-118 and INC-2026-112. A keyed bracket was ordered after the second one but isn't fitted yet."

**You ask how to do something, and ARIA walks you through it.**
> You: "Walk me through cleaning the pick photo-eye."
> ARIA gives the procedure a step or two at a time, starting with lockout, and waits for you to say "done".
> You: "Done, margin reads 150 percent." ARIA records the work, and the knowledge base updates.

**You report a problem, and ARIA troubleshoots during the call.**
> You: "The palletizer has stopped. Find the cause."
> ARIA: "I'll check the alarms and signals first."
> *Snapshot read, alarm history read, incident history searched, hypotheses ranked, sensor diagnostics run…*
> You (while it works): "The gripper was serviced this morning."
> *Your remark goes into the running investigation and raises belief in sensor misalignment. The tests still decide.*
> ARIA: "The close command is on but B21 doesn't see the jaw: it reads 2.9 mm against a 2.0 mm switching distance. Most likely B21 was knocked out of position during this morning's service."
> You: "Can you restart it?"
> ARIA: "I can't restart the cell. An authorized technician needs to realign B21 per procedure 4.1 first. Want me to raise a work order?"
> ARIA speaks about the report only after it has been written, re-read and verified.

**You ask to see something, and ARIA puts it on screen.**
> You: "Show me the line status." / "Put the alarms on screen." / "Show me what you found."
> ARIA renders a live card in the chat (line status, alarm history, maintenance plan, incident history, or the investigation's hypotheses and decision) and says one sentence about it. Nothing is shown unless you ask or it is part of the work you asked for.

**You keep talking while ARIA works (full duplex).**
> GPT-Live keeps listening and speaking while the backend runs. Anything you add mid-task ("the gripper was serviced this morning") is delegated too and folded into the running work. You see it marked "added to the running investigation".

**You ask about maintenance, and ARIA checks the CMMS.**
> You: "Anything overdue on the palletizer?" → "B12 lens cleaning and the infeed belt inspection are overdue, and the filter-regulator check is due this week."

## Debug view

Open the side panel and go to **Debug** during or after a call. It draws the call as parallel lanes: user audio (in), user text (ASR), thinking, backend, agent text and agent audio (out). It marks where GPT-Live delegated, where the backend result was injected, and where the agent spoke the result. Delegate-to-result latency is shown alongside. The **Live** tab lists every delegation and its status.

## Simulated plant state

The cell's current state is set in `backend/.env`:

```
PLANT_SCENARIO=gripper_feedback_missing
```

| Value | What the cell is doing | What ARIA should find |
|---|---|---|
| `normal_operation` | Running in AUTO | No fault; it answers questions only |
| `gripper_feedback_missing` | Stopped with A-301 | B21 sensor misaligned after service |
| `gripper_low_air` | Stopped with A-301, closed feedback late | Low air pressure, not the sensor |
| `case_missing_photoeye` | Waiting at pick with A-210 | Dirty photo-eye B12, not upstream starvation |
| `light_curtain_interlock` | Holding at place with S-120 | Stretch film blocking light-curtain beams; needs a human reset |

ARIA is never told the state. It only sees what its tools return. Restart the backend after changing the value.

## Architecture

| Layer | Where | What it does |
|---|---|---|
| Voice | `frontend/lib/live-voice.ts`, `backend/app/voice/live.py` | GPT-Live over WebRTC with client delegation. Each `session.delegation.created` goes to the backend. Progress and results return via `session.commentary.append` (spoken) or `session.thinking.append` (silent context). |
| Agent | `backend/app/agents/` | OpenAI Agents SDK runner with streaming and strict tools. Speech that arrives mid-task is fed into the running loop. |
| Investigation engine | `backend/app/agents/engine.py`, `data/fault_model.json` | Ranks hypotheses, eliminates by rules, picks the next test by information gain, and applies stop rules. The model proposes; the engine decides. |
| RAG | `backend/app/rag/` | PDF chunking with section headers, BM25 plus embeddings with RRF fusion, LLM reranking, and multi-step retrieval with retry. |
| Temporal KB | `backend/app/memory/` | Timestamped incidents and events. Facts carry valid_from and valid_until, and newer facts supersede older ones. |
| Evaluation | `backend/app/evals/` | Simulated caller ↔ agent conversations, observer, judge and deterministic checks, comparing baseline vs ARIA. The voice tier relays audio between two GPT-Live sessions. |

## Run

```powershell
# backend (Python 3.12+)
cd aria/backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env          # set OPENAI_API_KEY
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# frontend (Node 24)
cd aria/frontend
npm install
copy .env.example .env.local
npm run dev                     # http://localhost:3000
```

After adding the key, open **Knowledge**, then **Build temporal facts** and **Re-index folder**. Put your PDF manuals in `backend/data/manuals` or upload them on that page.

## Honest limits

The plant, its history, the CMMS and the PAL-200 guide are simulated. ARIA never restarts, resets or moves equipment. Evaluation numbers are only what your own runs measure.

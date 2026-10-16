# ARIA — 4-minute hackathon demo script

**Setup before you present:** set `PLANT_SCENARIO=gripper_feedback_missing` in `backend/.env`. Start the backend and frontend. Open http://localhost:3000 and use a headset.

---

## 1. Problem (20 s)

> "When a machine on a packaging line stops, the operator can see that it stopped but not why. A technician then spends the first part of the stop correlating alarms, signals, manuals and old incident notes before touching anything. That search is downtime."

## 2. What ARIA is (20 s)

> "ARIA is a voice assistant for the line, built on OpenAI GPT-Live. You call it like a colleague. It answers from the manuals, remembers the line's history, and when something breaks it troubleshoots live while you keep talking. It does this with real tool calls: it reads the machine, runs only permitted tests, and verifies its own report before it tells you anything."

## 3. Live demo (2 min 30 s)

Tap the mic and speak naturally. Point at the screen as the work appears.

| You say | What the audience sees |
|---|---|
| "What does alarm A-301 mean?" | **Knowledge base (RAG):** "Searching manuals", then the answer, cited to the PAL-200 guide. |
| "Has this happened before?" | **Temporal KB:** incident history with dates. A fact that has since changed is shown as superseded. |
| "The palletizer has stopped. Find the cause." | **Delegation:** ARIA says "let me check" right away while the backend starts working. Tool lines stream in: machine snapshot, alarm history, incident history, manuals, ranked hypotheses, diagnostic test. |
| *(while it is still working)* "The gripper was serviced this morning." | **Full duplex:** ARIA keeps listening. Your remark is delegated again and marked "added to the running investigation", and the hypotheses shift. |
| "Show me what you found." | **Visual on request:** the hypotheses card with the engine's decision and confidence appears in the chat. |
| *(ARIA speaks)* | "B21 reads 2.9 mm against a 2.0 mm switch point. Realign per procedure 4.1. Report saved and verified." |
| "Can you restart it?" | **Safety:** declined by policy, with the safe alternative. ARIA offers a work order. |
| "Yes, raise it." | A work order card appears. |

## 4. Under the hood (40 s)

Open the side panel and go to **Debug**, or show `docs/aria_call_timeline.png`.

> "This is the call as GPT-Live sees it. User audio keeps flowing while the backend works asynchronously. The voice model delegates, says a filler, keeps listening, and takes in my extra information. When the result is injected through `commentary.append` it speaks the verified answer. Background facts go in silently through `thinking.append`."

Key points, one line each:
- **GPT-Live with client delegation:** voice and turn-taking up front, the ARIA agent (OpenAI Agents SDK, strict function tools) in the back.
- **Knowledge:** hybrid RAG over the PDF manuals plus a temporal knowledge graph of incidents in which facts have validity windows.
- **The model proposes, the engine decides:** hypotheses are updated from actual test results, tests are chosen by information gain, permissions are deterministic, and stop rules are explicit.
- **Report:** written, re-read from disk and verified against the evidence before ARIA says it is done.
- **Evaluation:** a simulated caller talks to ARIA and to a baseline agent on the same hidden faults. We score diagnosis accuracy, grounding, unnecessary tests and safety.

## 5. Close (15 s)

> "ARIA doesn't just explain an alarm. It investigates while you talk, shows its evidence, and tells you the next safe action. The machine here is simulated; the reasoning, the tool calls and the voice are real."

---

**If something goes wrong**
- Voice fails: type the same lines. The flow and the on-screen work are identical.
- Quote evaluation numbers only from a run you actually executed on the **Evaluations** page, with the run id.

# ARIA — video narration

One continuous story. Each header is the slide on screen; read the narration straight through. Every section ends by handing over to the next slide, so the video flows. Total ≈ 6 minutes.

---

## Slide 1 — The use case

Picture a manufacturing plant. At the end of a packaging line sits a robotic palletizing cell. Cases arrive on a conveyor, a robot arm with a gripper picks them up, and stacks them onto a pallet. A programmable logic controller — the PLC — coordinates the conveyor, the robot, the gripper and the safety interlocks. Sensors confirm every condition: a case is present, the gripper has closed. If a required confirmation does not arrive, the PLC stops the sequence and raises an alarm.

The operator sees that the cell has stopped — but not why. A maintenance technician then has to correlate the alarm history, the live sensor signals, the sequence conditions, the equipment manuals and previous incidents before deciding what to inspect. That manual search is the downtime.

ARIA turns that search into an evidence-based investigation, through a voice conversation. It understands the operator's request, gathers the machine state, alarms, event history, procedures and past incidents, keeps fault hypotheses with evidence for and against each, runs only permitted diagnostic tests, observes the actual results, and updates its hypotheses. It stops when the evidence is sufficient, when no safe test remains, or when a human is needed. Then it writes a report grounded in the tool results, verifies it, and explains the next safe action in speech.

In this demo the palletizer and its faults are simulated. ARIA never claims to repair or restart equipment.

---

## Slide 2 — Built on OpenAI: GPT-Live delegates, reasoning models do the work

ARIA's voice is OpenAI GPT-Live — a full-duplex model. It listens and speaks at the same time, on one continuous stream.

Here is the key difference from a classic voice bot. A classic bot waits for you to finish, converts speech to text, thinks, then answers — one turn at a time. GPT-Live doesn't wait. As soon as it understands that the operator needs real work — "the palletizer stopped, find the cause" — it delegates that work to the backend, and the backend starts immediately. GPT-Live stays in the conversation: it says "let me check", keeps listening, and if the operator adds something — "the gripper was serviced this morning" — that is delegated too, straight into the work already running.

The work itself is done by a reasoning model, gpt-5.6-terra, inside the ARIA agent built on the OpenAI Agents SDK. It runs one bounded reasoning loop: read the machine state and incident context, propose fault hypotheses, apply deterministic machine rules to eliminate inconsistent ones, select the highest-value permitted test, call the diagnostic tool and wait for the actual result, update the ranking — and repeat until a stop condition is reached. Then it writes and verifies the report.

When the result is ready, it is injected back into the live call — what to say through commentary, background facts through thinking — and GPT-Live speaks it.

So the operator never waits in silence. The talking and the reasoning happen at the same time.

Let's start with the simplest thing an operator does: ask a question.

---

## Slide 3 — Scenario 1: Ask a question, get the answer from the manual

In this video, the worker asks what alarm A-301 means.

GPT-Live hands the question to the agent, and you can see the work appear: it searches the manuals. Behind that, the manual is split into sections, searched with both keywords and meaning, and the best passages are reranked before answering. So the answer comes straight from the PAL-200 guide: the gripper was told to close, but the closed sensor B21 never confirmed — usually because B21 shifted after a finger change.

Then the worker asks a follow-up: what gap should B21 be set to? One millimetre, plus or minus point two. Exact, cited, and if it isn't in the manual, ARIA says so instead of guessing.

But manuals only tell you how things should be. To troubleshoot well, you also need to know what actually happened on this line.

---

## Slide 4 — How the line's memory works

That's the temporal knowledge base.

Every past incident is stored as a timeline of events — the alarm, the tests, the repair, the result. From those records, ARIA extracts facts, and every fact carries time: when it became true, and whether something later replaced it.

So ARIA doesn't just know facts — it knows which are still true. The sensor is still on the old slotted bracket. A keyed bracket was ordered, but it's not fitted yet. And the photo-eye was upgraded last month, so the old model is marked as superseded.

Here's what that looks like in a conversation.

---

## Slide 5 — Scenario 2: Ask about history

In this video, the worker asks: has this happened before?

ARIA searches the incident history — matching on the alarm, the component and how recent it was — and answers: twice on this cell, both right after gripper finger changes, and the fix that was ordered still isn't fitted.

That's the difference between a search box and a memory of the line. History is treated as a clue, though, not proof. To know what's wrong right now, ARIA has to look at the machine itself.

---

## Slide 6 — How ARIA troubleshoots

When the cell stops, ARIA runs a loop: investigate, test, observe, update, decide — and repeat until it's sure. Then it writes a report, verifies it, and explains.

The key principle is simple: the model proposes, the engine decides. The language model understands the worker and suggests possible causes. But a deterministic engine updates those beliefs only from real test results, picks the test that will tell us the most next, and decides when there's enough evidence to stop.

Safety is built in. Tests that would move equipment are blocked unless conditions allow it. ARIA never restarts, resets or bypasses anything. And the report is re-read and checked against the evidence before ARIA says a word about it.

Let's watch it handle a real stop.

---

## Slide 7 — Scenario 3: Report a problem, troubleshoot on the call

In this video, the worker says: the palletizer has stopped, find the cause.

ARIA answers straight away — "I'll check the alarms and signals first" — and the work streams in on screen: it reads the machine, checks the alarm history, looks at past incidents and the manual, ranks the possible causes, and starts testing.

While it's still working, the worker adds: the gripper was serviced this morning. ARIA takes that in mid-task. It raises its suspicion of the sensor — but the tests still decide.

The sensor diagnostic confirms it: B21 reads 2.9 millimetres against a 2.0 millimetre switching distance. It was knocked out of position during the service.

Then the worker asks: can you restart it? And ARIA refuses — safely. The sensor has to be realigned by an authorized technician first. It offers to raise a work order instead.

The worker can also ask to see any of this on screen.

---

## Slide 8 — What ARIA can show

When the worker asks, ARIA draws a live card right in the conversation: the line status, the alarm history, the maintenance plan, past incidents, or what it found in the investigation.

Each card is built from the same tools the agent uses, at the moment you ask. There's no fixed dashboard to click through, and nothing appears unless you ask for it.

---

## Slide 9 — Scenario 4: Ask to see it

In this video, the worker says: show me the line status — and the card appears with the active alarm and the condition the sequence is waiting on. Then: show me what you found — and ARIA shows its ranked causes and why it stopped testing.

The worker stays hands-free. They just ask, and the right picture shows up.

All of this works because the conversation never has to pause. Let's look at why.

---

## Slide 10 — How full duplex works

This timeline shows one call, lane by lane.

The worker speaks. GPT-Live delegates the work, says "let me check," and keeps listening. In the purple lane, the backend is working in the background. Meanwhile the worker adds something — that's delegated too, and folded into the work already running. When the result is ready, it's injected back, and ARIA speaks the verified answer.

The app's debug view draws these same lanes from a real call.

---

## Slide 11 — Scenario 5: Keep talking while ARIA works

In this video, the worker interrupts ARIA mid-investigation with new information.

There's no waiting for a turn and no starting over. ARIA acknowledges it, marks it as added to the running investigation, and uses it in the next step — just like talking to an experienced colleague.

So what does all of this mean for the plant?

---

## Slide 12 — Business value

First, faster diagnosis. The evidence, the manual and the history come together in one call, instead of a walk between the panel, the binder and the expert.

Second, fewer wasted tests. Every test is chosen for what it will tell you, and we measure unnecessary tests against a baseline agent.

Third, safety by design. No remote restarts, no bypassing interlocks, and every report is verified before it's spoken.

And fourth, knowledge that stays. Every diagnosis and every logged fix goes back into the line's memory, so a new technician starts with a veteran's context.

We prove it by running ARIA and a baseline agent against the same hidden faults, scoring accuracy, grounding, wasted tests and safety.

ARIA doesn't just explain an alarm. It investigates with you — and tells you the next safe step.

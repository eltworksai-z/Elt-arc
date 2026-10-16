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

In this video, the operator asks: what does alarm A-301 mean?

GPT-Live delegates the question, and the work appears on screen: searching manuals. Behind that line, the equipment manual has been split into sections, each tagged with its title and page. ARIA searches them two ways at once, by exact keywords like "A-301" and by meaning, merges the two rankings, and then a second model rereads the best passages and keeps only the ones that actually answer the question.

So the answer is grounded: the close command was on, but the closed-position sensor B21 did not confirm within one and a half seconds. Per the PAL-200 guide, section 3, the most common cause is B21 knocked out of alignment after a gripper finger change.

The operator follows up: what gap should B21 be set to? One millimetre, plus or minus point two, against a two millimetre switching distance. That's procedure 4.1. Every answer names its source, and if the manual doesn't cover something, ARIA says so instead of guessing.

But a manual only tells you how the machine should behave. To troubleshoot this machine, you also need to know what has actually happened on this line.

---

## Slide 4 — How the line's memory works

That's the temporal knowledge base.

Every past incident is stored as a timestamped timeline: the alarm, the signal changes, the diagnostic tests, the repair, the technician's action and the outcome.

From those records, a model extracts individual facts and classifies each one. Some facts never change: "B21's switching distance is 2 millimetres." Some are one-off events: "valve Y4 was replaced." And some are states that can change over time: "B21 is mounted on the slotted bracket."

Every fact carries a validity window: when it became true, and when it stopped being true. When a newer fact contradicts an older one, the older one is marked superseded instead of deleted. So ARIA knows the sensor is still on the slotted bracket, that a keyed bracket was ordered but not yet fitted, and that the old photo-eye model was replaced last month.

It knows what is true today, and how it got there.

---

## Slide 5 — Scenario 2: Ask about history

In this video, the operator asks: has this happened before?

ARIA searches the incident history. It ranks past incidents by how similar they are, boosted when the alarm code matches, when the component matches, and when the incident is recent. It returns each incident with its full timeline, plus the facts that are still valid.

The answer: twice on this cell, INC-2025-118 and INC-2026-112, both within an hour of a gripper finger change, and both fixed by realigning B21. A keyed bracket was ordered after the second one, and it isn't fitted yet.

That's the difference between a search box and a memory of the line. But ARIA treats history as a clue, not as proof. To know what is wrong right now, it has to investigate the machine itself.

---

## Slide 6 — How ARIA troubleshoots

When the cell stops, ARIA runs one bounded reasoning loop.

First it gathers evidence: the machine snapshot, the alarm history with timestamps, and a trace of the sequence step showing which condition is not satisfied.

Then it builds hypotheses. For a gripper-close alarm, the fault model gives five candidates: the closed sensor is misaligned, the air pressure is low, the valve isn't switching, the jaws are jammed, or the sensor cable is faulty. The reasoning model gives each one a starting likelihood, based on the snapshot, the history and anything the operator said.

Now the engine takes over. For every permitted test, it calculates how much that test would separate the remaining hypotheses, and it runs the one with the highest information gain. It reads the actual result and updates every hypothesis: evidence for, evidence against. Hypotheses that fall below two percent are ruled out.

It stops when one cause reaches ninety percent confidence with supporting evidence and nothing against it. It also stops when no useful safe test remains, or when the test budget or time limit runs out. In those cases it says it is uncertain and asks for a technician, instead of inventing a cause.

Safety is enforced in code, not left to the model. A test that would move the gripper is blocked unless the robot is at home and the cell is out of automatic mode. Restart, reset and bypass requests are always declined.

The model proposes. The engine decides.

Let's watch it handle a real stop.

---

## Slide 7 — Scenario 3: Report a problem, troubleshoot on the call

In this video, the operator says: the palletizer has stopped, find the cause.

ARIA opens an incident and answers straight away: I'll check the alarms and signals first. On screen, the work streams in. It reads the machine: the cell is in fault at step 30, gripper close. The alarm history shows A-301. The sequence trace shows the close command is on, but the closed feedback is off.

It searches past incidents and the manual, then registers the five hypotheses. Sensor misalignment starts slightly ahead because of the history.

While it's working, the operator adds: the gripper was serviced this morning. That goes straight into the running investigation as new evidence, and ARIA raises its belief in sensor misalignment. But that is only a nudge. The tests still decide.

The engine picks the most informative test: the B21 IO-Link diagnostic. The result: the sensor sees the jaw at 2.9 millimetres, beyond its 2.0 millimetre switching point. That rules out the jam and the valve. The next test, the valve coil check, shows the valve is energized, which confirms air is reaching the gripper. A manual gripper cycle would also help, but the engine blocks it because the robot isn't at home, so moving the gripper over a case needs a technician.

Sensor misalignment is now above ninety percent with supporting evidence, so the loop stops.

ARIA writes the report, re-reads it from disk, and verifies it: every evidence reference exists, the tests listed are exactly the tests that ran, the diagnosis and confidence match the engine, and a separate model checks that every claim is backed by the evidence. Only then does it speak: B21 reads 2.9 millimetres against a 2.0 millimetre switching distance, most likely knocked out of position during this morning's service. The report is saved and verified.

The operator asks: can you restart it? ARIA routes that through the safety policy and declines. B21 needs to be realigned per procedure 4.1 by an authorized technician first. It offers a work order, and when the operator agrees, it creates one with the evidence attached.

---

## Slide 8 — What ARIA can show

All of this can also be shown on screen, but only when the operator asks.

ARIA can draw five kinds of live card right in the conversation: the line status with alarms and sequence conditions, the alarm history, the maintenance plan with what is overdue, past incidents with their timelines, and the investigation itself, with every hypothesis, its confidence and the engine's decision.

Each card is built at that moment from the same tools the agent uses. There's no separate dashboard to maintain, and nothing appears unless it was asked for.

---

## Slide 9 — Scenario 4: Ask to see it

In this video, the operator says: show me the line status. The card appears: fault at step 30, alarm A-301, close command issued, closed feedback missing.

Then: show me what you found. ARIA shows the investigation card: sensor misalignment at about ninety-two percent, the other causes ruled out or far behind, and why it stopped testing.

The operator never clicks through a dashboard. They ask, and the right picture shows up, while their hands stay on the machine.

All of this depends on one thing: the conversation never has to pause.

---

## Slide 10 — How full duplex works

This timeline shows one real call, lane by lane, at the same time scale.

At the top, the operator's audio and the live transcript. The operator says: the palletizer stopped, find the cause. GPT-Live delegates immediately, says "let me check", and keeps listening.

In the purple backend lane, the reasoning model gets to work. Each dot is a tool call: snapshot, alarms, incident history, manuals, hypotheses, tests, report, verification.

Mid-way, the operator speaks again. That is delegated too, and lands in the running investigation without restarting it. Short thinking updates keep GPT-Live aware of what has been found, without speaking them.

When the verified result is ready, it's injected back into the call, and the agent speaks it. At the end, the restart request is declined.

The app's debug view draws these same lanes from a live call.

---

## Slide 11 — Scenario 5: Keep talking while ARIA works

In this video, the operator interrupts ARIA mid-investigation with new information.

GPT-Live doesn't wait for its turn. It delegates the new information, the backend adds it to the running loop as operator evidence with its own reference, and the reasoning model can adjust its beliefs with it. The adjustment is capped, so a remark can shift a hypothesis but can never override a real test result.

On screen it is marked: added to the running investigation. ARIA acknowledges it in one short line and carries on. No starting over, no repeating yourself, just like talking to an experienced colleague.

And when the fix is done, the technician can say "I realigned B21 to one millimetre, twenty cycles OK", and ARIA records it into the line's memory, so the next investigation starts smarter.

So what does all of this mean for the plant?

---

## Slide 12 — Business value

First, faster diagnosis. The machine state, the manual and the line's history come together in one conversation, instead of a walk between the panel, the binder and the expert.

Second, fewer wasted tests. Every test is chosen for what it will reveal, and we count unnecessary tests against a baseline agent.

Third, safety by design. No remote restarts, no bypassed interlocks, tests that move equipment blocked by rule, and every report verified before it's spoken.

Fourth, knowledge that stays. Every diagnosis and every logged fix goes back into the line's memory, so a new technician on night shift starts with a veteran's context.

We prove it by running ARIA and a baseline agent against the same hidden faults, with a simulated GPT-Live caller, and scoring diagnostic accuracy, evidence grounding, unnecessary tests, report completion and safety.

ARIA doesn't just explain an alarm. It investigates with you, and tells you the next safe step.

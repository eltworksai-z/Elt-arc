FixPilot — Voice-First Industrial Troubleshooting Agent
1. Real-world use case
A realistic place for FixPilot is a manufacturing plant's robotic palletizing cell at the end of a packaging line. Cases arrive on a conveyor, a robot arm with a gripper picks them up, and the robot stacks them onto a pallet. A programmable logic controller (PLC) coordinates the conveyor, robot, gripper, and safety interlocks. Sensors confirm conditions such as a case being present and the gripper being closed. If a required confirmation does not arrive, the PLC may stop the sequence and raise an alarm.
When this happens, an operator can see that the cell has stopped but may not know why. A maintenance technician normally has to correlate alarm history, live sensor signals, sequence conditions, equipment manuals, and previous incidents before deciding what to inspect. FixPilot helps investigate the stop through a voice conversation, runs permitted software diagnostics against a simulated machine, explains the evidence, and recommends the next safe action. The hackathon demo uses a simulated palletizer and simulated faults, not a live industrial robot. It does not claim to physically repair or restart equipment.
2. Product definition
FixPilot is a voice-first autonomous troubleshooting agent for industrial machines. It turns troubleshooting from a manual search across alarms, signals, manuals, and incident notes into an evidence-based investigation.
The agent should:
Understand an operator's natural-language request through a live voice interface.
Gather machine state, alarms, event history, relevant procedures, and past incidents.
Maintain fault hypotheses and track evidence for and against each.
Select and execute the next permitted diagnostic test.
Observe the actual tool result and update its hypotheses.
Stop when evidence is sufficient, no safe/useful test remains, or human input is needed.
Generate a report grounded in tool results, verify that it was written correctly, and explain the next safe action in speech.
The central product behavior is investigate → test → observe → update → decide whether to continue → verify → explain. It should not be a chatbot that only describes what a technician might do.
3. The four core pieces — keep the scope focused
3.1 One reasoning loop
The agent investigates, observes results, selects its next test, and stops when it has sufficient evidence or needs a human.
Read incident context and current machine state.
Propose plausible fault hypotheses.
Apply deterministic machine/sequence rules to eliminate inconsistent hypotheses.
Select the highest-value permitted test that distinguishes remaining hypotheses.
Call the diagnostic tool and wait for its actual result.
Update evidence and hypothesis ranking.
Repeat until a stop condition is reached.
Write and verify the diagnosis report.
Use a bounded loop with a maximum number of tests and a clear timeout. If evidence is inconclusive, report uncertainty and request human help instead of inventing a cause.
3.2 One temporal memory
Store timestamped faults, diagnostic tests, repairs, and outcomes so a previous incident can inform a new investigation.
Use SQLite for the first implementation. Store:
Timestamp
Machine/cell identifier
Event type (alarm, signal change, diagnostic test, repair, result)
Signal or component
Observed value/result
Related incident ID
Technician action and outcome, when known
The agent can retrieve similar incidents, compare event order, and use past outcomes as supporting evidence. Historical similarity is not proof that the same fault has recurred; current machine evidence must still be checked.
Start with timestamped relational tables and indexed queries. Add a graph representation only if component relationships or multi-hop causal links materially improve retrieval. A graph database is not required for the MVP.
3.3 One live dashboard
Show the voice conversation, hypotheses, evidence, tool calls, decisions, and final verified report.
Recommended panels:
Conversation: operator turns, agent speech/transcript, interruptions, and clarifications.
Machine snapshot: simulated signals, active alarms, and current sequence/interlock state.
Hypotheses: candidate causes, confidence/rank, evidence for and against, and status.
Investigation timeline: timestamped milestones and observed test results.
Tool-call log: tool name, validated arguments, execution status, actual result, and errors.
Decision panel: why the next test was chosen, why the loop continues/stops, and whether a human is needed.
Verified report: final diagnosis, supporting evidence, uncertainty, recommended next safe action, and confirmation that the report matches the final result.
Use Streamlit for the first dashboard unless a custom browser frontend is essential for voice.
3.4 One evaluation suite
Run CRAWL, WALK, and RUN where applicable, and display baseline-versus-improved results. Use the OpenAI Cookbook voice-agent evaluation example as a development-time test harness, adapted to the industrial scenario. Confirm the exact interfaces and supported modes in the checked-out harness version.
CRAWL: controlled, simpler requests and single-turn tool/diagnosis tasks.
WALK: recorded audio and realistic speech conditions such as accents, noise, or ambiguous wording.
RUN: longer multi-turn conversations, interruptions, corrections, and new evidence arriving mid-investigation.
Create repeatable fault scenarios with hidden ground truth. Compare:
Baseline agent with model-driven tool selection.
Improved agent with deterministic machine rules.
Optionally, rules plus adaptive next-test selection.
Keep scenarios and tool permissions identical across versions. Measure:
Diagnostic accuracy against hidden ground truth
Evidence grounding
Correct tool selection and valid arguments
Number of diagnostic tests/tool calls
Time to completion
Report creation and verification
Safety violations (target: zero)
Voice response consistency with verified results
Show actual measured results; do not claim an improvement before running the suite. The evaluation harness is for development and regression testing, not a separate runtime agent in the product. Runtime still needs validation, permission checks, and verification of tool results.
4. End-to-end architecture
flowchart TD
    U[Operator] <--> V[GPT-Live / Realtime voice interface]
    V <--> A[Backend reasoning agent]
    A <--> R[Reasoning loop and hypothesis state]
    R <--> D[Deterministic machine rules and test selector]
    A <--> T[Typed diagnostic tools / function calling]
    T <--> S[Simulated palletizer and sensor/PLC state]
    A <--> M[Temporal incident memory / SQLite]
    A <--> K[Manuals and procedures / local search or RAG]
    A --> W[Report writer]
    W --> Q[Report verification]
    V --> UI[Live dashboard]
    A --> UI
    T --> UI
    M --> UI
    Q --> UI
    E[CRAWL / WALK / RUN evaluation suite] --> A
    E --> G[Graders and baseline-versus-improved metrics]
Responsibilities
Voice interface: low-latency audio, turn-taking, interruptions, spoken updates, and delivery of operator intent/context to the backend.
Backend agent: owns investigation state and coordinates multi-step tool calls.
Reasoning loop: decides what evidence is missing, which test to run next, and when to stop.
Deterministic rules: encode known machine sequence conditions and safety constraints. The model cannot override them.
Tools: return typed, auditable results. Tool success is not assumed until execution confirms it.
Temporal memory: stores timestamped incidents and outcomes.
Knowledge retrieval: finds relevant manual sections and procedures. Start with local documents; add hosted RAG only if useful.
Dashboard: visualizes the same state and events used by the agent.
Evaluation suite: tests behavior offline and measures regressions.
5. Voice conversation and tool flow
sequenceDiagram
    actor O as Operator
    participant V as GPT-Live Voice
    participant A as Backend Agent
    participant D as Diagnostic Engine
    participant T as Diagnostic Tools
    participant S as Simulator
    participant H as History / Reports

    O->>V: Speak request
    V->>A: Intent and conversation context
    A->>T: Read alarms and signal states
    T->>S: Query current simulated state
    S-->>T: Actual values and active alarms
    T-->>A: Typed tool result
    A->>H: Retrieve relevant past incidents
    H-->>A: Timestamped event sequences and outcomes
    A->>D: Hypotheses plus evidence
    D-->>A: Rule checks and next permitted test
    A->>T: Run diagnostic test
    T->>S: Execute safe simulated test
    S-->>T: Test result
    T-->>A: Actual test result
    A->>D: Update evidence and hypotheses
    D-->>A: Continue, stop, or request human
    A->>H: Write report
    H-->>A: Report path and write confirmation
    A->>H: Re-read and verify report
    A-->>V: Verified findings and next action
    V-->>O: Spoken explanation
Example voice exchange
Turn
Speaker
Conversation / action
What the system should do
1
Operator
“FixPilot, the palletizer has stopped. Find the cause.”
Start an investigation and create an incident record.
2
FixPilot
“I’ll check the current alarms and machine signals first.”
Give a short status update while the backend reads the machine snapshot.
3
System action
Read alarm history and current signal states.
Return actual simulated data with timestamps; log tool calls and results.
4
FixPilot
“There’s a gripper-close timeout. I’m checking whether the close command and feedback agree.”
Form and rank candidate hypotheses; select a safe, informative test.
5
System action
Inspect the gripper command, feedback signal, and sequence interlock.
Execute tools and record returned values; do not fabricate results.
6
Operator
“The gripper was serviced this morning.”
Treat this as new evidence; append it to the incident context and reconsider relevant history.
7
FixPilot
“That maintenance detail may be relevant. I’ll compare it with previous gripper-feedback incidents and verify the current signals.”
Retrieve related incidents and continue only with useful, permitted tests.
8
System action
Compare timestamped incident history and inspect the relevant signal state.
Rank hypotheses again and retain evidence for and against each.
9
FixPilot
“The close command is on, but the closed-feedback signal remains off. The sequence is waiting for that confirmation.”
Explain the supported finding and identify remaining uncertainty.
10
Operator
“Can you restart it?”
Apply the safety policy; do not restart or move equipment autonomously.
11
FixPilot
“I can’t restart the cell. The feedback condition is not satisfied. Please have an authorized technician inspect the sensor, wiring, and gripper according to the procedure.”
Decline the consequential action, state the reason, and recommend a safe next step.
12
System action
Write and re-read the diagnostic report.
Verify report contents against tool evidence, then mark the report complete.
13
FixPilot
“The report is saved. It records the timeout, the signal mismatch, the tests performed, and the recommended inspection.”
Speak only after report creation and verification succeed.
14
Evaluation suite
Run the same scenario against baseline and improved agents.
Score diagnosis, grounding, tool correctness, efficiency, report completion, and safety.
6. Diagnostic reasoning algorithm
flowchart TD
    A([New incident]) --> B[Read machine state and alarm timeline]
    B --> C[Retrieve similar timestamped incidents]
    C --> D[Generate candidate fault hypotheses]
    D --> E[Apply deterministic sequence rules]
    E --> F[Rank remaining hypotheses and permitted tests]
    F --> G[Execute next diagnostic test]
    G --> H[Observe actual result]
    H --> I[Update evidence and hypothesis ranking]
    I --> J{Enough evidence?}
    J -- No --> K{Safe useful test remains and budget available?}
    K -- Yes --> F
    K -- No --> L[Report uncertainty and request human]
    J -- Yes --> M[Prepare diagnosis and recommended next action]
    L --> N[Write report]
    M --> N
    N --> O[Re-read and verify report]
    O --> P[Speak result and update dashboard]
Stop conditions
Stop the loop when:
Evidence reaches a defined sufficiency threshold and no critical contradiction remains.
The maximum test count or time budget is reached.
No safe, permitted, useful test remains.
Required evidence is unavailable or tools fail.
Human judgment or authorized physical inspection is required.
The model can recommend a test, but deterministic permissions and machine safety rules decide whether it may execute.
7. Data and knowledge design
Temporal memory
Start with SQLite tables such as:
incidents: incident ID, machine ID, start/end time, summary, final diagnosis, outcome.
events: event ID, incident ID, timestamp, event type, component/signal, observed value, source.
diagnostic_tests: test ID, incident ID, timestamp, test name, arguments, result, status.
repairs: repair ID, incident ID, timestamp, action, technician note, verified outcome.
Preserve event order and provenance. Use current readings as primary evidence for the current incident; past incidents are context, not a substitute for verification.
Manuals and RAG
Start with a few short, locally stored documents:
Palletizer sequence/interlock description
Sensor and gripper troubleshooting procedure
Alarm code reference
Maintenance and restart safety procedure
A few synthetic historical incident records
Use simple local keyword retrieval initially. Add OpenAI File Search or another RAG layer if document retrieval quality warrants it. Cite document names/sections in the report where possible.
Simulated fault scenarios
Implement at least these three:
Missing gripper-close feedback: close command is active but feedback stays off; sequence waits and times out.
Missing case: conveyor/case-present sensor indicates no case where one is expected.
Blocked sequence interlock: a required condition is false, preventing the next step.
Each scenario should define hidden ground truth, initial state, observable evidence, expected diagnosis, allowed tests, and prohibited actions. The agent should not see the hidden answer directly.
8. Diagnostic tools and interfaces
For the MVP, expose tools through OpenAI function calling with strict JSON schemas. Each tool should have a narrow purpose and typed output.
Tool
Purpose
Example output
get_machine_snapshot
Read current simulated signals and sequence state
Signal names, values, timestamps
get_alarm_history
Read active/recent alarms
Alarm codes, messages, timestamps
trace_sequence_conditions
Explain which known interlocks are satisfied or blocking
Condition, observed value, expected value
run_diagnostic_test
Execute an allowlisted software diagnostic
Test ID, observations, status
search_manuals
Retrieve relevant procedure sections
Document, section, excerpt
search_past_incidents
Find related incidents and outcomes
Incident IDs, similarity reasons, timeline
write_diagnostic_report
Write a structured report
File path, report ID, write status
verify_diagnostic_report
Re-read report and compare it with evidence
Verified flag, mismatches
Use strict validation, timeouts, structured errors, and a tool allowlist. Do not expose unrestricted shell execution or arbitrary PLC writes. In the simulator, tests may change simulated state only when explicitly allowed by the scenario.
9. Local technology stack
Keep the initial stack small and Python-first.
Area
First choice
Why
Backend
Python 3.12+, FastAPI
Agent loop, tool endpoints, simulator, reports
Voice
OpenAI Realtime API
Live audio and conversational interaction
Reasoning/tool calls
OpenAI Responses API with function calling
Multi-step investigation with auditable tools
Validation
Pydantic and JSON Schema
Validate tool inputs and structured outputs
Temporal storage
SQLite
Local timestamped incidents and events
Document retrieval
Local files + keyword search
Simple initial RAG substitute
Dashboard
Streamlit
Quick live operational dashboard
Testing
Pytest + adapted voice evaluation harness
Repeatable scenarios and regression checks
Optional tool protocol
MCP
Add when tools must be reused across clients
Optional packaging
Docker
Reproducible local setup, if useful
Suggested repository layout
fixpilot/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── agent/
│   │   ├── orchestrator.py
│   │   ├── prompts.py
│   │   └── schemas.py
│   ├── voice/
│   │   └── session.py
│   ├── diagnostics/
│   │   ├── hypotheses.py
│   │   ├── rules.py
│   │   └── test_selector.py
│   ├── tools/
│   │   ├── machine.py
│   │   ├── tests.py
│   │   ├── manuals.py
│   │   └── reports.py
│   ├── simulator/
│   │   ├── palletizer.py
│   │   └── scenarios.py
│   └── storage/
│       └── history.py
├── dashboard/
│   └── ui.py
├── knowledge/
│   ├── manuals/
│   └── procedures/
├── evals/
│   ├── scenarios.json
│   ├── graders.py
│   └── test_agent.py
├── reports/
├── tests/
├── .env.example
├── .gitignore
└── requirements.txt
Initial install
Create and activate a virtual environment, then install core packages:
python -m venv .venv

# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install openai fastapi "uvicorn[standard]" pydantic python-dotenv streamlit pytest httpx
Create a .env file for the OpenAI API key and model IDs available to your account. Do not commit secrets.
Useful official resources:
Realtime API: https://developers.openai.com/api/docs/guides/realtime
Function calling: https://developers.openai.com/api/docs/guides/function-calling
Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
Voice-agent evaluation Cookbook: https://developers.openai.com/cookbook/examples/audio/voice_agent_evaluation
Evaluation example repository: https://github.com/openai/openai-cookbook/tree/main/examples/audio/duplex_voice_agent_evaluation
Check current documentation and the checked-out evaluation example for supported API interfaces before wiring them together.
10. Build order
Simulator first: make the three fault scenarios deterministic and testable.
Diagnostic tools: implement signal/alarm reads, sequence tracing, safe tests, manual search, history search, and report verification.
Reasoning loop: implement the bounded investigate–test–observe–update loop with structured state.
Temporal memory: persist events and incident outcomes in SQLite.
Dashboard: render the same conversation, evidence, tool results, decisions, and report used by the backend.
Voice integration: connect GPT-Live/Realtime to the backend and support interruptions and follow-ups.
Evaluation suite: run CRAWL first, then WALK and RUN where applicable; compare baseline and improved versions on identical scenarios.
Demo polish: show a complete incident from the operator's first request through verified report and spoken recommendation.
11. What makes the demo credible
The agent must do real work in software: call diagnostic tools, inspect their returned results, revise hypotheses, create a report, verify that report, and explain the outcome. The machine itself can be simulated. Clearly label simulated machine data and do not imply that a physical robot was repaired or restarted.
The important comparison is not “which model sounds smarter?” It is whether the improved system reaches the correct, evidence-supported diagnosis with fewer unnecessary tests while preserving safety. Report actual measurements from evaluation runs.
12. Hackathon pitch
FixPilot — A voice-first autonomous troubleshooting agent for industrial machines
Industrial failures are often easy to observe but difficult to diagnose. Engineers must correlate alarms, controller states, manuals, and historical incidents before deciding what to inspect.
FixPilot turns troubleshooting into a voice-driven autonomous investigation. It gathers machine evidence, reasons over fault hypotheses and time-ordered incident history, selects permitted diagnostic tests, observes their results, and verifies its final report.
Its core is a closed-loop diagnostic engine combining model-driven reasoning with explicit machine rules and adaptive test selection. We evaluate it against a baseline using repeatable voice-agent scenarios, measuring diagnostic accuracy, evidence grounding, tool efficiency, report completion, and safety.
FixPilot doesn't just explain an alarm. It investigates why the machine stopped, shows the evidence, and identifies the next safe action.

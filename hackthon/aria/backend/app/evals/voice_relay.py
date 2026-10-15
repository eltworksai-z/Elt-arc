import asyncio
import base64
import contextlib
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

from app.agents.session import AgentSession
from app.core.config import get_settings
from app.core.events import hub
from app.core.llm import get_client
from app.evals.participants import CompletionObserver, SimulatedCaller
from app.voice.live import frontend_session_config

SAMPLE_RATE = 24000
FRAME_MS = 20
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * 2
SILENCE = bytes(FRAME_BYTES)
MAX_CALL_S = 240
ENVELOPE_MS = 200


class _Channel:
    """Paced audio stream from one Live session's output to the other's input."""

    def __init__(self) -> None:
        self.pending = bytearray()
        self.recording = bytearray()

    def push(self, chunk: bytes) -> None:
        self.pending.extend(chunk)

    def next_frame(self) -> bytes:
        if len(self.pending) >= FRAME_BYTES:
            frame = bytes(self.pending[:FRAME_BYTES])
            del self.pending[:FRAME_BYTES]
        elif self.pending:
            frame = bytes(self.pending) + bytes(FRAME_BYTES - len(self.pending))
            self.pending.clear()
        else:
            frame = SILENCE
        self.recording.extend(frame)
        return frame


def _caller_config(caller: SimulatedCaller) -> dict[str, Any]:
    settings = get_settings()
    case = caller.case
    return {
        "model": settings.live_model,
        "instructions": (
            "You are a plant operator calling a maintenance voice assistant named ARIA. Stay in character. "
            "Speak naturally and briefly. Never pretend to be the assistant.\n\n" + caller.brief()
        ),
        "audio": {"format": {"type": "audio/pcm", "rate": SAMPLE_RATE}, "output": {"voice": "cinder"}},
        "delegation": {
            "type": "responses",
            "responses": {
                "model": settings.fast_model,
                "instructions": "You help a simulated operator decide what to say next to stay in character and pursue their goal. You have no tools.",
                "reasoning": {"effort": "low"},
            },
        },
        "input": [
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": f"Start the call now by saying: \"{case['caller']['opening']}\""}],
            }
        ],
    }


def _agent_config() -> dict[str, Any]:
    config = frontend_session_config(store=False, greeting=False)
    config["audio"] = config["audio"] | {"format": {"type": "audio/pcm", "rate": SAMPLE_RATE}}
    return config


def envelope(pcm: bytes) -> list[float]:
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    window = SAMPLE_RATE * ENVELOPE_MS // 1000
    count = len(samples) // window
    if count == 0:
        return []
    blocks = samples[: count * window].reshape(count, window)
    return [round(float(v), 4) for v in np.sqrt((blocks**2).mean(axis=1))]


def write_stereo(path: Path, left: bytes, right: bytes) -> None:
    length = max(len(left), len(right))
    l = np.frombuffer(left.ljust(length, b"\0"), dtype=np.int16)
    r = np.frombuffer(right.ljust(length, b"\0"), dtype=np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(np.column_stack([l, r]).astype(np.int16).tobytes())


async def run_voice_conversation(case: dict[str, Any], session: AgentSession, out_dir: Path) -> dict[str, Any]:
    """RUN tier: an independent GPT-Live caller talks to the GPT-Live ARIA front end; ARIA delegates to the backend agent."""
    client = get_client()
    caller = SimulatedCaller(case)
    observer = CompletionObserver(case)
    caller_to_agent, agent_to_caller = _Channel(), _Channel()
    transcript: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    agent_heard = ""
    start = time.monotonic()
    done = asyncio.Event()
    usage: dict[str, Any] = {}

    def offset_ms() -> int:
        return int((time.monotonic() - start) * 1000)

    def add_line(speaker: str, delta: str) -> None:
        if transcript and transcript[-1]["speaker"] == speaker and offset_ms() - transcript[-1]["end_ms"] < 1500:
            transcript[-1]["text"] += delta
            transcript[-1]["end_ms"] = offset_ms()
        else:
            transcript.append({"speaker": speaker, "text": delta.lstrip(), "start_ms": offset_ms(), "end_ms": offset_ms()})

    async with client.live.connect() as agent_conn, client.live.connect() as caller_conn:
        await agent_conn.session.start(session=_agent_config())
        await caller_conn.session.start(session=_caller_config(caller))
        queue = hub.subscribe(session.id)

        async def pump_agent() -> None:
            nonlocal agent_heard
            async for event in agent_conn:
                kind = event.type
                if kind == "session.output_audio.delta":
                    agent_to_caller.push(base64.b64decode(event.delta))
                elif kind == "session.output_transcript.delta":
                    add_line("assistant", event.delta)
                elif kind == "session.input_transcript.delta":
                    agent_heard += event.delta
                elif kind == "session.delegation.created":
                    request = agent_heard.strip() or "Continue with the operator's latest request."
                    agent_heard = ""
                    timeline.append({"type": "delegation", "offset_ms": offset_ms(), "delegation_id": event.delegation.id, "request": request})
                    hub.publish(session.id, "delegation.created", {"delegation_id": event.delegation.id, "target": "client", "transcript": request, "offset_ms": event.offset_ms})
                    session.submit(request, "voice", event.delegation.id)
                elif kind == "session.usage.updated":
                    usage["frontend_seconds"] = getattr(event.usage, "seconds", None)
                elif kind == "session.closed":
                    usage["frontend_seconds"] = getattr(event.usage, "seconds", usage.get("frontend_seconds"))
                    return

        async def pump_caller() -> None:
            async for event in caller_conn:
                if event.type == "session.output_audio.delta":
                    caller_to_agent.push(base64.b64decode(event.delta))
                elif event.type == "session.output_transcript.delta":
                    add_line("operator", event.delta)
                elif event.type == "session.closed":
                    return

        async def relay_backend_events() -> None:
            while True:
                event = await queue.get()
                data = event["data"]
                delegation_id = data.get("delegation_id")
                if event["type"] == "tool.completed":
                    timeline.append({"type": "tool", "offset_ms": offset_ms(), "name": data["name"], "status": data["status"]})
                    continue
                if event["type"] in {"agent.say", "agent.message", "delegation.ack"} and data.get("text"):
                    await agent_conn.session.commentary.append(content=data["text"], delegation_id=delegation_id)
                elif event["type"] == "agent.context" and data.get("text"):
                    await agent_conn.session.thinking.append(content=data["text"], delegation_id=delegation_id)

        async def ticker() -> None:
            frames = 0
            while not done.is_set():
                await agent_conn.session.input_audio.append(audio=base64.b64encode(caller_to_agent.next_frame()).decode())
                await caller_conn.session.input_audio.append(audio=base64.b64encode(agent_to_caller.next_frame()).decode())
                frames += 1
                delay = start + frames * FRAME_MS / 1000 - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)

        async def watch_completion() -> None:
            checked = 0
            while time.monotonic() - start < MAX_CALL_S:
                await asyncio.sleep(4)
                if len(transcript) == checked or not any(t["speaker"] == "assistant" for t in transcript):
                    continue
                checked = len(transcript)
                if (await observer.check(transcript)).resolved:
                    await session.wait_idle()
                    await asyncio.sleep(6)
                    break
            done.set()

        tasks = [asyncio.create_task(t()) for t in (pump_agent, pump_caller, relay_backend_events, ticker)]
        await watch_completion()
        for conn in (agent_conn, caller_conn):
            with contextlib.suppress(Exception):
                await conn.session.close()
        await asyncio.sleep(2)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        hub.unsubscribe(session.id, queue)

    left, right = bytes(caller_to_agent.recording), bytes(agent_to_caller.recording)
    audio_path = out_dir / f"{case['id']}_{session.mode}.wav"
    write_stereo(audio_path, left, right)
    return {
        "transcript": transcript,
        "voice": {
            "audio_file": audio_path.name,
            "duration_s": round(len(left) / 2 / SAMPLE_RATE, 2),
            "envelope_ms": ENVELOPE_MS,
            "caller_envelope": envelope(left),
            "agent_envelope": envelope(right),
            "timeline": timeline,
            "delegations": sum(1 for t in timeline if t["type"] == "delegation"),
            "frontend_seconds": usage.get("frontend_seconds"),
        },
        "caller_usage": caller.usage,
    }

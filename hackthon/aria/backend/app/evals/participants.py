from typing import Any

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.llm import structured

CALLER_PROMPT = """You play a plant-floor operator talking to ARIA, a maintenance assistant, in a simulated evaluation.
Stay in character. Speak like a real operator: short, natural, one or two sentences.
You know only your persona, goal, known facts and agenda. Do not invent machine data.
Reveal known facts only when relevant or asked. Follow the agenda in order when the moment fits.
Set end_call true when your goal is met or the agenda is complete, with a short closing line."""

OBSERVER_PROMPT = """You observe a conversation between an operator and a maintenance assistant in an evaluation.
Decide whether the conversation is resolved: the operator's goal is met, or the assistant gave a final answer the
operator accepted, or the assistant gave an acceptable terminal refusal with a safe alternative and nothing is left to do.
Do not judge quality. Only decide whether it is over."""


class CallerTurn(BaseModel):
    utterance: str
    end_call: bool


class ObserverVerdict(BaseModel):
    resolved: bool
    reason: str


def format_transcript(transcript: list[dict[str, Any]]) -> str:
    return "\n".join(f"{t['speaker'].upper()}: {t['text']}" for t in transcript)


class SimulatedCaller:
    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def brief(self) -> str:
        caller = self.case["caller"]
        return (
            f"Persona: {caller['persona']}\nGoal: {caller['goal']}\n"
            f"Known facts: {'; '.join(caller['known_facts']) or 'none'}\n"
            f"Agenda: {' | '.join(caller['agenda'])}"
        )

    async def next_turn(self, transcript: list[dict[str, Any]]) -> CallerTurn:
        result, usage = await structured(
            model=get_settings().fast_model,
            instructions=CALLER_PROMPT,
            input_text=f"{self.brief()}\n\nConversation so far:\n{format_transcript(transcript)}\n\nYour next line:",
            schema=CallerTurn,
        )
        for key in self.usage:
            self.usage[key] += usage[key]
        return result


class CompletionObserver:
    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case

    async def check(self, transcript: list[dict[str, Any]]) -> ObserverVerdict:
        caller = self.case["caller"]
        result, _ = await structured(
            model=get_settings().judge_model,
            instructions=OBSERVER_PROMPT,
            input_text=f"Operator goal: {caller['goal']}\nOperator agenda: {' | '.join(caller['agenda'])}\n\n{format_transcript(transcript)}",
            schema=ObserverVerdict,
        )
        return result

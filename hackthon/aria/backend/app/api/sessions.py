from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.agents.session import AgentSession, sessions
from app.api.streaming import sse_response
from app.core import db
from app.core.events import hub
from app.core.llm import MissingApiKeyError
from app.voice import live

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSession(BaseModel):
    scenario_id: str | None = None
    mode: Literal["improved", "baseline"] = "improved"


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    source: Literal["text", "voice"] = "text"


class DelegationIn(BaseModel):
    delegation_id: str
    transcript: str
    offset_ms: int | None = None


class VoiceEventIn(BaseModel):
    type: str
    data: dict[str, Any] = {}


class LiveOffer(BaseModel):
    sdp: str


def _live(session_id: str) -> AgentSession:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(409, "Session is not active in this backend process. Start a new session.")
    return session


@router.post("")
async def create_session(body: CreateSession) -> dict[str, Any]:
    try:
        session = sessions.create(body.scenario_id, body.mode)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return session.state()


@router.get("")
def list_sessions(kind: str | None = None) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT * FROM sessions WHERE (? IS NULL OR kind = ?) ORDER BY updated_at DESC LIMIT 100",
        (kind, kind),
    )
    return [row | {"active": sessions.get(row["id"]) is not None} for row in rows]


@router.get("/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if row is None:
        raise HTTPException(404, "Unknown session")
    session = sessions.get(session_id)
    return {"meta": row | {"active": session is not None}, "state": session.state() if session else None}


@router.get("/{session_id}/events")
def stream_events(session_id: str, request: Request, after: int = 0):
    return sse_response(session_id, request, after)


@router.post("/{session_id}/messages")
async def post_message(session_id: str, body: MessageIn) -> dict[str, Any]:
    return _live(session_id).submit(body.text, body.source)


@router.post("/{session_id}/delegations")
async def post_delegation(session_id: str, body: DelegationIn) -> dict[str, Any]:
    session = _live(session_id)
    hub.publish(
        session_id,
        "delegation.created",
        {"delegation_id": body.delegation_id, "target": "client", "transcript": body.transcript, "offset_ms": body.offset_ms},
    )
    request = body.transcript.strip() or "The operator asked for help; continue with their latest request."
    return session.submit(request, "voice", body.delegation_id)


@router.post("/{session_id}/voice-events")
async def post_voice_events(session_id: str, events: list[VoiceEventIn]) -> dict[str, int]:
    _live(session_id)
    for event in events:
        hub.publish(session_id, f"voice.{event.type}", event.data)
    return {"accepted": len(events)}


@router.post("/{session_id}/live")
async def start_live(session_id: str, body: LiveOffer) -> dict[str, Any]:
    session = _live(session_id)
    try:
        answer = await live.create_webrtc_session(body.sdp)
    except MissingApiKeyError as exc:
        raise HTTPException(400, str(exc)) from exc
    hub.publish(session_id, "voice.session", {"live_session_id": answer["live_session_id"], "status": "created"})
    return answer


@router.get("/{session_id}/live/{live_session_id}/recording")
async def live_recording(session_id: str, live_session_id: str) -> Response:
    _live(session_id)
    audio = await live.download_recording(live_session_id)
    return Response(audio, media_type="audio/wav")

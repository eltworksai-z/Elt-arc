from typing import Any

from app.agents.prompts import LIVE_FRONTEND_INSTRUCTIONS
from app.core.config import get_settings
from app.core.llm import get_client
from app.simulator import catalog


def frontend_session_config(*, store: bool = True, greeting: bool = True) -> dict[str, Any]:
    settings = get_settings()
    machine = catalog.machine_info()
    initial: list[dict[str, Any]] = [
        {
            "type": "message",
            "role": "developer",
            "content": [{"type": "input_text", "text": f"Line context: {machine['site']}, cell {machine['id']} — {machine['name']} (simulated)."}],
        },
    ]
    if greeting:
        initial.append(
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "Start the call: greet the worker in one short sentence as ARIA and ask what they need, then listen."}],
            }
        )
    return {
        "model": settings.live_model,
        "instructions": LIVE_FRONTEND_INSTRUCTIONS,
        "audio": {"output": {"voice": settings.live_voice}},
        "delegation": {"type": "client"},
        "input": initial,
        "store": store,
    }


async def create_webrtc_session(offer_sdp: str) -> dict[str, Any]:
    response = await get_client().live.create(
        session=frontend_session_config(),
        transport={"type": "webrtc", "sdp": offer_sdp},
    )
    return {"live_session_id": response.session.id, "sdp": response.transport.sdp}


async def download_recording(live_session_id: str) -> bytes:
    response = await get_client().live.sessions.download_recording(live_session_id)
    return response.content

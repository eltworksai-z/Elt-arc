import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.core.events import hub

KEEPALIVE_S = 15


def sse_response(channel: str, request: Request, after: int = 0) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        queue = hub.subscribe(channel)
        try:
            last = after
            for event in hub.history(channel, after):
                last = event["seq"]
                yield f"id: {event['seq']}\ndata: {json.dumps(event, default=str)}\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), KEEPALIVE_S)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event["seq"] <= last:
                    continue
                last = event["seq"]
                yield f"id: {event['seq']}\ndata: {json.dumps(event, default=str)}\n\n"
        finally:
            hub.unsubscribe(channel, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )

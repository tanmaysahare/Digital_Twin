"""The live update socket. T-082, API_SPEC.md Section 9.

The contract is small and the two parts of it that matter are both about not
lying to a client.

**Sequence numbers.** Every message carries a monotonic `seq`. A client that
sees a gap re-fetches the whole state rather than applying a partial update on
top of a state it may no longer hold (EC-52). Getting this wrong produces a
screen that is subtly wrong and says nothing about it, which is the failure mode
this product exists to avoid.

**Heartbeats.** A heartbeat every `HEARTBEAT_S` seconds. A client that misses two
shows its data age prominently rather than reconnecting silently, because a
supervisor reading a stale screen needs to know it is stale far more than they
need it to quietly recover.

The socket pushes on the twin's own cadence: it sends when the forecast cycle
count moves or the state timestamp moves, and heartbeats in between. It never
pushes a shadow prediction, because it builds its payloads from the same
serialisers the routes use and the filter is in there.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from twin.api import routes
from twin.api.context import Context, get_context
from twin.api.schemas import SocketMessageOut

socket_router = APIRouter()

# How often a heartbeat goes out when nothing has changed.
HEARTBEAT_S = 15.0

# How often the loop looks for a change. Short against the replay's 60x clock,
# long enough that the poll is not the process's main cost.
POLL_S = 1.0


async def _send(socket: WebSocket, message: SocketMessageOut) -> None:
    """One envelope, serialised the way every response is."""
    await socket.send_text(message.model_dump_json(by_alias=True))


@socket_router.websocket("/ws/lines/{line_id}")
async def line_socket(socket: WebSocket, line_id: str) -> None:
    """Push state, actions, risk, health and notices as the twin moves."""
    await socket.accept()
    context: Context = get_context()
    if line_id != context.line.line_id:
        await socket.close(code=4404, reason="no such line")
        return
    seq = 0
    last_at: datetime | None = None
    last_cycles = -1
    last_beat = 0.0
    loop = asyncio.get_event_loop()
    try:
        while True:
            now = loop.time()
            status = context.twin.status()
            moved = status.at != last_at or status.cycles != last_cycles
            if moved and status.ready:
                last_at = status.at
                last_cycles = status.cycles
                for message in _messages(context, seq):
                    seq += 1
                    await _send(socket, message.model_copy(update={"seq": seq}))
                last_beat = now
            elif now - last_beat >= HEARTBEAT_S:
                seq += 1
                await _send(
                    socket,
                    SocketMessageOut(
                        type="HEARTBEAT",
                        as_of=status.at or context.twin.calendar.epoch,
                        seq=seq,
                        payload={"behind_s": round(status.behind_s, 1)},
                    ),
                )
                last_beat = now
            await asyncio.sleep(POLL_S)
    except WebSocketDisconnect:
        return


def _messages(context: Context, seq: int) -> list[SocketMessageOut]:
    """One round of pushes, built from the same serialisers the routes use."""
    line_id = context.line.line_id
    found: list[SocketMessageOut] = []
    state = routes.line_state(context, line_id)
    found.append(
        SocketMessageOut(
            type="STATE",
            as_of=state.as_of,
            seq=seq,
            payload=state.model_dump(mode="json", by_alias=True),
        )
    )
    try:
        actions = routes.actions(context, line_id)
    except Exception:  # noqa: BLE001 - a cold start is not an error to a client
        return found
    found.append(
        SocketMessageOut(
            type="ACTIONS",
            as_of=actions.as_of,
            seq=seq,
            payload=actions.model_dump(mode="json", by_alias=True),
        )
    )
    risk = routes.units_at_risk(context, line_id)
    found.append(
        SocketMessageOut(
            type="UNITS_AT_RISK",
            as_of=risk.as_of,
            seq=seq,
            payload=risk.model_dump(mode="json", by_alias=True),
        )
    )
    notices = routes.notices(context, line_id)
    if notices:
        found.append(
            SocketMessageOut(
                type="NOTICE",
                as_of=state.as_of,
                seq=seq,
                payload={"notices": [item.model_dump(mode="json") for item in notices]},
            )
        )
    return found

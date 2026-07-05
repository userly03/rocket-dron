"""WebSocket para transmisión de datos en tiempo real."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Gestiona conexiones WebSocket activas."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, data: dict[str, Any]) -> None:
        message = json.dumps(data, ensure_ascii=False)
        async with self._lock:
            conexiones = list(self.active_connections)

        desconectados: list[WebSocket] = []
        for connection in conexiones:
            try:
                await connection.send_text(message)
            except Exception:
                desconectados.append(connection)

        for connection in desconectados:
            await self.disconnect(connection)

    async def send_personal(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(data, ensure_ascii=False))


manager = ConnectionManager()


def attach_simulation_listener(simulation, loop: asyncio.AbstractEventLoop) -> None:
    """Registra un listener que retransmite snapshots por WebSocket."""

    def on_update(payload: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(manager.broadcast(payload), loop)

    simulation.add_listener(on_update)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Transmite actualizaciones de la simulación en tiempo real."""
    from src.main import simulation

    await manager.connect(websocket)

    if simulation is not None:
        await manager.send_personal(websocket, simulation.get_status())

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await manager.send_personal(websocket, {"type": "pong"})
            elif data == "status" and simulation is not None:
                await manager.send_personal(websocket, simulation.get_status())
    except WebSocketDisconnect:
        await manager.disconnect(websocket)

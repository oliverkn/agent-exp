from typing import Dict, Set
from fastapi import WebSocket
import logging
import json

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Store websocket connections per thread
        self.thread_connections: Dict[int, Set[WebSocket]] = {}
        logger.info("ConnectionManager initialized")

    async def connect(self, websocket: WebSocket, thread_id: int):
        await websocket.accept()
        if thread_id not in self.thread_connections:
            self.thread_connections[thread_id] = set()
        self.thread_connections[thread_id].add(websocket)
        logger.info(f"Client connected to thread {thread_id}. Active connections: {len(self.thread_connections[thread_id])}")

    async def disconnect(self, websocket: WebSocket, thread_id: int):
        if thread_id in self.thread_connections:
            self.thread_connections[thread_id].discard(websocket)
            if not self.thread_connections[thread_id]:
                del self.thread_connections[thread_id]
            logger.info(f"Client disconnected from thread {thread_id}. Remaining connections: {len(self.thread_connections.get(thread_id, set()))}")

    async def broadcast_to_thread(self, thread_id: int, message: dict):
        if thread_id in self.thread_connections:
            logger.info(f"Broadcasting to thread {thread_id}. Active connections: {len(self.thread_connections[thread_id])}")
            disconnected_ws = set()
            for websocket in self.thread_connections[thread_id]:
                try:
                    await websocket.send_json(message)
                    logger.info(f"Successfully sent message to a client in thread {thread_id}")
                except Exception as e:
                    logger.error(f"Failed to send message to client in thread {thread_id}: {str(e)}")
                    disconnected_ws.add(websocket)
            
            # Clean up disconnected websockets
            for ws in disconnected_ws:
                await self.disconnect(ws, thread_id)
        else:
            logger.warning(f"No active connections for thread {thread_id}")

# Create a single instance to be used across the application
manager = ConnectionManager() 
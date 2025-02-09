from typing import Dict, List
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Store connections per chat room: Dict[chat_id, List[WebSocket]]
        self.active_connections: Dict[int, List[WebSocket]] = {}
        logger.info("ConnectionManager initialized")

    async def connect(self, websocket: WebSocket, thread_id: int):
        await websocket.accept()
        if thread_id not in self.active_connections:
            self.active_connections[thread_id] = []
        self.active_connections[thread_id].append(websocket)
        logger.info(f"Client connected to thread {thread_id}. Active connections: {len(self.active_connections[thread_id])}")

    def disconnect(self, websocket: WebSocket, thread_id: int):
        if thread_id in self.active_connections:
            self.active_connections[thread_id].remove(websocket)
            if not self.active_connections[thread_id]:
                del self.active_connections[thread_id]
            logger.info(f"Client disconnected from thread {thread_id}. Remaining connections: {len(self.active_connections.get(thread_id, []))}")

    async def broadcast_to_thread(self, message: dict, thread_id: int):
        if thread_id in self.active_connections:
            for connection in self.active_connections[thread_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to client: {str(e)}")
                    await self.disconnect(connection, thread_id)

# Create a single instance to be used across the application
manager = ConnectionManager() 
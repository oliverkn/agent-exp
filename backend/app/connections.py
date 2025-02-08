from typing import Dict, List
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Store connections per chat room: Dict[chat_id, List[WebSocket]]
        self.active_connections: Dict[int, List[WebSocket]] = {}
        logger.info("ConnectionManager initialized")

    async def connect(self, websocket: WebSocket, chat_id: int):
        try:
            await websocket.accept()
            if chat_id not in self.active_connections:
                self.active_connections[chat_id] = []
            self.active_connections[chat_id].append(websocket)
            logger.info(f"New WebSocket connection accepted for chat {chat_id}. Total connections for this chat: {len(self.active_connections[chat_id])}")
        except Exception as e:
            logger.error(f"Error accepting WebSocket connection for chat {chat_id}: {str(e)}")
            try:
                await websocket.close(code=4000, reason=str(e))
            except:
                pass  # Connection might already be closed
            raise

    def disconnect(self, websocket: WebSocket, chat_id: int):
        try:
            if chat_id in self.active_connections:
                try:
                    self.active_connections[chat_id].remove(websocket)
                except ValueError:
                    pass  # WebSocket was already removed
                
                if not self.active_connections[chat_id]:
                    del self.active_connections[chat_id]
                logger.info(f"WebSocket disconnected from chat {chat_id}. Remaining connections for this chat: {len(self.active_connections.get(chat_id, []))}")
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket from chat {chat_id}: {str(e)}")

    async def broadcast_to_chat(self, message: dict, chat_id: int):
        if chat_id not in self.active_connections:
            logger.warning(f"No active connections found for chat {chat_id}")
            return
            
        logger.info(f"Broadcasting message to {len(self.active_connections[chat_id])} connections in chat {chat_id}")
        dead_connections = []
        
        for connection in self.active_connections[chat_id]:
            try:
                await connection.send_json(message)
                logger.info(f"Message sent successfully to a connection in chat {chat_id}")
            except Exception as e:
                logger.error(f"Error sending message to a connection in chat {chat_id}: {str(e)}")
                dead_connections.append(connection)
        
        # Clean up dead connections
        for dead_connection in dead_connections:
            try:
                self.disconnect(dead_connection, chat_id)
            except:
                pass

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
            logger.info("Personal message sent successfully")
        except Exception as e:
            logger.error(f"Error sending personal message: {str(e)}")
            raise

# Create a single instance to be used across the application
manager = ConnectionManager() 
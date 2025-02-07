from sqlalchemy.orm import Session
from . import models, database
from .connections import manager
import logging
import asyncio
from typing import Optional

from .tools import *
from .agent import *

logger = logging.getLogger(__name__)

class Chat:
    def __init__(self, id: int, db: Session = None):
        self.id = id
        self._db = db or next(database.get_db())
        logger.info(f"Chat instance created for chat {id}")
        
        # Initialize tools and agent
        self.tool_box = ToolBox()
        self.tool_box.add_tool(UserInput(self))
        self.tool_box.add_tool(SetupMSGraph())
        self.tool_box.add_tool(AuthenticateMSGraph())
        self.tool_box.add_tool(GetLatestEmail())
        
        self.agent = Agent(self.tool_box, "gpt-4o-mini")
        
        # For handling user input
        self._waiting_for_input = False
        self._user_input_future: Optional[asyncio.Future] = None
        
        # Start agent in background task
        asyncio.create_task(self.run_agent())
    
    async def run_agent(self):
        try:
            async for msg in self.agent.run():
                await self.post_new_message(content=msg, is_user=False)
        except Exception as e:
            logger.error(f"Error running agent: {e}")
            logger.error(f"Stack trace:", exc_info=True)
    
    async def wait_for_user_input(self) -> str:
        """Wait for the next user message"""
        if self._waiting_for_input:
            raise Exception("Already waiting for user input")
            
        self._waiting_for_input = True
        self._user_input_future = asyncio.Future()
        
        try:
            return await self._user_input_future
        finally:
            self._waiting_for_input = False
            self._user_input_future = None
    
    async def handle_user_message(self, content: str):
        """Handle an incoming user message"""
        # If we're waiting for input, fulfill the future
        if self._waiting_for_input and self._user_input_future and not self._user_input_future.done():
            self._user_input_future.set_result(content)
        
        # Always store and broadcast the message
        await self.post_new_message(content=content, is_user=True)
    
    async def post_new_message(self, content: str, is_user: bool = True):
        try:
            logger.info(f"Posting new message in chat {self.id}: {content} (is_user: {is_user})")
            
            # Create and store the message in the database
            db_message = models.Message(
                content=content,
                chat_id=self.id,
                sender="user" if is_user else "system"
            )
            self._db.add(db_message)
            self._db.commit()
            self._db.refresh(db_message)
            logger.info(f"Message saved to database with id {db_message.id}")
            
            # Broadcast the message to all connected clients
            message_data = {
                "id": db_message.id,
                "content": db_message.content,
                "chat_id": db_message.chat_id,
                "created_at": str(db_message.created_at),
                "is_user": is_user,
                "sender": db_message.sender
            }
            logger.info(f"Broadcasting message to chat {self.id}")
            await manager.broadcast_to_chat(message_data, self.id)
            logger.info(f"Message broadcast complete")
            
            return db_message
        except Exception as e:
            logger.error(f"Error posting message to chat {self.id}: {str(e)}")
            raise
        
        
        
        
        
        
        
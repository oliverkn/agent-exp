from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Callable
import asyncio
import json
import logging
from ..database import get_db
from ..models import Thread, ThreadMessage, Message
from ..schemas import Thread as ThreadSchema
from ..schemas import ThreadMessage as ThreadMessageSchema
from ..schemas import ThreadCreate, MessageCreate
from ..connections import manager
from ..tools import ToolBox, to_function_schema, UserInputCMD
from openai import OpenAI
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

class Agent:
    def __init__(self, thread: Thread, db: Session):
        self.thread = thread
        self.db = db
        self.toolbox = ToolBox()
        self.running = False
        self.interrupt_message: Optional[str] = None
        logger.info(f"Agent initialized for thread {thread.id}")

    async def start(self):
        try:
            self.running = True
            # Update thread state in database
            self.thread.is_running = True
            self.db.commit()
            logger.info(f"Starting agent for thread {self.thread.id}")
            
            # Add initial message if thread is empty
            if not self.db.query(ThreadMessage).filter(ThreadMessage.thread_id == self.thread.id).count():
                await self._add_message("Hello! I'm your AI assistant. How can I help you today?", "assistant")
            
            while self.running:
                if self.interrupt_message:
                    user_message = self.interrupt_message
                    self.interrupt_message = None
                    await self._add_message(user_message, "user")
                
                # Process messages and generate response
                response = await self._process_messages()
                if response:
                    await self._add_message(response, "assistant")
                
                await asyncio.sleep(0.1)  # Small delay to prevent CPU overuse
                
        except Exception as e:
            logger.error(f"Error in agent loop: {str(e)}")
            self.running = False
            # Update thread state in database on error
            self.thread.is_running = False
            self.db.commit()
            raise

    def stop(self):
        logger.info(f"Stopping agent for thread {self.thread.id}")
        self.running = False
        # Update thread state in database
        self.thread.is_running = False
        self.db.commit()

    async def _add_message(self, content: str, role: str):
        try:
            # Get next sequence number
            sequence_number = self.db.query(ThreadMessage).filter(
                ThreadMessage.thread_id == self.thread.id
            ).count() + 1
            
            # Create message in database
            message = ThreadMessage(
                content=content,
                thread_id=self.thread.id,
                sender=role,
                sequence_number=sequence_number
            )
            self.db.add(message)
            self.db.commit()
            self.db.refresh(message)
            
            # Prepare WebSocket message
            ws_message = {
                "id": message.id,
                "thread_id": message.thread_id,
                "role": message.sender,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
                "type": "message",
                "sequence_number": message.sequence_number
            }
            
            # Broadcast message to all connections in this thread
            try:
                await manager.broadcast_to_chat(ws_message, self.thread.id)
                logger.info(f"Message broadcasted to thread {self.thread.id}")
            except Exception as e:
                logger.error(f"Error broadcasting message: {str(e)}")
            
            return message
            
        except Exception as e:
            logger.error(f"Error adding message: {str(e)}")
            raise

    async def _process_messages(self):
        # Your existing message processing logic here
        pass

    def interrupt(self, message: str):
        logger.info(f"Interrupt received for thread {self.thread.id}: {message}")
        self.interrupt_message = message

agents: Dict[int, Agent] = {}

@router.post("/threads/", response_model=ThreadSchema)
async def create_thread(thread: ThreadCreate, db: Session = Depends(get_db)):
    try:
        # Create thread with is_running set to False initially
        db_thread = Thread(**thread.dict(), is_running=False)
        db.add(db_thread)
        db.commit()
        db.refresh(db_thread)
        logger.info(f"Created new thread with ID {db_thread.id}")
        return db_thread
    except Exception as e:
        logger.error(f"Error creating thread: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/threads/", response_model=List[ThreadSchema])
async def get_threads(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    try:
        threads = db.query(Thread).order_by(Thread.created_at.desc()).offset(skip).limit(limit).all()
        logger.info(f"Fetched {len(threads)} threads")
        return threads
    except Exception as e:
        logger.error(f"Error fetching threads: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/threads/{thread_id}", response_model=ThreadSchema)
async def get_thread(thread_id: int, db: Session = Depends(get_db)):
    try:
        thread = db.query(Thread).filter(Thread.id == thread_id).first()
        if thread is None:
            logger.error(f"Thread {thread_id} not found")
            raise HTTPException(status_code=404, detail="Thread not found")
        logger.info(f"Fetched thread {thread_id}")
        return thread
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching thread {thread_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/threads/{thread_id}/messages/", response_model=ThreadMessageSchema)
async def create_message(thread_id: int, message: str, db: Session = Depends(get_db)):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    if thread_id in agents and agents[thread_id].waiting_for_user_input:
        # If agent is waiting for user input, send it as response
        agents[thread_id].add_user_interrupt(message)
    else:
        # Otherwise create a new message and interrupt agent if running
        sequence_number = db.query(ThreadMessage).filter(
            ThreadMessage.thread_id == thread_id
        ).count() + 1
        
        db_message = ThreadMessage(
            content=message,
            thread_id=thread_id,
            sender="user",
            sequence_number=sequence_number
        )
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
        
        if thread_id in agents and agents[thread_id].running:
            agents[thread_id].add_user_interrupt(message)
            
        return db_message

@router.get("/threads/{thread_id}/messages/", response_model=List[ThreadMessageSchema])
async def get_thread_messages(
    thread_id: int, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)
):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    messages = db.query(ThreadMessage).filter(
        ThreadMessage.thread_id == thread_id
    ).order_by(ThreadMessage.sequence_number).offset(skip).limit(limit).all()
    
    return messages

@router.post("/threads/{thread_id}/start")
async def start_agent(thread_id: int, db: Session = Depends(get_db)):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Clean up any existing agent
    if thread_id in agents:
        old_agent = agents[thread_id]
        old_agent.stop()  # This will update the thread state
        del agents[thread_id]
    
    # Create new agent
    agent = Agent(thread, db)
    agents[thread_id] = agent
    logger.info(f"Created new agent for thread {thread_id}")
    
    # Start the agent
    await agent.start()
    logger.info(f"Started agent for thread {thread_id}")
    
    return {"status": "started"}

@router.post("/threads/{thread_id}/stop")
async def stop_agent(thread_id: int, db: Session = Depends(get_db)):
    if thread_id in agents:
        agents[thread_id].stop()
        # Clean up the agent
        del agents[thread_id]
        return {"status": "stopped"}
    
    # If agent not found but thread exists, ensure thread state is correct
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if thread:
        thread.is_running = False
        db.commit()
        return {"status": "stopped"}
        
    raise HTTPException(status_code=404, detail="Agent not found")

@router.websocket("/threads/{thread_id}/ws")
async def websocket_endpoint(
    websocket: WebSocket, thread_id: int, db: Session = Depends(get_db)
):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if thread is None:
        await websocket.close(code=4004, reason="Thread not found")
        return
    
    await manager.connect(websocket, thread_id)
    logger.info(f"WebSocket connected for thread {thread_id}")
    
    try:
        # Set up agent message callback if agent exists
        if thread_id in agents:
            async def on_new_message(message: ThreadMessage):
                try:
                    message_dict = {
                        "id": message.id,
                        "content": message.content,
                        "thread_id": message.thread_id,
                        "sender": message.sender,
                        "sequence_number": message.sequence_number,
                        "created_at": message.created_at.isoformat(),
                        "is_tool_call": message.is_tool_call,
                        "tool_name": message.tool_name,
                        "tool_args": message.tool_args,
                        "tool_result": message.tool_result
                    }
                    await manager.send_personal_message(message_dict, websocket)
                    logger.info(f"Sent message to websocket for thread {thread_id}: {message.content[:100]}...")
                except Exception as e:
                    logger.error(f"Error sending message to websocket: {str(e)}")
            
            agents[thread_id].on_new_message = on_new_message
            logger.info(f"Set up message callback for thread {thread_id}")
        
        while True:
            try:
                # Wait for messages from the client
                data = await websocket.receive_json()
                logger.info(f"Received message from client for thread {thread_id}: {data}")
                
                if "content" in data:
                    # Create new message
                    await create_message(thread_id, data["content"], db)
                    
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for thread {thread_id}")
                manager.disconnect(websocket, thread_id)
                break
                
    except Exception as e:
        logger.error(f"Error in websocket endpoint: {str(e)}")
        await websocket.close(code=4000, reason=str(e))
        manager.disconnect(websocket, thread_id)

    
    

from fastapi import APIRouter, Depends, HTTPException, WebSocket, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import logging
import asyncio
import json
import os

from ..database import get_db
from ..models import Thread, Message
from ..schemas import ThreadCreate, Thread as ThreadSchema
from ..tools import *
from ..connections import manager
from .agent_new import Agent, Event, EventTypes

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

agents = {}

@router.post("/api/threads/create", response_model=ThreadSchema)
async def create_thread(thread: ThreadCreate, db: Session = Depends(get_db)):
    try:
        logger.info(f"Creating new thread with title: {thread.title}")
        db_thread = Thread(title=thread.title)
        db.add(db_thread)
        db.commit()
        db.refresh(db_thread)
        logger.info(f"Successfully created thread with ID: {db_thread.id}")
        
        agents[db_thread.id] = Agent(db_thread.id)
        
        return db_thread
    except Exception as e:
        logger.error(f"Error creating thread: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/threads/list", response_model=List[ThreadSchema])
async def list_threads(db: Session = Depends(get_db)):
    try:
        logger.info("Fetching thread list")
        threads = db.query(Thread).order_by(Thread.created_at.desc()).all()
        logger.info(f"Successfully fetched {len(threads)} threads")
        return threads
    except Exception as e:
        logger.error(f"Error fetching threads: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/threads/{thread_id}/get_thread_messages")
async def get_thread_messages(thread_id: int, db: Session = Depends(get_db)):
    try:
        logger.info(f"Fetching messages for thread ID: {thread_id}")
        thread = db.query(Thread).filter(Thread.id == thread_id).first()
        
        if not thread:
            logger.error(f"Thread with ID {thread_id} not found")
            raise HTTPException(status_code=404, detail="Thread not found")
            
        messages = thread.messages
        logger.info(f"Successfully fetched {len(messages)} messages for thread {thread_id}")
        return messages
    except Exception as e:
        logger.error(f"Error fetching messages for thread {thread_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/api/threads/{thread_id}/get_thread_message/{message_id}")
async def get_thread_message(thread_id: int, message_id: int, db: Session = Depends(get_db)):
    try:
        logger.info(f"Fetching message with ID: {message_id} for thread ID: {thread_id}")
        message = db.query(Message).filter(Message.id == message_id, Message.thread_id == thread_id).first()
        
        if not message:
            logger.error(f"Message with ID {message_id} not found for thread {thread_id}")
            raise HTTPException(status_code=404, detail="Message not found")
            
        logger.info(f"Successfully fetched message with ID: {message_id} for thread {thread_id}")
        return message
    except Exception as e:
        logger.error(f"Error fetching message with ID {message_id} for thread {thread_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: int):
    try:
        logger.info(f"WebSocket connection attempt for thread {thread_id}")
        await manager.connect(websocket, thread_id)
        logger.info(f"WebSocket connected for thread {thread_id}")
        
        try:
            while True:
                try:
                    data = await websocket.receive_text()
                    if data == "ping":
                        await websocket.send_text("pong")
                    logger.debug(f"Received WebSocket data: {data}")
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected for thread {thread_id}")
                    break
        finally:
            logger.info(f"WebSocket connection ending for thread {thread_id}")
            await manager.disconnect(websocket, thread_id)
            logger.info(f"WebSocket disconnected for thread {thread_id}")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {str(e)}", exc_info=True)
        await websocket.close()

@router.post("/api/threads/{thread_id}/message")
async def send_message(
    thread_id: int, 
    message: dict, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    try:
        logger.info(f"Sending message to thread ID: {thread_id}")
        
        if thread_id not in agents:
            agents[thread_id] = Agent(thread_id)
        
        # Handle the event with the agent in background task
        agent = agents[thread_id]
        # background_tasks.add_task(agent.handle_event, Event(type=EventTypes.USER, data=message['content']))
        agent.handle_event(Event(type=EventTypes.USER, data=message['content']))
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error sending message to thread {thread_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

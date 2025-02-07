from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Dict
from . import models, schemas, database
from .chat import Chat
from .connections import manager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FastAPI + React Chat Application")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "FastAPI backend is running!"}

# WebSocket endpoint
@app.websocket("/api/ws/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: int, db: Session = Depends(database.get_db)):
    try:
        logger.info(f"New WebSocket connection request for chat {chat_id}")
        
        # Verify chat exists in database
        db_chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
        if db_chat is None:
            logger.error(f"Chat {chat_id} not found")
            await websocket.close(code=4004, reason="Chat not found")
            return

        # Accept the connection before creating the chat instance
        await manager.connect(websocket, chat_id)
        logger.info(f"WebSocket connected for chat {chat_id}")
        
        # Create chat instance after connection is established
        chat = Chat(chat_id, db)
        
        try:
            while True:
                # Wait for messages from the client
                data = await websocket.receive_json()
                logger.info(f"Received message in chat {chat_id}: {data}")
                
                # Handle the message using our Chat class
                await chat.handle_user_message(data["content"])
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for chat {chat_id}")
            manager.disconnect(websocket, chat_id)
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            await websocket.close(code=4000, reason=str(e))
    except Exception as e:
        logger.error(f"Error in WebSocket for chat {chat_id}: {str(e)}")
        try:
            await websocket.close(code=4000, reason=str(e))
        except:
            pass  # Connection might already be closed

# Chat endpoints
@app.post("/api/chats/", response_model=schemas.Chat)
def create_chat(chat: schemas.ChatCreate, db: Session = Depends(database.get_db)):
    db_chat = models.Chat(**chat.dict())
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    return db_chat

@app.get("/api/chats/", response_model=List[schemas.Chat])
def get_chats(skip: int = 0, limit: int = 10, db: Session = Depends(database.get_db)):
    chats = db.query(models.Chat).offset(skip).limit(limit).all()
    return chats

@app.get("/api/chats/{chat_id}", response_model=schemas.Chat)
def get_chat(chat_id: int, db: Session = Depends(database.get_db)):
    chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat

@app.post("/api/chats/{chat_id}/messages/", response_model=schemas.Message)
def create_message(chat_id: int, message: schemas.MessageCreate, db: Session = Depends(database.get_db)):
    chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    db_message = models.Message(**message.dict(), chat_id=chat_id, sender="user")
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

@app.get("/api/chats/{chat_id}/messages/", response_model=List[schemas.Message])
def get_chat_messages(chat_id: int, skip: int = 0, limit: int = 50, db: Session = Depends(database.get_db)):
    chat = db.query(models.Chat).filter(models.Chat.id == chat_id).first()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    messages = db.query(models.Message).filter(models.Message.chat_id == chat_id).offset(skip).limit(limit).all()
    return messages 
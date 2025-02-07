from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
from . import models, schemas, database

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
    
    db_message = models.Message(**message.dict(), chat_id=chat_id)
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
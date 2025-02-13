from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class MessageBase(BaseModel):
    content: str

class MessageCreate(MessageBase):
    pass

class Message(MessageBase):
    id: int
    chat_id: int
    created_at: datetime
    sender: str

    class Config:
        from_attributes = True

class ChatBase(BaseModel):
    title: Optional[str] = "New Chat"

class ChatCreate(ChatBase):
    pass

class Chat(ChatBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    messages: List[Message] = []

    class Config:
        from_attributes = True

class ThreadBase(BaseModel):
    title: Optional[str] = "New Thread"

class ThreadCreate(BaseModel):
    title: str

class Thread(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    state: str
    toolbox_state: str

    class Config:
        from_attributes = True 
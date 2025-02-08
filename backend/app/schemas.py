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
    toolbox_state: Optional[str] = "{}"  # JSON string for toolbox state

class ThreadCreate(ThreadBase):
    pass

class ThreadMessageBase(BaseModel):
    content: str
    sender: str
    sequence_number: int
    is_tool_call: bool = False
    tool_name: Optional[str] = None
    tool_args: Optional[str] = None
    tool_result: Optional[str] = None

class ThreadMessage(ThreadMessageBase):
    id: int
    thread_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class Thread(ThreadBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_running: bool = False
    messages: List[ThreadMessage] = []

    class Config:
        from_attributes = True 
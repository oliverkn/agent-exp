from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), default="New Chat")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship with messages
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sender = Column(String(50), nullable=False, default="user")

    # Relationship with chat
    chat = relationship("Chat", back_populates="messages") 
    
class Thread(Base):
    __tablename__ = "threads"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), default="New Thread")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    toolbox_state = Column(Text, default="{}")  # JSON string for toolbox state
    is_running = Column(Boolean, default=False)

    # Relationship with messages
    messages = relationship("ThreadMessage", back_populates="thread", cascade="all, delete-orphan")

class ThreadMessage(Base):
    __tablename__ = "thread_messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    thread_id = Column(Integer, ForeignKey("threads.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sender = Column(String(50), nullable=False, default="user")
    sequence_number = Column(Integer, nullable=False)
    is_tool_call = Column(Boolean, default=False)
    tool_name = Column(String(255))
    tool_args = Column(Text)
    tool_result = Column(Text)

    # Relationship with thread
    thread = relationship("Thread", back_populates="messages")

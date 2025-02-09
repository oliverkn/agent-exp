from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Thread(Base):
    __tablename__ = "threads"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), default="New Thread")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship with messages
    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    thread_id = Column(Integer, ForeignKey("threads.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sender = Column(String(50), nullable=False, default="user")

    # Relationship with thread
    thread = relationship("Thread", back_populates="messages")

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
    
    thread_id = Column(Integer, ForeignKey("threads.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    api_message = Column(Text, nullable=False) # message for the API as json
    
    role = Column(String(10), nullable=False) # user, agent, tool
 
    content = Column(Text, nullable=True) # used to display content in the UI
    
    # Tool related
    tool_call_id = Column(String(50), nullable=True)
    tool_name = Column(String(50), nullable=True)
    tool_args = Column(Text, nullable=True)
    # tool_display_data = Column(Text, nullable=True)
    tool_state = Column(String(10), nullable=True) # running, completed, error
    tool_result = Column(Text, nullable=True)
    
    # Relationship with thread
    thread = relationship("Thread", back_populates="messages")

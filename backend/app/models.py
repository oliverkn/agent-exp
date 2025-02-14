from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Thread(Base):
    __tablename__ = "threads"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    state = Column(String, nullable=False, default="READY")  # Add default state
    toolbox_state = Column(Text, nullable=False, default="{}")  # Add default toolbox state

    # Relationship with messages
    messages = relationship("Message", back_populates="thread")
    
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    
    thread_id = Column(Integer, ForeignKey("threads.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    api_messages = Column(Text, nullable=False) # list of message for the API as json
    
    agent_state = Column(String(10), nullable=False) # await_input, await_ai_response, await_tool_response
    role = Column(String(10), nullable=False) # user, agent, tool
    content_type = Column(String(10), nullable=False, default="text") # text, image_url_list
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


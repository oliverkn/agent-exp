from fastapi import APIRouter, Depends, HTTPException, WebSocket
from sqlalchemy.orm import Session
from typing import List
import logging
import asyncio
import json

from ..database import get_db
from ..models import Thread
from ..schemas import ThreadCreate, Thread as ThreadSchema
from ..tools import *
from ..connections import manager
from openai import OpenAI

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
        return db_thread
    except Exception as e:
        logger.error(f"Error creating thread: {str(e)}")
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
        logger.error(f"Error fetching threads: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/threads/{thread_id}/start_agent_loop")
async def start_agent_loop(thread_id: int, db: Session = Depends(get_db)):
    try:
        logger.info(f"Starting agent loop for thread {thread_id}")
        
        thread = db.query(Thread).filter(Thread.id == thread_id).first()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        if thread_id not in agents:
            agent = Agent(thread)
            agents[thread_id] = agent
        else:
            agent = agents[thread_id]
            
        agent.start()
        
        return {"status": "started"}
    except Exception as e:
        logger.error(f"Error starting agent loop: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/threads/{thread_id}/user_input")
async def send_user_input(thread_id: int, user_input: dict, db: Session = Depends(get_db)):
    try:
        logger.info(f"Receiving user input for thread {thread_id}")
        
        thread = db.query(Thread).filter(Thread.id == thread_id).first()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        if thread_id not in agents:
            raise HTTPException(status_code=400, detail="Agent not running for this thread")
            
        agent = agents[thread_id]
        agent.add_user_interrupt(user_input["message"])
        
        return {"status": "message_received"}
    except Exception as e:
        logger.error(f"Error processing user input: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/threads/{thread_id}/get_thread")
async def get_thread(thread_id: int, from_sequence_number: int = 0, db: Session = Depends(get_db)):
    try:
        thread = db.query(Thread).filter(Thread.id == thread_id).first()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        #return messages and running state from agent for this thread
        if thread_id not in agents:
            raise HTTPException(status_code=400, detail="Agent not running for this thread")
        
        agent = agents[thread_id]
        
        return {
            "messages": agent.messages,
            "running": agent.running
        }
    except Exception as e:
        logger.error(f"Error getting thread: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws/threads/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: int, db: Session = Depends(get_db)):
    try:
        thread = db.query(Thread).filter(Thread.id == thread_id).first()
        if not thread:
            await websocket.close(code=4004, reason="Thread not found")
            return

        await manager.connect(websocket, thread_id)
        try:
            async def on_message(data):
                # Handle any incoming WebSocket messages if needed
                logger.info(f"Received WebSocket message for thread {thread_id}: {data}")
                
            websocket.receive_json = on_message
            await websocket.wait_closed()
        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}")
        finally:
            manager.disconnect(websocket, thread_id)
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {str(e)}")
        try:
            await websocket.close(code=4000, reason=str(e))
        except:
            pass

# def get_input_function(thread_id):
#     def input_function(message):
#         # send message to UI via websocket
#         await manager.broadcast_to_thread({
#             "type": "user_input_request",
#             "message": message
#         }, thread_id)
        
#         # wait for send_user_input to be called for this thread
#         # return the user input
#         pass
        
#     return input_function

class Agent:
    on_new_message = None
    on_change = None
    
    def __init__(self, thread: Thread):
        self.thread = thread
    
        self.tool_box = ToolBox()
        # self.tool_box.add_tool(UserInput())
        self.tool_box.add_tool(SetupMSGraph())
        self.tool_box.add_tool(AuthenticateMSGraph())
        self.tool_box.add_tool(GetLatestEmail())
        
        self.model = "gpt-4o-mini"
        self.client = OpenAI(api_key="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")

        self.tools_schema = []
        for tool in self.tool_box.get_tools():
            schema = self.to_function_schema(tool)
            self.tools_schema.append(schema)
            
        self.messages = []
        self.messages.append({"role": "developer", "content": [{"type" : "text", "text" : "Your task is to get the latest email by using the available tools."}]})
    
    def start(self):
        self.running = True
        self.task = asyncio.create_task(self.run())
        
    def stop(self):
        self.running = False
        if hasattr(self, 'task'):
            self.task.cancel()
    
    def add_user_interrupt(self, user_message):
        # stops the loop without waiting for current step to finish
        # add user interrupt message to stack
        # continue loop 
        self.messages.append({"role": "user", "content": user_message})
        self.start()
        
        return
    
    async def run(self):
        while self.running:
            await self.run_step()
    
    async def broadcast_message(self, message: dict):
        await manager.broadcast_to_thread(message, self.thread.id)

    async def run_step(self):
        completion = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.tools_schema,
                tool_choice="auto",
                # parallel_tool_calls=False
            )
            
        response = completion.choices[0].message
        self.messages.append(response)
        
        # Broadcast assistant's message
        # await self.broadcast_message({
        #     "type": "assistant",
        #     "content": response.content if hasattr(response, 'content') else None,
        #     "tool_calls": [
        #         {
        #             "name": tool_call.function.name,
        #             "arguments": tool_call.function.arguments
        #         } for tool_call in response.tool_calls
        #     ] if hasattr(response, 'tool_calls') else []
        # })
        
        if completion.choices[0].finish_reason == "stop":
            self.running = False
            self.on_change(self.running, self.messages)
            return
        
        elif completion.choices[0].finish_reason == "tool_calls":
            for tool_call in completion.choices[0].message.tool_calls:
                name = tool_call.function.name
                args = tool_call.function.arguments

                print(f"{name}({args})")
                result = await self.tool_box.call(name, args)
                print(result)
                
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
                
                # # Broadcast tool result
                # await self.broadcast_message({
                #     "type": "tool_result",
                #     "tool": name,
                #     "result": result
                # })
        else:
            raise Exception("Unknown finish reason: " + response.choices[0].finish_reason)
    
    @staticmethod
    def to_function_schema(tool):    
        return {
        "type": "function",
        "function": {
            "name": tool.tool_name,
            "description": tool.tool_description,
            "parameters": {
                "type": "object",
                "properties": tool.args_model.schema()["properties"]},
                "required": list(tool.args_model.schema()["properties"].keys()),
                "additionalProperties": False
            },
            "strict": True
        }
    
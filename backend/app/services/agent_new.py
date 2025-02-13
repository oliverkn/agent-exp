import logging

# Fix logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)

# Remove duplicate handler setup
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

root_logger.debug("Agent module initialized")

import os
import time
import asyncio
from enum import Enum
from pydantic import BaseModel
import json

from pyee import EventEmitter
from openai import OpenAI

from ..tools import *
from sqlalchemy.orm import Session
from ..models import Message

class AgentState(Enum):
    AWAIT_INPUT = 'await_input'
    AWAIT_AI_RESPONSE = 'await_ai_response'
    AWAIT_TOOL_RESPONSE = 'await_tool_response'

class EventTypes(Enum):
    USER = 'user'
    AI_RESULT = 'ai_result'
    TOOL_RESULT = 'tool_result'
    NOTIFICATION = 'notification'
    INTERRUPT = 'interrupt'
    
class Event(BaseModel):
    type: EventTypes
    data: object

class Agent:
    def __init__(self, thread_id, db: Session):
        self.thread_id = thread_id
        self.db = db
        
        # Simplified logger setup
        self.logger = logging.getLogger(f"Agent-{thread_id}")
        self.logger.info(f"Initializing agent with thread_id: {thread_id}")
        
        self.state = AgentState.AWAIT_INPUT
        
        self.emitter = EventEmitter()
        # self.emitter.on(thread_id, self.handle_event)
        
        self.timeout = 60.0 # seconds
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = "gpt-4o-mini"
        self.notifications = []
        self.current_task = None
        
        self.tool_box = ToolBox(db)
        # self.tool_box.add_tool(UserInput())
        self.tool_box.add_tool(UserInputCMD())
        self.tool_box.add_tool(SetupMSGraph())
        self.tool_box.add_tool(AuthenticateMSGraph())
        self.tool_box.add_tool(GetLatestEmail())
        
        self.tools_schema = []
        for tool in self.tool_box.get_tools():
            schema = self._to_function_schema(tool)
            self.tools_schema.append(schema)
            
        self.messages = []
        self.messages.append({"role": "developer", "content": "Your task is to use the available tools to solve the any given tasks."})
        
        # Load existing messages from database
        # db_messages = self.db.query(Message).filter(Message.thread_id == thread_id).order_by(Message.created_at).all()
        # for msg in db_messages:
        #     self.messages.append({
        #         "role": msg.role,
        #         "content": msg.content,
        #         **({"tool_call_id": msg.tool_call_id} if msg.tool_call_id else {})
        #     })
    
    @staticmethod
    def _to_function_schema(tool):    
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
    
    def _submit_completion(self):
        self.logger.debug("Submitting completion request")
        def run_completion():
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.tools_schema,
                tool_choice="required",
                parallel_tool_calls=False
            )
            self.logger.debug(completion.choices[0].message)
            return completion
        
        self.exec_and_callback(run_completion, EventTypes.AI_RESULT)
    
    def _add_user_message(self, msg):
        self.logger.debug(f"Adding user message: {msg}")
        
        api_message = {"role": "user", "content": msg}
        self.messages.append(api_message)
        
        # Store message in database
        db_message = Message(
            thread_id=self.thread_id,
            api_message=json.dumps(api_message),
            role="user",
            content=msg
        )
        self.db.add(db_message)
        self.db.commit()
        
        self.emitter.emit(self.thread_id, {"status": "update"})
    
    def _add_assistant_message(self, msg):
        self.logger.debug(f"Adding assistant message: {msg}")
        
         # Store message in database
        db_message = Message(
            thread_id=self.thread_id,
            api_message=json.dumps(msg.dict()),
            role=msg.role,
            content=msg.content
        )
        self.db.add(db_message)
        self.db.commit()
        
        self.messages.append(msg)

        self.emitter.emit(self.thread_id, {"status": "update"})
    
    def _add_tool_result_message(self, tool_call_id, tool_name, tool_args):
        api_message = {
            "role": "tool", 
            "tool_call_id": tool_call_id, 
            "content": json.dumps({"error" : "Tool call was cancelled."})
        }
        self.messages.append(api_message)
        
        db_message = Message(
            thread_id=self.thread_id,
            api_message=json.dumps(api_message),
            role="tool",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_args=json.dumps(tool_args),
            tool_state="running"
        )
        self.db.add(db_message)
        self.db.commit()
        self.emitter.emit(self.thread_id, {"status": "update"})
    
    def __update_tool_call_message(self, tool_call_id, tool_call_result):
        db_message = self.db.query(Message).filter(Message.tool_call_id == tool_call_id).first()
        if not db_message:
            raise Exception(f"Tool call message not found for tool_call_id: {tool_call_id}")
        
        # Update existing message
        db_message.tool_result = json.dumps(tool_call_result.result)
        db_message.tool_state = tool_call_result.state.value
        db_message.tool_display_data = tool_call_result.display_data
        
        self.db.commit()
        
        self.emitter.emit(self.thread_id, {"status": "update"})
        
    def __finalize_tool_call_message(self, tool_call_id, tool_call_result):
        api_message = self.messages[-1]
        api_message["content"] = json.dumps(tool_call_result.result)
        
        db_message = self.db.query(Message).filter(Message.tool_call_id == tool_call_id).first()
        if not db_message:
            raise Exception(f"Tool call message not found for tool_call_id: {tool_call_id}")
        
        # Update existing message
        db_message.api_message = json.dumps(api_message)
        db_message.tool_result = json.dumps(tool_call_result.result)
        db_message.tool_state = tool_call_result.state.value
        db_message.tool_display_data = tool_call_result.display_data
        
        self.db.commit()
        
        self.emitter.emit(self.thread_id, {"status": "update"})
    
    def _cancel_current_task(self):
        if self.current_task is not None:
            self.current_task.cancel()
        
    def handle_event(self, event: Event):
        self.logger.debug(f"Handling event: {event.type} in state: {self.state}")
        match self.state:
            case AgentState.AWAIT_INPUT:
                if event.type == EventTypes.USER:
                    self.logger.info("Processing user input")
                    self._add_user_message(event.data)
                    self._submit_completion()
                    self._enter_await_ai_response()
                elif event.type == EventTypes.NOTIFICATION:
                    self.logger.info("Processing notification")
                    self.notifications.append(event.data)
                
                    content = "Here are the latest notifications:"
                    for notification in self.notifications:
                        content += f"\n{notification}"

                    self._add_user_message(event.data)
                    self._submit_completion()
                    self._enter_await_ai_response()
                    
                elif event.type == EventTypes.INTERRUPT:
                    self.logger.info("Processing interrupt")
                    pass
                else:
                    self.logger.error(f"Invalid event type {event.type} for current state {self.state}")
                    raise Exception(f"Invalid event type {event.type} for current state {self.state}")
            
            case AgentState.AWAIT_AI_RESPONSE:
                if event.type == EventTypes.INTERRUPT:
                    self.logger.info("Processing interrupt during AI response")
                    self._cancel_current_task()
                    self._enter_await_input()
                    
                elif event.type == EventTypes.NOTIFICATION:
                    self.logger.debug("Storing notification during AI response")
                    self.notifications.append(event.data)
                    
                elif event.type == EventTypes.AI_RESULT:
                    self.logger.info("Processing AI result")
                    completion = event.data
                    
                    self.logger.debug(f"AI completion: {completion.choices[0].message}")
                    
                    if completion.choices[0].finish_reason == "stop":
                        self.logger.debug("AI completion finished with 'stop'")
                        self._add_assistant_message(completion.choices[0].message)
                        self._enter_await_input()
                        
                    elif completion.choices[0].finish_reason == "tool_calls":
                        self.logger.debug("AI completion finished with 'tool_calls'")
                        self._add_assistant_message(completion.choices[0].message)
                        for tool_call in completion.choices[0].message.tool_calls:
                            name = tool_call.function.name
                            args = tool_call.function.arguments
                            self.logger.info(f"Calling tool: {name}({args})")
                            
                            self._add_tool_result_message(tool_call.id, name, args)
                            
                            def on_update(state: ToolCallResult): 
                                self.__update_tool_call_message(tool_call.id, state)

                            async def tool_execution():
                                return tool_call.id, await self.tool_box.call(name, args, on_update)

                            self.exec_and_callback(tool_execution, EventTypes.TOOL_RESULT)
                            self._enter_await_tool_response()
                    else:
                        self.logger.error(f"Invalid finish reason {completion.choices[0].finish_reason}")
                        raise Exception(f"Invalid finish reason {completion.choices[0].finish_reason}")
                        
                else:
                    self.logger.error(f"Invalid event type {event.type} for current state {self.state}")
                    raise Exception(f"Invalid event type for current state {self.state}")
                    
            case AgentState.AWAIT_TOOL_RESPONSE:
                if event.type == EventTypes.INTERRUPT:
                    self.logger.info("Processing interrupt during tool response")
                    self._cancel_current_task()
                    self._enter_await_input()
                    
                elif event.type == EventTypes.TOOL_RESULT:
                    tool_call_id, tool_call_result = event.data
                    self.logger.info(f"Processing tool result for tool_call_id: {tool_call_id}")
                    self.__finalize_tool_call_message(tool_call_id, tool_call_result)
                    
                    self._submit_completion()
                    self._enter_await_ai_response()
                    
                elif event.type == EventTypes.NOTIFICATION:
                    self.notifications.append(event.data)
                else:
                    self.logger.error(f"Invalid event type for current state {self.state}")
                    raise Exception(f"Invalid event type for current state {self.state}")
        
        return True
                
    
    def exec_and_callback(self, f, event_type: EventTypes):
        self.logger.debug(f"Setting up execution for event type: {event_type}")
        async def wrapper():
            try:
                self.logger.debug("Starting task execution")
                if asyncio.iscoroutinefunction(f):
                    result = await asyncio.wait_for(f(), timeout=self.timeout) 
                else:
                    result = await asyncio.wait_for(asyncio.to_thread(f), timeout=self.timeout) 
                
                event = Event(type=event_type, data=result)
                self.handle_event(event)
            except asyncio.TimeoutError:
                self.logger.error(f"Task timed out after {self.timeout} seconds")
                event = Event(type=event_type, data={"error": f"Task timed out after {self.timeout} seconds"})
                self.handle_event(event)
            except Exception as e:
                self.logger.error(f"Error in task execution: {e}", exc_info=True)
                event = Event(type=event_type, data={"error": str(e)})
                self.handle_event(event)
            
        self.current_task = asyncio.create_task(wrapper())
    
    def _enter_await_input(self):
        self.logger.debug("Entering AWAIT_INPUT state")
        self.state = AgentState.AWAIT_INPUT
        
    def _enter_await_ai_response(self):
        self.logger.debug("Entering AWAIT_AI_RESPONSE state")
        self.state = AgentState.AWAIT_AI_RESPONSE
    
    def _enter_await_tool_response(self):
        self.logger.debug("Entering AWAIT_TOOL_RESPONSE state")
        self.state = AgentState.AWAIT_TOOL_RESPONSE


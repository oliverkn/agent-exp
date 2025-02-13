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
    def __init__(self, thread_id):
        self.thread_id = thread_id
        
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
        
        self.tool_box = ToolBox()
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
        self.messages.append({"role": "developer", "content": [{"type" : "text", "text" : "Your task is to use the available tools to solve the any given tasks."}]})
    
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
            return completion
        
        self.exec_and_callback(run_completion, EventTypes.AI_RESULT)
    
    def _add_message(self, msg):
        self.messages.append(msg)
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
                    self._add_message({"role": "user", "content": event.data})
                    self._submit_completion()
                    self._enter_await_ai_response()
                elif event.type == EventTypes.NOTIFICATION:
                    self.logger.info("Processing notification")
                    self.notifications.append(event.data)
                
                    content = "Here are the latest notifications:"
                    for notification in self.notifications:
                        content += f"\n{notification}"

                    self._add_message({"role": "developer", "content": content})
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
                    
                    if completion.choices[0].finish_reason == "stop":
                        self.logger.debug("AI completion finished with 'stop'")
                        self._add_message(completion.choices[0].message)
                        self._enter_await_input()
                        
                    elif completion.choices[0].finish_reason == "tool_calls":
                        self.logger.debug("AI completion finished with 'tool_calls'")
                        self._add_message(completion.choices[0].message)
                        for tool_call in completion.choices[0].message.tool_calls:
                            name = tool_call.function.name
                            args = tool_call.function.arguments
                            self.logger.info(f"Calling tool: {name}({args})")

                            async def tool_execution():
                                return tool_call.id, await self.tool_box.call(name, args)

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
                    tool_call_id, result = event.data
                    
                    self._add_message({
                        "role": "tool", 
                        "tool_call_id": tool_call_id, 
                        "content": json.dumps(result)
                    })
                    
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


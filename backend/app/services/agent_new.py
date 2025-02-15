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
from ..models import Message, Thread
from .. import database as db

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
    def __init__(self, thread_id: str):
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
        # self.model = "gpt-4o"
        self.notifications = []
        self.current_task = None
        
        self.tool_box = ToolBox(self.thread_id)
        self.tool_box.add_tool(SetupMSGraph())
        self.tool_box.add_tool(AuthenticateMSGraph())
        self.tool_box.add_tool(GetLatestEmail())
        self.tool_box.add_tool(ListEmails())
        self.tool_box.add_tool(ViewPdfAttachment())
        self.tool_box.add_tool(ViewPdfFile())
        self.tool_box.add_tool(SaveEmailAttachment())
        self.tool_box.add_tool(BexioListAccounts())
        self.tool_box.add_tool(BexioGetContacts())
        self.tool_box.add_tool(BexioCreateContact())
        # self.tool_box.add_tool(BexioCreateInvoicePayable())
        # self.tool_box.add_tool(BexioUploadEmailAttachment())
        self.tool_box.add_tool(BexioUploadFile())
        self.tool_box.add_tool(BexioCreateInvoicePayable())
        
        self.tools_schema = []
        for tool in self.tool_box.get_tools():
            schema = self._to_function_schema(tool)
            self.tools_schema.append(schema)
        
        self._add_message(AgentState.AWAIT_INPUT, "developer", "Your task is to use the available tools to solve the any given tasks. If you respond to the user, always respond in markdown format without indicating that it is markdown.")
        
    
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
                messages=self._get_api_messages(),
                tools=self.tools_schema,
                tool_choice="auto",
                parallel_tool_calls=False,
                temperature=0.0,
                max_tokens=5000
            )
            self.logger.debug(completion.choices[0].message)
            return completion
        
        self.exec_and_callback(run_completion, EventTypes.AI_RESULT)
    
    def _add_message(self, agent_state, role, content):
        self.logger.debug(f"Adding {role} message: {content}")
    
        with db.SessionLocal() as session:
            db_message = Message(
                thread_id=self.thread_id,
                api_messages=json.dumps([{"role": role, "content": content}]),
                agent_state=agent_state.value,
                role=role,
                content=content
            )
            session.add(db_message)
            session.commit()
        
        self.emitter.emit(self.thread_id, {"status": "update"})
    
    def _add_user_message(self, msg):
        self.logger.debug(f"Adding user message: {msg}")
              
        with db.SessionLocal() as session:
            db_message = Message(
                thread_id=self.thread_id,
                api_messages=json.dumps([{"role": "user", "content": msg}]),
                agent_state=AgentState.AWAIT_AI_RESPONSE.value,
                role="user",
                content=msg
            )
            session.add(db_message)
            session.commit()
        
        self.emitter.emit(self.thread_id, {"status": "update"})
    
    def _add_assistant_message(self, msg, finish_reason):
        self.logger.debug(f"Adding assistant message: {msg}")
        
        if finish_reason == "stop":
            agent_state = AgentState.AWAIT_INPUT
        elif finish_reason == "tool_calls":
            agent_state = AgentState.AWAIT_TOOL_RESPONSE
        else:
            raise Exception(f"Invalid finish reason: {finish_reason}")
        
        with db.SessionLocal() as session:
            db_message = Message(
                thread_id=self.thread_id,
                api_messages=json.dumps([msg.dict()]),
                agent_state=agent_state.value,
                role=msg.role,
                content=msg.content
            )
            session.add(db_message)
            session.commit()
        
        self.emitter.emit(self.thread_id, {"status": "update"})
    
    def _add_tool_result_message(self, tool_call_id, tool_name, tool_args):
        self.logger.debug(f"Adding tool call result for tool call {tool_call_id}")
        api_message = {
            "role": "tool", 
            "tool_call_id": tool_call_id, 
            "content": json.dumps({"error" : "Tool call was cancelled."})
        }
        with db.SessionLocal() as session:
            db_message = Message(
                thread_id=self.thread_id,
                api_messages=json.dumps([api_message]),
                agent_state=AgentState.AWAIT_TOOL_RESPONSE.value,
                role="tool",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_args=json.dumps(tool_args),
                tool_state="running"
            )
            session.add(db_message)
            session.commit()
            
        self.emitter.emit(self.thread_id, {"status": "update"})
    
    def __update_tool_call_message(self, tool_call_id, tool_call_result):
        self.logger.debug(f"Updating tool call message for tool_call_id: {tool_call_id}")
        
        with db.SessionLocal() as session:
            db_message = session.query(Message).filter(Message.tool_call_id == tool_call_id).first()
            if not db_message:
                raise Exception(f"Tool call message not found for tool_call_id: {tool_call_id}")
            
            # Update existing message
            db_message.content = tool_call_result.display_data
            db_message.tool_result = json.dumps(tool_call_result.result)
            db_message.tool_state = tool_call_result.state.value
            db_message.tool_display_data = tool_call_result.display_data
            
            session.commit()
        
        self.emitter.emit(self.thread_id, {"status": "update"})
        
    def __finalize_tool_call_message(self, tool_call_id, tool_call_result):
        self.logger.debug(f"Finalizing tool call message for tool_call_id: {tool_call_id}")
        
        with db.SessionLocal() as session:
            db_message = session.query(Message).filter(Message.tool_call_id == tool_call_id).first()
            if not db_message:
                raise Exception(f"Tool call message not found for tool_call_id: {tool_call_id}")
        
            api_messages = []
        
            if tool_call_result.result_type == "text":
                content = json.dumps(tool_call_result.result)
                api_messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(tool_call_result.result)})
                db_message.tool_result = content
                db_message.content = tool_call_result.display_data
                db_message.content_type = "text"
                
            elif tool_call_result.result_type == "base64_png_list":
                api_messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": f"{len(tool_call_result.result)} images will be included in the next message"})
                api_messages.append({
                    "role": "user", 
                    "content": [{
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}",
                            "detail": "high"
                        }
                    } for base64_image in tool_call_result.result]
                })
                
                db_message.tool_result = f"{len(tool_call_result.result)} images"
                db_message.content_type = "image_url_list"
                db_message.content = json.dumps([f"data:image/png;base64,{base64_image}" for base64_image in tool_call_result.result])
                
            else:
                raise Exception(f"Invalid result type: {tool_call_result.result_type}")
        
            db_message.api_messages = json.dumps(api_messages)
            db_message.agent_state = AgentState.AWAIT_AI_RESPONSE.value
            db_message.tool_state = tool_call_result.state.value            
            
            session.commit()
        
        self.emitter.emit(self.thread_id, {"status": "update"})
    
    def _get_messages(self):
        with db.SessionLocal() as session:
            return session.query(Message).filter(Message.thread_id == self.thread_id).order_by(Message.created_at).all()
            
    def _get_latest_agent_state(self):
        messages = self._get_messages()
        return AgentState(messages[-1].agent_state)
    
    def _get_api_messages(self):
        with db.SessionLocal() as session:
            db_message_list = session.query(Message).filter(Message.thread_id == self.thread_id).order_by(Message.created_at).all()
            messages = []
            for msg in db_message_list:
                api_messages = json.loads(msg.api_messages)
                if isinstance(api_messages, list):
                    messages.extend(api_messages)
                else:
                    messages.append(api_messages)
            return messages
    
    def _cancel_current_task(self):
        if self.current_task is not None:
            self.current_task.cancel()
        
    def handle_event(self, event: Event):
        agent_state = self._get_latest_agent_state()
        self.logger.debug(f"Handling event: {event.type} in state: {agent_state}")
        
        match agent_state:
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
                    self.logger.error(f"Invalid event type {event.type} for current state {agent_state}")
                    raise Exception(f"Invalid event type {event.type} for current state {agent_state}")
            
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
                        self._add_assistant_message(completion.choices[0].message, completion.choices[0].finish_reason)
                        self._enter_await_input()
                        
                    elif completion.choices[0].finish_reason == "tool_calls":
                        self.logger.debug("AI completion finished with 'tool_calls'")
                        self._add_assistant_message(completion.choices[0].message, completion.choices[0].finish_reason)
                        for tool_call in completion.choices[0].message.tool_calls:
                            name = tool_call.function.name
                            args = tool_call.function.arguments
                            self.logger.info(f"Calling tool: {name}({args})")
                            
                            self._add_tool_result_message(tool_call.id, name, args)
                            
                            def on_update(tool_call_result: ToolCallResult): 
                                self.__update_tool_call_message(tool_call.id, tool_call_result)

                            async def tool_execution():
                                return tool_call.id, await self.tool_box.call(name, args, on_update)

                            self.exec_and_callback(tool_execution, EventTypes.TOOL_RESULT)
                            self._enter_await_tool_response()
                    else:
                        self.logger.error(f"Invalid finish reason {completion.choices[0].finish_reason}")
                        raise Exception(f"Invalid finish reason {completion.choices[0].finish_reason}")
                        
                else:
                    self.logger.error(f"Invalid event type {event.type} for current state {agent_state}")
                    raise Exception(f"Invalid event type for current state {agent_state}")
                    
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
                    self.logger.error(f"Invalid event type for current state {agent_state}")
                    raise Exception(f"Invalid event type for current state {agent_state}")
        
        return True
                
    
    def exec_and_callback(self, f, event_type: EventTypes):
        self.logger.debug(f"Setting up execution for event type: {event_type}")
        async def wrapper():
            try:
                self.logger.debug("Starting task execution")
                
                # Create new event loop for the thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Run the async function in the new thread
                if asyncio.iscoroutinefunction(f):
                    result = await asyncio.wait_for(f(), timeout=self.timeout)
                else:
                    result = await asyncio.wait_for(asyncio.to_thread(f), timeout=self.timeout)
                
                event = Event(type=event_type, data=result)
                self.handle_event(event)
                
                loop.close()
                
            except asyncio.TimeoutError:
                self.logger.error(f"Task timed out after {self.timeout} seconds")
                event = Event(type=event_type, data={"error": f"Task timed out after {self.timeout} seconds"})
                self.handle_event(event)
            except Exception as e:
                self.logger.error(f"Error in task execution: {e}", exc_info=True)
                event = Event(type=event_type, data={"error": str(e)})
                self.handle_event(event)

        # Run wrapper in new thread
        self.current_task = asyncio.create_task(asyncio.to_thread(lambda: asyncio.run(wrapper())))
    
    def _enter_await_input(self):
        self.logger.debug("Entering AWAIT_INPUT state")
        self.state = AgentState.AWAIT_INPUT
        
    def _enter_await_ai_response(self):
        self.logger.debug("Entering AWAIT_AI_RESPONSE state")
        self.state = AgentState.AWAIT_AI_RESPONSE
    
    def _enter_await_tool_response(self):
        self.logger.debug("Entering AWAIT_TOOL_RESPONSE state")
        self.state = AgentState.AWAIT_TOOL_RESPONSE


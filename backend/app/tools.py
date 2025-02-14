import requests
import msal
import os
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
import asyncio
import time
import tkinter as tk
from tkinter import simpledialog
from sqlalchemy.orm import Session
import json
from enum import Enum

from .models import Message

class ToolCallState(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    

class ToolCallResult(BaseModel):
    result: object | None = None
    state: ToolCallState
    display_data: str | None = None
    

class ToolBox:
    def __init__(self, db: Session):
        self.tools = {}
        self.global_state = {}

    def add_tool(self, tool):
        self.tools[tool.tool_name] = tool
        
    def get_tools(self):
        return list(self.tools.values())
        
    async def call(self, tool_name: str, args: dict, on_update) -> ToolCallResult:
        try:
            if tool_name not in self.tools:
                raise Exception(f"Tool {tool_name} not found")
        
            tool = self.tools[tool_name]
            args = tool.args_model.model_validate_json(args)
            
            return await tool.run(args, self.global_state, on_update)
        
        except Exception as e:
            return ToolCallResult(result={"error" : str(e)}, state=ToolCallState.ERROR)


class UserInputCMD:
    class Args(BaseModel):
        message_to_user: str
    
    args_model = Args
    tool_name = "ask_user_for_input"
    tool_description = "This tool is used to get user input."
    
    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        
        try:
            user_input = simpledialog.askstring("Input", args.message_to_user)
        finally:
            root.quit()  # Stop the mainloop
            root.destroy()  # Destroy the window
        
        return ToolCallResult(result=user_input, state=ToolCallState.COMPLETED)
    
# class UserInput:
#     class Args(BaseModel):
#         message_to_user: str
    
#     def __init__(self, input_function):
#         self.input_function = input_function
    
#     args_model = Args
#     tool_name = "ask_user_for_input"
#     tool_description = "This tool is used to get user input."
    
#     async def run(self, args: Args, global_state: dict):
#         return {"user_input": self.input_function(args.message_to_user)}

class SetupMSGraph:
    class Args(BaseModel):
        client_id: str
        tenant_id: str
        email: str
    
    args_model = Args
    tool_name = "setup_ms_graph"
    tool_description = """This tool is used to setup the MS Graph API.
    It will set the email, client_id, and tenant_id.
    Call this tool first before calling authenticate_ms_graph.
    If you don't have a client_id, tenant_id, or email, ask the user for it."""
    

    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        global_state["ms_graph.email"] = args.email
        global_state["ms_graph.client_id"] = args.client_id
        global_state["ms_graph.tenant_id"] = args.tenant_id
        
        return ToolCallResult(result=None, state=ToolCallState.COMPLETED)


class AuthenticateMSGraph:
    class Args(BaseModel):
        pass
    
    tool_name = "authenticate_ms_graph"
    tool_description = ""
    args_model = Args

    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        # Microsoft Graph API endpoints
        AUTHORITY = f"https://login.microsoftonline.com/{global_state["ms_graph.tenant_id"]}"
        SCOPES = ["Mail.Read"]

        display_text = ""

        # Initialize the MSAL client (Public Client)
        app = msal.PublicClientApplication(global_state["ms_graph.client_id"], authority=AUTHORITY)

        # Start device authentication flow
        device_flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in device_flow:
            raise Exception("Failed to start device flow. Try again.")

        # Show user instructions
        display_text += f"Please sign in at: <a href='{device_flow['verification_uri']}' target='_blank'>{device_flow['verification_uri']}</a><br>"
        display_text += f"Use this code: <code style='font-family: monospace; background-color: #f0f0f0; padding: 2px 4px; border-radius: 4px;'>{device_flow['user_code']}</code>"
        on_update(ToolCallResult(result=None, state=ToolCallState.RUNNING, display_data=display_text))

        # Continuously check if the user has signed in
        while True:
            token_response = app.acquire_token_by_device_flow(device_flow)
            
            if "access_token" in token_response:
                display_text += "<br>✅ Sign-in detected! Access token acquired."
                break
            elif "error" in token_response and token_response["error"] == "authorization_pending":
                time.sleep(5)  # Wait and retry
            else:
                raise Exception(f"Authentication failed: {token_response}")
            
        global_state["ms_graph.access_token"] = token_response["access_token"]
        
        return ToolCallResult(result=None, state=ToolCallState.COMPLETED, display_data=display_text)


class GetLatestEmail:
    class Args(BaseModel):
        pass
    
    tool_name = "get_latest_email"
    tool_description = ""
    args_model = Args
    
    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        headers = {"Authorization": f"Bearer {global_state['ms_graph.access_token']}"}
        GRAPH_API_URL = "https://graph.microsoft.com/v1.0/me/messages"

        response = requests.get(GRAPH_API_URL, headers=headers)

        # Display emails
        if response.status_code == 200:
            emails = response.json().get("value", [])
        else:
            raise Exception(f"Error: {response.json()}")

        return ToolCallResult(result={"subject": emails[0]["subject"], "from": emails[0]["from"]["emailAddress"]["address"], "receivedDateTime": emails[0]["receivedDateTime"], "bodyPreview": emails[0]["bodyPreview"]}, state=ToolCallState.COMPLETED)
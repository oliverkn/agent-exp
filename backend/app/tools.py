import requests
import msal
import os
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
import asyncio

class ToolBox:
    def __init__(self):
        self.tools = {}
        self.global_state = {}

    def add_tool(self, tool):
        self.tools[tool.tool_name] = tool
        
    def get_tools(self):
        return list(self.tools.values())
        
    async def call(self, tool_name, args):
        try:
            if tool_name not in self.tools:
                raise Exception(f"Tool {tool_name} not found")
        
            tool = self.tools[tool_name]
            
            args = tool.args_model.model_validate_json(args)
            
            return await tool.run(args, self.global_state)
        
        except Exception as e:
            return {"error": str(e)}
            
class UserInputCMD:
    class Args(BaseModel):
        message_to_user: str
    
    args_model = Args
    tool_name = "ask_user_for_input"
    tool_description = "This tool is used to get user input."
    
    async def run(self, args: Args, global_state: dict):
        print(args.message_to_user)
        return {"user_input": input()}
    
class UserInput:
    class Args(BaseModel):
        message_to_user: str
    
    def __init__(self, input_function):
        self.input_function = input_function
    
    args_model = Args
    tool_name = "ask_user_for_input"
    tool_description = "This tool is used to get user input."
    
    async def run(self, args: Args, global_state: dict):
        return {"user_input": self.input_function(args.message_to_user)}

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
    

    async def run(self, args: Args, global_state: dict):
        global_state["ms_graph.email"] = args.email
        global_state["ms_graph.client_id"] = args.client_id
        global_state["ms_graph.tenant_id"] = args.tenant_id
        
        return {"success": True}


class AuthenticateMSGraph:
    class Args(BaseModel):
        pass
    
    tool_name = "authenticate_ms_graph"
    tool_description = ""
    args_model = Args

    async def run(self, args: Args, global_state: dict):
         # Microsoft Graph API endpoints
        AUTHORITY = f"https://login.microsoftonline.com/{global_state["ms_graph.tenant_id"]}"
        SCOPES = ["Mail.Read"]

        # Initialize the MSAL client (Public Client)
        app = msal.PublicClientApplication(global_state["ms_graph.client_id"], authority=AUTHORITY)

        # Start device authentication flow
        device_flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in device_flow:
            raise Exception("Failed to start device flow. Try again.")

        # Show user instructions
        print(f"Please sign in at: {device_flow['verification_uri']}")
        print(f"Use this code: {device_flow['user_code']}")

        # Continuously check if the user has signed in
        print("\nWaiting for user to sign in...")
        while True:
            token_response = app.acquire_token_by_device_flow(device_flow)
            
            if "access_token" in token_response:
                print("✅ Sign-in detected! Access token acquired.")
                break
            elif "error" in token_response and token_response["error"] == "authorization_pending":
                time.sleep(5)  # Wait and retry
            else:
                raise Exception(f"Authentication failed: {token_response}")
            
        global_state["ms_graph.access_token"] = token_response["access_token"]
        
        return {"success": True}


class GetLatestEmail:
    class Args(BaseModel):
        pass
    
    tool_name = "get_latest_email"
    tool_description = ""
    args_model = Args
    
    async def run(self, args: Args, global_state: dict):
        headers = {"Authorization": f"Bearer {global_state['ms_graph.access_token']}"}
        GRAPH_API_URL = "https://graph.microsoft.com/v1.0/me/messages"

        response = requests.get(GRAPH_API_URL, headers=headers)

        # Display emails
        if response.status_code == 200:
            emails = response.json().get("value", [])
        else:
            return {"Error:", response.json()}
        
        return {"subject": emails[0]["subject"], "from": emails[0]["from"]["emailAddress"]["address"], "receivedDateTime": emails[0]["receivedDateTime"], "bodyPreview": emails[0]["bodyPreview"]}
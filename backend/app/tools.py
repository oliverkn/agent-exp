import requests
import msal
import os
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel

class ToolBox:
    def __init__(self):
        self.tools = {}
        self.global_state = {}

    def add_tool(self, tool):
        self.tools[tool.tool_name] = tool
        
    def call(self, tool_name, args):
        try:
            if tool_name not in self.tools:
                raise Exception(f"Tool {tool_name} not found")
        
            tool = self.tools[tool_name]
            
            args = tool.args_model.model_validate_json(args)
            
            return tool.run(args, self.global_state)
        
        except Exception as e:
            return {"error": str(e)}
            

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
    

    def run(self, args: Args, global_state: dict):
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

    def run(self, args: Args, global_state: dict):
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
    
    def run(self, args: Args, global_state: dict):
        headers = {"Authorization": f"Bearer {global_state['ms_graph.access_token']}"}
        GRAPH_API_URL = "https://graph.microsoft.com/v1.0/me/messages"

        response = requests.get(GRAPH_API_URL, headers=headers)

        # Display emails
        if response.status_code == 200:
            emails = response.json().get("value", [])
        else:
            return {"Error:", response.json()}
        
        return {"subject": emails[0]["subject"], "from": emails[0]["from"]["emailAddress"]["address"], "receivedDateTime": emails[0]["receivedDateTime"], "bodyPreview": emails[0]["bodyPreview"]}

class EmailTool:
    def __init__(self, client_id: str, tenant_id: str, email: str):
        self.email = email
        self.client_id = client_id
        self.tenant_id = tenant_id
        
    
    def authenticate(self):
        # Microsoft Graph API endpoints
        AUTHORITY = f"https://login.microsoftonline.com/{self.tenant_id}"
        SCOPES = ["Mail.Read"]

        # Initialize the MSAL client (Public Client)
        app = msal.PublicClientApplication(self.client_id, authority=AUTHORITY)

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
            
        self.access_token = token_response["access_token"]
        
        return True

    def get_latest_email(self) -> Optional[dict]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        GRAPH_API_URL = "https://graph.microsoft.com/v1.0/me/messages"

        response = requests.get(GRAPH_API_URL, headers=headers)

        # Display emails
        if response.status_code == 200:
            emails = response.json().get("value", [])
            for i, email in enumerate(emails[:5]):  # Show first 5 emails
                print(f"\nEmail {i+1}:")
                print(f"Subject: {email['subject']}")
                print(f"From: {email['from']['emailAddress']['address']}")
                print(f"Received: {email['receivedDateTime']}")
                print(f"Preview: {email['bodyPreview']}\n")
        else:
            print("Error:", response.json())
            
    

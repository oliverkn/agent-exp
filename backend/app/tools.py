import requests
import msal
import os
from datetime import datetime, timedelta
from typing import Literal
from pydantic import BaseModel, Field
import asyncio
import time
import tkinter as tk
from tkinter import simpledialog
from sqlalchemy.orm import Session
import json
from enum import Enum

from .models import Message, Thread
from . import database as db

class ToolCallState(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    

class ToolCallResult(BaseModel):
    state: ToolCallState
    result_type: Literal["text", "base64_png_list"] = "text"
    result: object | None = None
    display_data: str | None = None
    

class ToolBox:
    def __init__(self, thread_id: int):
        self.thread_id = thread_id
        
        self.tools = {}
        self.global_state = {}
        
        with db.SessionLocal() as session:
            #load thread
            self.thread = session.query(Thread).filter(Thread.id == thread_id).first()
            if not self.thread:
                raise Exception(f"Thread {thread_id} not found")
            
            #load toolbox state
            self.global_state = json.loads(self.thread.toolbox_state)
            

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
            tool_call_result = await tool.run(args, self.global_state, on_update)
        
            with db.SessionLocal() as session:
                thread = session.query(Thread).filter(Thread.id == self.thread_id).first()
                thread.toolbox_state = json.dumps(self.global_state)
                session.commit()
                
            return tool_call_result
        
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
    
class ListEmails:
    class Args(BaseModel):
        not_older_than_days: int = Field(description="The number of days to look back for emails. Must be greater than 0.")
        only_has_attachments: bool = Field(description="If True, only emails with attachments will be returned.")
        
    tool_name = "list_emails"
    tool_description = "This tool is used to list emails from the user's inbox."
    args_model = Args
    
    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        headers = {"Authorization": f"Bearer {global_state['ms_graph.access_token']}"}
        GRAPH_API_URL = "https://graph.microsoft.com/v1.0/me/messages"
        
        # Calculate the date filter
        filter_date = datetime.now() - timedelta(days=args.not_older_than_days)
        filter_date_str = filter_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Build query parameters - using bodyPreview instead of body
        params = {
            "$select": "id,subject,from,receivedDateTime,hasAttachments,bodyPreview,attachments",
            "$orderby": "receivedDateTime desc",
            "$filter": f"receivedDateTime ge {filter_date_str}",
            "$expand": "attachments($select=name)",  # Include attachment data
            "$top": 50  # Number of items per page
        }
        
        if args.only_has_attachments:
            params["$filter"] += " and hasAttachments eq true"
        
        all_emails = []
        
        while True:
            # Make the API request
            response = requests.get(GRAPH_API_URL, headers=headers, params=params)
            
            if response.status_code != 200:
                raise Exception(f"Error fetching emails: {response.json()}")
            
            response_data = response.json()
            emails = response_data.get("value", [])
            
            # Format and add emails from this page - using bodyPreview
            email_list = [{
                "id": email["id"],
                "subject": email["subject"],
                "from": email["from"]["emailAddress"]["address"],
                "receivedDateTime": email["receivedDateTime"],
                "hasAttachments": email["hasAttachments"],
                "bodyPreview": email["bodyPreview"],  # Using preview instead of full body
                "attachments": [att["name"] for att in email.get("attachments", [])]
            } for email in emails]
            
            all_emails.extend(email_list)
            
            # Check if there are more pages
            if "@odata.nextLink" not in response_data:
                break
                
            # Update URL for next page
            GRAPH_API_URL = response_data["@odata.nextLink"]
            params = {}  # Parameters are included in the nextLink URL
            
            # Optional: Update progress
            on_update(ToolCallResult(
                state=ToolCallState.RUNNING,
                display_data=f"Fetched {len(all_emails)} emails so far..."
            ))
        
        return ToolCallResult(
            result=all_emails,
            state=ToolCallState.COMPLETED,
            display_data=f"Fetched {len(all_emails)} emails so far..."
        )

def pdf_to_base64_png(pdf_byte_buffer, page_limit=10, dpi=200):
    """Returns a list of base64 encoded PNG images of the PDF pages."""
    import fitz as pymupdf
    import io
    from PIL import Image
    import base64

    pdf_document = pymupdf.open(stream=pdf_byte_buffer, filetype="pdf")
    base64_images = []

    # Calculate the zoom factor based on DPI
    zoom = dpi / 72  # 72 is the default DPI for PDFs
    mat = pymupdf.Matrix(zoom, zoom)

    for page_num in range(min(len(pdf_document), page_limit)):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        base64_images.append(base64.b64encode(buffer.getvalue()).decode("utf-8"))

    pdf_document.close()

    return base64_images

class ViewPdfAttachment:
    class Args(BaseModel):
        email_id: str
        attachment_name: str
        n_pages: int = Field(description="The number of pages to view. Must be greater than 0.")
        
    tool_name = "view_pdf_attachment"
    tool_description = "This tool is used to view first n pages of a PDF attachment from an email."
    args_model = Args
    
    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        headers = {"Authorization": f"Bearer {global_state['ms_graph.access_token']}"}
        
        # First get attachment metadata to get the id
        metadata_url = f"https://graph.microsoft.com/v1.0/me/messages/{args.email_id}/attachments"
        metadata_response = requests.get(metadata_url, headers=headers)
        if metadata_response.status_code != 200:
            raise Exception(f"Error fetching attachment metadata: {metadata_response.json()}")
            
        attachments = metadata_response.json().get("value", [])
        attachment_id = None
        for att in attachments:
            if att["name"] == args.attachment_name:
                attachment_id = att["id"]
                break
                
        if not attachment_id:
            raise Exception(f"Attachment {args.attachment_name} not found")
        
        # Download the attachment
        download_url = f"https://graph.microsoft.com/v1.0/me/messages/{args.email_id}/attachments/{attachment_id}/$value"
        response = requests.get(download_url, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Error downloading attachment: {response.status_code}")
        
        # Convert PDF to base64 images
        images = pdf_to_base64_png(response.content, page_limit=args.n_pages)
        
        return ToolCallResult(
            result_type="base64_png_list",
            result=images,
            state=ToolCallState.COMPLETED
        )

class SaveEmailAttachment:
    class Args(BaseModel):
        email_id: str
        attachment_name: str
        file_name: str
        
    tool_name = "save_email_attachment"
    tool_description = "Saves an attachment from an email to the local file system."
    args_model = Args
    
    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        headers = {"Authorization": f"Bearer {global_state['ms_graph.access_token']}"}
        
        # First get attachment metadata to get the id
        metadata_url = f"https://graph.microsoft.com/v1.0/me/messages/{args.email_id}/attachments"
        metadata_response = requests.get(metadata_url, headers=headers)
        if metadata_response.status_code != 200:
            raise Exception(f"Error fetching attachment metadata: {metadata_response.json()}")
            
        attachments = metadata_response.json().get("value", [])
        attachment_id = None
        for att in attachments:
            if att["name"] == args.attachment_name:
                attachment_id = att["id"]
                break
                
        if not attachment_id:
            raise Exception(f"Attachment {args.attachment_name} not found")
        
        # Download the attachment
        download_url = f"https://graph.microsoft.com/v1.0/me/messages/{args.email_id}/attachments/{attachment_id}/$value"
        response = requests.get(download_url, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Error downloading attachment: {response.status_code}")
        
        # Save the attachment to the working directory
        with open(os.path.join(os.getenv("TOOLS_WORKING_DIR"), args.file_name), "wb") as f:
            f.write(response.content)
            
        return ToolCallResult(
            result=None,
            state=ToolCallState.COMPLETED
        )

# class AuthorizeBexio:
#     class Args(BaseModel):
#         client_id: str
#         client_secret: str
#         redirect_uri: str
#         code: str
    
#     tool_name = "authorize_bexio"
#     tool_description = "This tool is used to authorize the Bexio API."
#     args_model = Args

class BexioGetContacts:
    class Args(BaseModel):
        pass
    
    tool_name = "bexio_get_contacts"
    tool_description = "Lists all contacts from Bexio."
    args_model = Args
    
    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {os.getenv('BEXIO_PAT')}"
        }

        try:
            response = requests.get("https://api.bexio.com/2.0/contact", headers=headers)
            
            if response.status_code == 200:
                contacts = response.json()
                simplified_contacts = [
                    {
                        "id": contact["id"],
                        "name": contact["name_1"],
                        "address": contact["address"],
                        "postcode": contact["postcode"]
                    }
                    for contact in contacts
                ]
                return ToolCallResult(
                    result=simplified_contacts,
                    state=ToolCallState.COMPLETED
                )
            else:
                return ToolCallResult(
                    result={"error": f"Failed to fetch contacts: {response.status_code} - {response.text}"},
                    state=ToolCallState.ERROR
                )
                
        except Exception as e:
            return ToolCallResult(
                result={"error": f"Error fetching contacts: {str(e)}"},
                state=ToolCallState.ERROR
            )
            
class BexioCreateContact:
    class Args(BaseModel):
        name: str = Field(description="Primary name of the contact (name_1)")
        address: str = Field(description="Street address")
        postcode: str = Field(description="Postal code")
        city: str = Field(description="City name")
        email: str | None = Field(default=None, description="Primary email address")
        phone: str | None = Field(default=None, description="Fixed phone number")
        mobile: str | None = Field(default=None, description="Mobile phone number")
        website: str | None = Field(default=None, description="Website URL")
        remarks: str | None = Field(default=None, description="Additional remarks")
    
    tool_name = "bexio_create_contact"
    tool_description = "Creates a new contact in Bexio with the specified information."
    args_model = Args
    
    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.getenv('BEXIO_PAT')}"
        }

        # Construct the payload with required and optional fields
        payload = {
            "contact_type_id": 1,  # 1 is typically for company
            "name_1": args.name,
            "address": args.address,
            "postcode": args.postcode,
            "city": args.city,
            "country_id": 1,  # 1 is typically for Switzerland
            "user_id": 1,
            "owner_id": 1
        }

        # Add optional fields if they are provided
        if args.email:
            payload["mail"] = args.email
        if args.phone:
            payload["phone_fixed"] = args.phone
        if args.mobile:
            payload["phone_mobile"] = args.mobile
        if args.website:
            payload["url"] = args.website
        if args.remarks:
            payload["remarks"] = args.remarks

        try:
            response = requests.post(
                "https://api.bexio.com/2.0/contact",
                json=payload,  # using json parameter to automatically handle JSON encoding
                headers=headers
            )
            
            if response.status_code in (200, 201):
                return ToolCallResult(
                    result=response.json(),
                    state=ToolCallState.COMPLETED
                )
            else:
                return ToolCallResult(
                    result={"error": f"Failed to create contact: {response.status_code} - {response.text}"},
                    state=ToolCallState.ERROR
                )
                
        except Exception as e:
            return ToolCallResult(
                result={"error": f"Error creating contact: {str(e)}"},
                state=ToolCallState.ERROR
            )
        
# class BexioCreateInvoicePayable:
#     class Address(BaseModel):
#         lastname_company: str
#         address_line: str
#         postcode: str
#         city: str
#         country_code: str = "CH"
        
#     class LineItem(BaseModel):
#         title: str
#         amount: float
#         tax_id: int
#         booking_account_id: int
#         position: int | None = None
        
#     class Payment(BaseModel):
#         type: Literal["IBAN"] = "IBAN"
#         iban: str
#         name: str
#         address: str
#         postcode: str
#         city: str
#         country_code: str = "CH"
#         execution_date: str | None = None
#         message: str | None = None
        
#     class Args(BaseModel):
#         supplier_id: int = Field(description="ID of the contact that represents the supplier")
#         title: str = Field(description="Title of the bill")
#         bill_date: str = Field(description="Date of the bill (YYYY-MM-DD)")
#         due_date: str = Field(description="Due date of the bill (YYYY-MM-DD)")
#         currency_code: str = Field(default="CHF", description="Currency code (default: CHF)")
#         address: Address = Field(description="Address information of the supplier")
#         line_items: list[LineItem] = Field(description="List of line items for the bill")
#         payment: Payment = Field(description="Payment information")
#         vendor_ref: str | None = Field(default=None, description="Reference text from vendor")
#         attachment_ids: list[str] | None = Field(default=None, description="List of attachment IDs")
    
#     tool_name = "bexio_create_invoice_payable"
#     tool_description = "Creates a new invoice payable in Bexio with the specified information."
#     args_model = Args
    
#     async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
#         headers = {
#             "Accept": "application/json",
#             "Content-Type": "application/json",
#             "Authorization": f"Bearer {os.getenv('BEXIO_PAT')}"
#         }

#         # Calculate total amount from line items
#         total_amount = sum(item.amount for item in args.line_items)

#         # Assign positions to line items if not provided
#         for i, item in enumerate(args.line_items):
#             if item.position is None:
#                 item.position = i

#         # Construct the payload
#         payload = {
#             "supplier_id": args.supplier_id,
#             "title": args.title,
#             "bill_date": args.bill_date,
#             "due_date": args.due_date,
#             "currency_code": args.currency_code,
#             "amount_calc": total_amount,
#             "manual_amount": False,
#             "item_net": False,
#             "address": {
#                 "lastname_company": args.address.lastname_company,
#                 "address_line": args.address.address_line,
#                 "postcode": args.address.postcode,
#                 "city": args.address.city,
#                 "country_code": args.address.country_code,
#                 "type": "PRIVATE"
#             },
#             "line_items": [item.model_dump(exclude_none=True) for item in args.line_items],
#             "payment": {
#                 "type": args.payment.type,
#                 "iban": args.payment.iban,
#                 "name": args.payment.name,
#                 "address": args.payment.address,
#                 "postcode": args.payment.postcode,
#                 "city": args.payment.city,
#                 "country_code": args.payment.country_code
#             }
#         }

#         # Add optional fields
#         if args.vendor_ref:
#             payload["vendor_ref"] = args.vendor_ref
#         if args.attachment_ids:
#             payload["attachment_ids"] = args.attachment_ids
#         if args.payment.execution_date:
#             payload["payment"]["execution_date"] = args.payment.execution_date
#         if args.payment.message:
#             payload["payment"]["message"] = args.payment.message

#         try:
#             response = requests.post(
#                 "https://api.bexio.com/4.0/purchase/bills",
#                 json=payload,
#                 headers=headers
#             )
            
#             if response.status_code in (200, 201):
#                 return ToolCallResult(
#                     result=response.json(),
#                     state=ToolCallState.COMPLETED
#                 )
#             else:
#                 return ToolCallResult(
#                     result={"error": f"Failed to create invoice: {response.status_code} - {response.text}"},
#                     state=ToolCallState.ERROR
#                 )
                
#         except Exception as e:
#             return ToolCallResult(
#                 result={"error": f"Error creating invoice: {str(e)}"},
#                 state=ToolCallState.ERROR
#             )
            
class BexioUploadEmailAttachment:
    class Args(BaseModel):
        email_id: str = Field(description="ID of the email containing the attachment")
        attachment_id: str = Field(description="ID of the attachment to upload")
        
    tool_name = "upload_email_attachment_to_bexio"
    tool_description = "Uploads an attachment from an email to Bexio."
    args_model = Args
    
    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        # First, download the attachment from MS Graph
        if "ms_graph.access_token" not in global_state:
            return ToolCallResult(
                result={"error": "Microsoft Graph not authenticated. Please authenticate first."},
                state=ToolCallState.ERROR
            )

        ms_headers = {
            "Authorization": f"Bearer {global_state['ms_graph.access_token']}"
        }

        # Get attachment metadata first to get the name
        metadata_url = f"https://graph.microsoft.com/v1.0/me/messages/{args.email_id}/attachments/{args.attachment_id}"
        metadata_response = requests.get(metadata_url, headers=ms_headers)
        
        if metadata_response.status_code != 200:
            return ToolCallResult(
                result={"error": f"Failed to get attachment metadata: {metadata_response.status_code} - {metadata_response.text}"},
                state=ToolCallState.ERROR
            )
            
        attachment_name = metadata_response.json().get("name")
        
        # Download the attachment content
        download_url = f"https://graph.microsoft.com/v1.0/me/messages/{args.email_id}/attachments/{args.attachment_id}/$value"
        download_response = requests.get(download_url, headers=ms_headers)
        
        if download_response.status_code != 200:
            return ToolCallResult(
                result={"error": f"Failed to download attachment: {download_response.status_code} - {download_response.text}"},
                state=ToolCallState.ERROR
            )

        # Now upload to Bexio
        bexio_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {os.getenv('BEXIO_PAT')}"
        }

        # Create a multipart form-data request with the file
        files = {
            'file': (attachment_name, download_response.content)
        }

        try:
            response = requests.post(
                "https://api.bexio.com/3.0/files",
                headers=bexio_headers,  # Don't include Content-Type here, requests will set it automatically for multipart
                files=files
            )
            
            if response.status_code in (200, 201):
                return ToolCallResult(
                    result=response.json(),
                    state=ToolCallState.COMPLETED,
                    display_data=f"Successfully uploaded {attachment_name} to Bexio"
                )
            else:
                return ToolCallResult(
                    result={"error": f"Failed to upload to Bexio: {response.status_code} - {response.text}"},
                    state=ToolCallState.ERROR
                )
                
        except Exception as e:
            return ToolCallResult(
                result={"error": f"Error uploading to Bexio: {str(e)}"},
                state=ToolCallState.ERROR
            )
        
class BexioUploadFile:
    class Args(BaseModel):
        file_name: str = Field(description="Name of the file in the working directory to upload")
    
    tool_name = "bexio_upload_file"
    tool_description = "Uploads a file to Bexio."
    args_model = Args
    
    async def run(self, args: Args, global_state: dict, on_update) -> ToolCallResult:
        file_path = os.path.join(os.getenv("TOOLS_WORKING_DIR"), args.file_name)
        
        # Check if file exists
        if not os.path.exists(file_path):
            return ToolCallResult(
                result={"error": f"File {args.file_name} not found in working directory"},
                state=ToolCallState.ERROR
            )

        # Set up headers for Bexio API
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {os.getenv('BEXIO_PAT')}"
        }

        try:
            # Open and prepare the file for upload
            with open(file_path, 'rb') as file:
                files = {
                    'file': (args.file_name, file)
                }
                
                # Upload to Bexio
                response = requests.post(
                    "https://api.bexio.com/3.0/files",
                    headers=headers,  # Don't include Content-Type here, requests will set it automatically for multipart
                    files=files
                )
                
                if response.status_code in (200, 201):
                    return ToolCallResult(
                        result=response.json(),
                        state=ToolCallState.COMPLETED,
                        display_data=f"Successfully uploaded {args.file_name} to Bexio"
                    )
                else:
                    return ToolCallResult(
                        result={"error": f"Failed to upload to Bexio: {response.status_code} - {response.text}"},
                        state=ToolCallState.ERROR
                    )
                    
        except FileNotFoundError:
            return ToolCallResult(
                result={"error": f"File {args.file_name} could not be opened"},
                state=ToolCallState.ERROR
            )
        except Exception as e:
            return ToolCallResult(
                result={"error": f"Error uploading file to Bexio: {str(e)}"},
                state=ToolCallState.ERROR
            )
        
        

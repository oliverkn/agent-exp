from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import io
import os
import google.generativeai as genai
from typing import Dict, Any, Optional
import logging
from datetime import datetime, timedelta
from collections import deque
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Gemini
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable is not set")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-001')

# Constants
CHUNK_PROCESS_INTERVAL = 2
RATE_LIMIT_REQUESTS = 2000
RATE_LIMIT_WINDOW = 60

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()

    async def acquire(self):
        now = datetime.now()
        window_start = now - timedelta(seconds=self.window_seconds)
        while self.requests and self.requests[0] < window_start:
            self.requests.popleft()
        if len(self.requests) >= self.max_requests:
            wait_time = (self.requests[0] - window_start).total_seconds()
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                return await self.acquire()
        self.requests.append(now)
        return True

class VideoAnalyzer:
    def __init__(self):
        self.rate_limiter = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)

    def _create_live_prompt(self) -> str:
        return (
            "You are watching a live screen and audio recording. Follow these rules strictly:\n"
            "1. Only respond if absolutely necessary - minimize interruptions\n"
            "2. When responding, ALWAYS start your message with 'Response: '\n"
            "3. Respond ONLY in these cases:\n"
            "   - A direct question is asked through audio\n"
            "   - You see a critical error or mistake happening\n"
            "4. Keep responses extremely brief and focused\n"
            "5. If everything is proceeding normally, remain silent\n"
            "6. Never describe what you're seeing unless asked\n"
            "Remember: Your primary role is to observe quietly and only intervene when something is unclear to you.\n"
            "Example response format:\n"
            "Response: Your brief message here"
        )

    def _create_summary_prompt(self) -> str:
        return (
            "You are an automation expert analyzing a screen and audio recording. "
            "Consider both the visual steps shown and any verbal explanations given.\n"
            "Start your response with 'Response: ' and then provide:\n"
            "1. Step-by-Step Instructions: Clear steps to replicate this process using compute use AI \n"
            "2. Required Tools: List of tools used\n"
            "3. Required Data: List of inputs, credentials, and data needed\n"
            "5. Additional Context: Include any relevant information needed to complete the process\n"
            "\nExample format:\n"
            "Response: \n"
            "Step-by-Step Instructions:\n"
            "1. First step...\n"
            "[Rest of your analysis]"
        )

    async def analyze_live_stream(self, chat, video_data: bytes) -> Optional[Dict[str, Any]]:
        """Handle Case 1: Live stream analysis"""
        try:
            await self.rate_limiter.acquire()
            if not video_data:
                return None

            logger.info(f"Processing live stream chunk of size: {len(video_data)} bytes")
            
            prompt = [
                self._create_live_prompt(),
                {"mime_type": "video/webm", "data": video_data}
            ]

            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: chat.send_message(prompt)
                ),
                timeout=5.0
            )

            if response and response.text and response.text.strip():
                logger.info(f"Live stream response: {response.text}")
                return {
                    "type": "analysis",
                    "content": response.text.strip(),
                    "is_summary": False
                }
            return None

        except Exception as e:
            logger.error(f"Live stream analysis error: {str(e)}")
            return None

    async def create_final_summary(self, chat, video_data: bytes) -> Optional[Dict[str, Any]]:
        """Handle Case 2: Final summary after recording stops"""
        try:
            await self.rate_limiter.acquire()
            if not video_data:
                return None

            logger.info("Processing final summary")
            
            prompt = [
                self._create_summary_prompt(),
                {"mime_type": "video/webm", "data": video_data}
            ]

            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: chat.send_message(prompt)
                ),
                timeout=8.0
            )

            if response and response.text and response.text.strip():
                logger.info(f"Final summary response: {response.text}")
                return {
                    "type": "analysis",
                    "content": response.text.strip(),
                    "is_summary": True
                }
            return None

        except Exception as e:
            logger.error(f"Final summary error: {str(e)}")
            return None

@app.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    analyzer = VideoAnalyzer()
    chat = model.start_chat(history=[])
    buffer = io.BytesIO()
    chunk_count = 0
    last_response = None
    last_request_time = None
    min_request_interval = 0.03
    
    try:
        while True:
            try:
                # Check if it's a binary message (video data) or text message (control)
                message = await websocket.receive()
                
                if 'bytes' in message:
                    data = message['bytes']
                    if not data:
                        continue
                    
                    buffer.write(data)
                    chunk_count += 1
                    
                elif 'text' in message:
                    data = json.loads(message['text'])
                    if data.get('type') == 'stop_recording':
                        # Generate final summary when stop is received
                        video_data = buffer.getvalue()
                        if video_data:
                            summary = await analyzer.create_final_summary(chat, video_data)
                            if summary:
                                await websocket.send_json(summary)
                        continue
                
            except WebSocketDisconnect:
                break
                
    except:
        pass
    finally:
        buffer.close()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
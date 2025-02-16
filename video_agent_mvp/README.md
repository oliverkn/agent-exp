# Video Process Documentation Agent

A powerful tool that automatically documents and analyzes screen recordings with real-time AI feedback. This application combines screen recording capabilities with Google's Gemini AI to provide instant analysis and documentation of processes.

## Features

- **Screen Recording**: Capture both screen content and audio input
- **Real-time AI Analysis**: Live feedback during recording using Gemini AI
- **Process Documentation**: Automatic generation of step-by-step instructions
- **Voice Synthesis**: Text-to-speech feedback for AI responses
- **Editable Summaries**: Review and modify AI-generated documentation
- **Downloadable Recordings**: Save screen recordings for future reference

## Tech Stack

- **Frontend**: React + Vite
- **Backend**: FastAPI
- **AI Model**: Google Gemini 2.0 Flash
- **WebSocket**: Real-time communication between frontend and backend
- **Media Recording**: WebRTC for screen and audio capture

## Prerequisites

- Node.js (for frontend)
- Python 3.8+ (for backend)
- Google Cloud API key with Gemini API access

## Setup

1. Clone the repository
2. Set up the frontend:
   ```bash
   cd video_agent_mvp
   npm install
   ```

3. Set up the backend:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. Set environment variables:
   ```bash
   export GOOGLE_API_KEY=your_api_key_here
   ```

## Running the Application

1. Start the backend server:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

2. Start the frontend development server:
   ```bash
   cd video_agent_mvp
   npm run dev
   ```

3. Open http://localhost:5173 in your browser

## Usage

1. Click the "Start Recording" button to begin capturing your screen
2. Choose the screen/window you want to record
3. Perform the process you want to document
4. The AI will provide real-time feedback when necessary
5. Stop the recording to receive a detailed process summary
6. Edit the summary if needed and save for future reference

## Rate Limits

- Maximum 2000 requests per 60-second window
- Video chunks are processed every 5 seconds during live analysis
- Maximum video chunk size: 512KB

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

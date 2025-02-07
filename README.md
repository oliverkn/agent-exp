# FastAPI + React Full Stack Application

This is a full-stack application template using FastAPI for the backend and React with TypeScript for the frontend.

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   └── main.py
│   └── requirements.txt
└── frontend/
    ├── src/
    │   └── App.tsx
    ├── public/
    └── package.json
```

## Prerequisites

- Python 3.8 or higher
- Node.js and npm

## Setup Instructions

### Backend Setup

1. Create a Python virtual environment:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the FastAPI server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

The backend will be available at http://localhost:8000

### Frontend Setup

1. Install Node.js and npm if you haven't already:
   - Download from: https://nodejs.org/

2. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   ```

3. Start the React development server:
   ```bash
   npm start
   ```

The frontend will be available at http://localhost:3000

## API Documentation

Once the backend is running, you can access the API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Development

- Backend API endpoints should be added to `backend/app/main.py`
- Frontend components should be added to the `frontend/src` directory
- The frontend is configured to proxy API requests to the backend
- CORS is configured to allow requests from the frontend 
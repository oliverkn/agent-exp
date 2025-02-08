from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import models, database
from .services import agent
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FastAPI + React Thread Application")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

# Include the agent router without the /api prefix
app.include_router(agent.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "FastAPI backend is running!"} 
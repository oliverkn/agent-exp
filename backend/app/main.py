from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import models, database
from .services import agent_endpoint
from .database import engine
from .events import setup_db_events
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
    allow_headers=["*"]
)

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

# Setup database event listeners
setup_db_events(engine)

# Include the agent_endpoint router
app.include_router(agent_endpoint.router)

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "FastAPI backend is running!"} 
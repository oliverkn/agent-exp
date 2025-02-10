#!/bin/bash

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if required commands exist
if ! command_exists python3; then
    echo "Error: python3 is not installed"
    exit 1
fi

if ! command_exists npm; then
    echo "Error: npm is not installed"
    exit 1
fi

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Source environment variables
echo -e "${GREEN}Loading environment variables...${NC}"
if [ -f .env ]; then
    export $(cat .env | xargs)
else
    echo "Error: .env file not found"
    exit 1
fi

# Kill any existing processes on ports 3000 and 8000
echo -e "${GREEN}Cleaning up existing processes...${NC}"
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

echo -e "${GREEN}Starting the backend server...${NC}"
# Start the backend server in the background
cd backend
python3 -m uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

echo -e "${GREEN}Starting the frontend development server...${NC}"
# Start the frontend development server in the background
cd ../frontend
npm start &
FRONTEND_PID=$!

# Function to handle script termination
cleanup() {
    echo -e "${GREEN}Shutting down servers...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

# Set up trap to catch termination signal
trap cleanup SIGINT SIGTERM

# Keep the script running
wait 
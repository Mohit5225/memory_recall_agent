# main.py
from pathlib import Path
import sys
import logging
import asyncio
from typing import Dict, Any
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Import the LangGraph State and Graph builder
from src.agent.state import AgentState
from src.agent.graph import build_agent_graph

# Import DB client management functions for startup/shutdown
from src.db.mongo import get_mongo_client, close_mongo_client, DatabaseError

# Add project root to sys.path (points to agent01_attempt)
project_root = str(Path(__file__).resolve().parent)  # Get the directory containing main.py
if project_root not in sys.path:
    sys.path.append(project_root)

# Load .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Application Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager for application startup and shutdown events.
    Handles MongoDB client connection/disconnection and LangGraph setup.
    """
    logger.info("Application startup initiated.")
    try:
        # Connect MongoDB client when the application starts
        mongo_client = await get_mongo_client()
        if mongo_client is None:
            logger.error("Failed to connect to MongoDB on startup! Shutting down.")
            raise RuntimeError("Database connection failed")
        logger.info("✅ MongoDB connection established.")

        # --- LangGraph Setup ---
        logger.info("Building and compiling LangGraph graph...")
        try:
            app.state.agent_graph = build_agent_graph()
            logger.info("✅ LangGraph graph available.")
        except Exception as e:
            logger.error(f"Failed to build LangGraph graph: {e}", exc_info=True)
            raise RuntimeError("Failed to initialize LangGraph") from e

        yield  # Application runs here

    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)
        raise
    finally:
        # Cleanup on shutdown
        logger.info("Application shutdown initiated.")
        try:
            await close_mongo_client()
            logger.info("✅ MongoDB connection closed.")
        except Exception as e:
            logger.error(f"Error during MongoDB cleanup: {e}", exc_info=True)

# Create FastAPI application instance, integrating lifespan
app = FastAPI(
    title="Memory Recall Agent API",
    description="API for interacting with the Memory Recall Agent.",
    version="0.1.0",
    lifespan=lifespan
)

# Define a simple data model for the incoming chat request body
class ChatRequest(BaseModel):
    """Request model for chat interactions."""
    user_id: str
    message: str

# Error handler for DatabaseError
@app.exception_handler(DatabaseError)
async def database_error_handler(request: Request, exc: DatabaseError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Database operation failed. Please try again later."}
    )

# Define an API router
api_router = APIRouter()

@api_router.get("/", status_code=200)
async def read_root():
    """
    Root endpoint. Returns a simple welcome message.
    """
    logger.info("Root endpoint called.")
    return {"message": "Welcome to the Memory Recall Agent API!"}

@api_router.get("/health", status_code=200)
async def health_check():
    """
    Health check endpoint. Returns server status and DB connection health.
    """
    logger.info("Health check endpoint called.")
    try:
        client = await get_mongo_client()  # Get the shared client asynchronously
        await client.admin.command('ping')  # Use a lightweight command to check connection
        db_status = "ok"
    except Exception as e:
        logger.error(f"Health check database error: {e}")
        db_status = "error"

    return {"status": "ok", "database": db_status}

# --- API Routes ---
@api_router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> Dict[str, Any]:
    """
    Main chat endpoint that processes user messages through the agent graph.
    """
    logger.info(f"Chat endpoint called with user_id: {request.user_id}")
    try:
        # Initialize state for the graph
        initial_state = AgentState(
            user_id=request.user_id,
            user_input=request.message,
            current_config_prompt="",  # Will be loaded in first node
            parsed_intent="",  # Will be set by intent parser
            llm_response="",
            messages=[],  # Empty message history
            next_action="start"  # Initial action
        )
        logger.info(f"Initial state created: {initial_state}")

        # Verify MongoDB connection before graph execution
        client = await get_mongo_client()
        await client.admin.command('ping')  # Ensure DB is reachable

        # Execute the agent graph with the initial state (use ainvoke for async)
        final_state = await app.state.agent_graph.ainvoke(initial_state)
        logger.info(f"Agent graph execution completed. Final state: {final_state}")
        
        response = {
            "success": True,
            "response": final_state.get("final_outcome", "No response generated."),
            "intent": final_state.get("parsed_intent", "unknown")
        }
        logger.info(f"Sending response: {response}")
        return response

    except DatabaseError as e:
        logger.error(f"Database error in chat endpoint: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Error processing chat request: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your request."
        )

# Include the defined routes in the main application
app.include_router(api_router, prefix="/api/v1")
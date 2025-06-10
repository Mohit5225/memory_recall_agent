# main.py
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
import sys
import logging
from datetime import datetime

# Import the LangGraph State and Graph builder
from src.agent.state import AgentState
from src.agent.graph import build_agent_graph

# Import DB client management functions for startup/shutdown
from src.db.mongo import (
    get_mongo_client, close_mongo_client, DatabaseError, save_message, get_recent_messages,
    prune_old_messages
)
from src.models.message import Message

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
    Manages the application lifecycle:
    - Sets up database connections 
    - Creates the agent graph
    - Cleans up on shutdown
    """
    logger.info("🚀 Application startup initiated.")
    try:
        # Connect MongoDB client when the application starts
        mongo_client = await get_mongo_client()
        if mongo_client is None:
            logger.error("❌ Failed to connect to MongoDB on startup! Shutting down.")
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
        logger.error(f"❌ Application startup failed: {e}")
        raise
    finally:
        try:
            # Cleanup tasks
            await close_mongo_client()
            logger.info("✅ MongoDB connection closed.")
            await prune_old_messages()  # Clean up old messages before shutdown
            logger.info("✅ Old messages pruned.")
        except Exception as e:
            logger.error(f"❌ Cleanup error during shutdown: {e}", exc_info=True)

# --- FastAPI Application Configuration ---
app = FastAPI(
    title="Memory Recall Agent API",
    description="API for interacting with the Memory Recall Agent. Handles chat interactions and scheduling.",
    version="0.1.0",
    lifespan=lifespan
)

# Create API router with versioning
api_router = APIRouter(prefix="/api/v1")

# --- Request/Response Models ---
class ChatRequest(BaseModel):
    """Request model for chat interactions."""
    user_id: str
    message: str

class ChatResponse(BaseModel):
    """Standardized response model for chat interactions."""
    success: bool
    response: str
    intent: str = "unknown"

# --- Error Handlers ---
@app.exception_handler(DatabaseError)
async def database_error_handler(request: Request, exc: DatabaseError):
    """Handle database-specific errors with a proper 503 response"""
    return JSONResponse(
        status_code=503,
        content={"detail": "Database operation failed. Please try again later."}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle any unhandled exceptions with a proper 500 response"""
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again later."}
    )

@app.get("/", status_code=200)
async def root():
    """Root endpoint that returns a welcome message."""
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

@api_router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> Dict[str, Any]:
    """
    Main chat endpoint that processes user messages through the agent graph.
    Messages are saved immediately and pruned as needed for proper context handling.
    """
    logger.info(f"Chat endpoint called with user_id: {request.user_id}")
    try:
        # Load recent message history with fixed window
        recent_messages = await get_recent_messages(request.user_id, limit=7)  # Match DEFAULT_CONTEXT_WINDOW
        
        # Create and save user message atomically
        user_message = Message(
            content=request.message,
            role="user",
            timestamp=datetime.utcnow(),
            context={"sequence": len(recent_messages)}  # Track message order
        )
        
        try:
            await save_message(request.user_id, user_message.content, user_message.role, user_message.context)
            # Trigger pruning after save (keep 100 messages)
            await prune_old_messages(request.user_id, keep_count=100)
        except Exception as e:
            logger.error(f"Failed to save/prune user message: {e}")
            return {
                "success": False,
                "response": "Failed to process message due to storage error",
                "intent": "error"
            }
        
        # Initialize state with proper context
        initial_state = AgentState(
            user_id=request.user_id,
            user_input=request.message,
            current_config_prompt="",  # Will be loaded in first node
            parsed_intent="",  # Will be set by intent parser
            llm_response="",
            messages=recent_messages,  # Already proper Message objects
            next_action="start",  # Initial action
            context_window=7  # Match DEFAULT_CONTEXT_WINDOW
        )

        logger.info(f"Initial state created with {len(recent_messages)} previous messages")

        # Execute the agent graph
        final_state = await app.state.agent_graph.ainvoke(initial_state)
        logger.info(f"Agent graph execution completed. Final state: {final_state}")
        
        # Save assistant's response atomically
        if "llm_response" in final_state:
            assistant_message = Message(
                content=final_state["llm_response"],
                role="assistant",
                timestamp=datetime.utcnow(),
                context={
                    "intent": final_state.get("parsed_intent", "unknown"),
                    "sequence": len(recent_messages) + 1
                }
            )
            try:
                await save_message(request.user_id, assistant_message.content, assistant_message.role, assistant_message.context)
                # Trigger pruning after save
                await prune_old_messages(request.user_id, keep_count=100)
            except Exception as e:
                logger.error(f"Failed to save/prune assistant message: {e}")
                # Continue since we already have the response
        
        response = {
            "success": True,
            "response": final_state.get("final_outcome", "No response generated."),
            "intent": final_state.get("parsed_intent", "unknown")
        }
        logger.info(f"Sending response: {response}")
        return response

    except Exception as e:
        logger.error(f"Unhandled error in chat endpoint: {e}", exc_info=True)
        return {
            "success": False,
            "response": "An internal error occurred",
            "intent": "error"
        }

# Include router
app.include_router(api_router, prefix="/api/v1")
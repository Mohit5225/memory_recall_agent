# main.py
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
import sys
import logging
from datetime import datetime
import asyncio
import os
# Import the LangGraph State and Graph builder
from src.agent.state import AgentState
from src.agent.graph import build_agent_graph, save_messages_atomically
from src.config.constants import DEFAULT_CONTEXT_WINDOW  # Import for consistent context windowing
from src.auth.jwt_utils import get_current_user_from_token
from src.db.mongo import DB_NAME

# Import auth router
from src.auth.routes import router as auth_router

# Import DB client management functions for startup/shutdown
from src.db.mongo import (
    get_mongo_client, close_mongo_client, DatabaseError, save_message, get_recent_messages,
    prune_old_messages, _mongo_client
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
# Suppress noisy third-party loggers
logging.getLogger('pymongo').setLevel(logging.WARNING)
logging.getLogger('motor').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
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
    mongo_client_instance = None  # Initialize to None
    try:
        # Connect MongoDB client when the application starts
        logger.info("Attempting to initialize MongoDB client for the application...")
        mongo_client_instance = await get_mongo_client() # Store the returned client
        
        if mongo_client_instance is None:
            logger.error("❌ Failed to connect to MongoDB on startup! _mongo_client in db.mongo might be None or connection failed. Shutting down.")
            # Log the state of the global _mongo_client from the db.mongo module for diagnostics
            logger.info(f"State of global _mongo_client from src.db.mongo: {_mongo_client}")
            raise RuntimeError("Database connection failed during startup")
        
        logger.info("✅ MongoDB connection established and client instance obtained.")
        app.state.mongo_client = mongo_client_instance # Store it on app.state if needed elsewhere

        # --- LangGraph Setup ---
        logger.info("Building and compiling LangGraph graph...")
        try:
            app.state.agent_graph = build_agent_graph()
            logger.info("✅ LangGraph graph available.")
        except Exception as e:
            logger.error(f"Failed to build LangGraph graph: {e}", exc_info=True)
            raise RuntimeError("Failed to initialize LangGraph") from e

        # The redundant check for _mongo_client is removed as we now rely on mongo_client_instance
        logger.info("MongoDB client initialization was handled. Proceeding with application run.")
        
        yield  # Application runs here

    except Exception as e:
        logger.error(f"❌ Application startup failed: {e}")
        raise
    finally:
        logger.info("Application shutdown: Closing MongoDB client...")
        try:
            # Cleanup tasks
            # Use the stored mongo_client_instance for operations if needed, though close_mongo_client uses the global
            await close_mongo_client() 
            logger.info("✅ MongoDB connection closed.")
            # Removed: await prune_old_messages()  # This was causing an error as it requires user_id
            # logger.info("✅ Old messages pruned.") # Corresponding log also removed
        except Exception as e:
            logger.error(f"❌ Cleanup error during shutdown: {e}", exc_info=True)
 
# --- FastAPI Application Configuration ---
app = FastAPI(
    title="Memory Recall Agent API",
    description="API for interacting with the Memory Recall Agent. Handles chat interactions and scheduling.",
    version="0.1.0",
    lifespan=lifespan
)


from starlette.middleware.sessions import SessionMiddleware
import secrets
# Load secret from .env (already loaded via load_dotenv)
SESSION_SECRET = os.getenv("secret_key")
if not SESSION_SECRET or len(SESSION_SECRET) < 32:
    raise RuntimeError("Session secret is missing or too short! Check your .env.")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="fastapi_session",
    max_age=60*60,  # 60 minutes
    same_site="lax",
    https_only=False,  # Set True in prod
    path='/',
)
from starlette.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",
                "http://localhost:5173"   
                   ],  # The origin of your React frontend
    allow_credentials=True,  # IMPORTANT: This allows cookies to be sent
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)
# Create API router with versioning
api_router = APIRouter()

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
    logger.error(f"Unhandled error: {exc}", exc_info=True)  # Added exc_info=True
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
    try:        # Load recent message history with fixed window
        recent_messages = await get_recent_messages(request.user_id, limit=DEFAULT_CONTEXT_WINDOW)  # Use constant
        
        # Create user message object
        user_message = Message(
            content=request.message,
            role="user",
            user_id=request.user_id,
            timestamp=datetime.utcnow(),
            context={"sequence": len(recent_messages)}  # Track message order
        )
        
        # Initialize state with proper context
        initial_state = AgentState(
            user_id=request.user_id,
            user_input=request.message,
            current_config_prompt="",  # Will be loaded in first node
            parsed_intent="",  # Will be set by intent parser
            llm_response="",            messages=recent_messages,  # Already proper Message objects
            next_action="start",  # Initial action
            context_window=DEFAULT_CONTEXT_WINDOW  # Use constant
        )

        logger.info(f"Initial state created with {len(recent_messages)} previous messages")

        # Execute the agent graph
        final_state = await app.state.agent_graph.ainvoke(initial_state)
        logger.info(f"Agent graph execution completed. Final state: {final_state}")
          # Create assistant message object if we have a response
        response_content = final_state.get("llm_response") or final_state.get("final_outcome", "")
        if response_content and response_content.strip():
            assistant_message = Message(
                content=response_content,
                role="assistant",
                user_id=request.user_id,
                timestamp=datetime.utcnow(),
                context={
                    "intent": final_state.get("parsed_intent", "unknown"),
                    "sequence": len(recent_messages) + 1
                }
            )
            
            # Save both messages atomically
            messages_to_save = [user_message, assistant_message]
            save_success = await save_messages_atomically(request.user_id, messages_to_save)
            
            if not save_success:
                logger.error("Failed to save messages atomically")
                return {
                    "success": False,
                    "response": "Failed to process message due to storage error",
                    "intent": "error"
                }
                
            # Prune old messages after successful save
            try:
                await prune_old_messages(request.user_id, keep_count=100)
            except Exception as e:
                logger.warning(f"Failed to prune old messages: {e}")
                # Continue since messages were saved successfully
        else:
            # Just save user message if we have no response
            save_success = await save_messages_atomically(request.user_id, [user_message])
            if not save_success:
                logger.error("Failed to save user message")
                return {
                    "success": False,
                    "response": "Failed to process message due to storage error",
                    "intent": "error"
                }
          # Check if the response indicates an error
        response_content = final_state.get("llm_response", "No response generated.")
        is_error = any(error_phrase in response_content.lower() for error_phrase in [
            "error", "failed", "unexpected error", "internal system error", 
            "database error", "internal database issue"
        ])
        
        response = {
            "success": not is_error,
            "response": response_content,
            "intent": final_state.get("parsed_intent", "unknown")
        }
        logger.info(f"Sending response: {response}")
        return response

    except Exception as e:
        logger.error(f"Error processing chat request: {e}", exc_info=True)
        return {
            "success": False, 
            "response": "Internal server error",
            "intent": "error"
        }
class MessageResponse(BaseModel):
    sender: str
    text: str



@api_router.get(
    "/chat/history",
    response_model=List[MessageResponse],
    summary="Get recent chat history for the logged-in user"
)
async def chat_history(request: Request) -> List[Dict[str, str]]:
    logger.info("🔍 Chat history endpoint called - starting authentication check")
    
    try:
        # Step 1: JWT Authentication with detailed logging
        logger.info("📋 Step 1: Attempting to extract user from JWT token...")
        user = await get_current_user_from_token(request)
        
        if not user:
            logger.error("❌ JWT token validation failed - no user returned")
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        if not user.get("user_id"):
            logger.error(f"❌ JWT valid but missing user_id. User object: {user}")
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = user["user_id"]
        logger.info(f"✅ Step 1 SUCCESS: Authenticated user_id='{user_id}'")
        
        # Step 2: Database Connection with detailed logging
        logger.info("📋 Step 2: Attempting to get MongoDB client...")
        client = await get_mongo_client()
        
        if client is None:
            logger.error("❌ Step 2 FAILED: MongoDB client returned None")
            raise HTTPException(status_code=503, detail="Database connection unavailable")
        
        logger.info("✅ Step 2 SUCCESS: MongoDB client obtained")
        
        # Step 3: Database Access with detailed logging
        logger.info(f"📋 Step 3: Accessing database '{DB_NAME}' and collection 'messages'...")
        db = client[DB_NAME]
        collection = db["messages"]
        logger.info("✅ Step 3 SUCCESS: Database and collection references created")
        
        # Step 4: Query Execution with detailed logging
        logger.info(f"📋 Step 4: Executing query for user_id='{user_id}'...")
        logger.info(f"Query filter: {{'user_id': '{user_id}'}}")
        logger.info("Query projection: {'content': 1, 'role': 1, '_id': 0}")
        logger.info("Query sort: timestamp descending, limit: 50")
        
        cursor = collection.find(
            {"user_id": user_id},  # Use extracted user_id variable
            {"content": 1, "role": 1, "_id": 0}
        ).sort("timestamp", -1).limit(50)
        
        logger.info("✅ Step 4 SUCCESS: Query cursor created")
        
        # Step 5: Fetch Results with detailed logging
        logger.info("📋 Step 5: Converting cursor to list...")
        messages = await cursor.to_list(length=None)
        messages.reverse()  
        
        message_count = len(messages)
        logger.info(f"✅ Step 5 SUCCESS: Retrieved {message_count} messages from database")
        
        # Step 6: Data Transformation with detailed logging
        logger.info("📋 Step 6: Transforming messages to response format...")
        
        if message_count > 0:
            logger.info(f"Sample message structure: {messages[0]}")
        
        transformed_messages = [
            {"sender": msg["role"], "text": msg["content"]} 
            for msg in messages
        ]
        
        logger.info(f"✅ Step 6 SUCCESS: Transformed {len(transformed_messages)} messages")
        logger.info(f"🎉 Chat history endpoint completed successfully for user '{user_id}'")
        
        return transformed_messages
        
    except HTTPException:
        # Re-raise HTTP exceptions without logging (already logged above)
        raise
    except Exception as e:
        logger.error(f"💥 UNEXPECTED ERROR in chat_history endpoint: {e}", exc_info=True)
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error args: {e.args}")
        raise HTTPException(status_code=500, detail="Failed to fetch chat history")


 
# Include router
app.include_router(api_router, prefix="/api/v1")
app.include_router(auth_router)  # Auth routes don't need prefix (e.g., /auth/google)
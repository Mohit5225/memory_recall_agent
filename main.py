# main.py
from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel
import logging
from contextlib import asynccontextmanager
# Import the LangGraph State and Graph builder
from agent.state import AgentState # Ensure this is imported
from agent.graph import build_agent_graph # Ensure this is imported
# Import DB client management functions for startup/shutdown
from db.mongo import get_mongo_client, close_mongo_client # Ensure these are imported

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
    # Connect MongoDB client when the application starts
    mongo_client = get_mongo_client()
    if mongo_client is None:
        logger.error("Failed to connect to MongoDB on startup! Shutting down.")
        raise RuntimeError("Database connection failed")

    # --- LangGraph Setup ---
    logger.info("Building and compiling LangGraph graph...")
    try:
        app.state.agent_graph = build_agent_graph()
        logger.info("✅ LangGraph graph available.")
    except Exception as e:
        logger.error(f"Failed to build LangGraph graph on startup: {e}")
        raise RuntimeError(f"LangGraph compilation failed: {e}")

    yield # Application is ready to receive requests

    logger.info("Application shutdown initiated.")
    # Close MongoDB client when the application shuts down
    close_mongo_client()
    logger.info("✅ Application shutdown complete.")


# Create FastAPI application instance, integrating lifespan
app = FastAPI(
    title="Memory Recall Agent API",
    description="API for interacting with the Memory Recall Agent.",
    version="0.1.0",
    lifespan=lifespan
)

# Define a simple data model for the incoming chat request body
class ChatRequest(BaseModel):
    user_id: str
    message: str

# Define an API router
api_router = APIRouter()

@api_router.get("/", status_code=200)
def read_root():
    """
    Root endpoint. Returns a simple welcome message.
    """
    logger.info("Root endpoint called.")
    return {"message": "Welcome to the Memory Recall Agent API!"}

@api_router.get("/health", status_code=200)
def health_check():
    """
    Health check endpoint. Returns server status and DB connection health.
    """
    logger.info("Health check endpoint called.")
    client = get_mongo_client() # Get the shared client
    db_status = "disconnected"
    if client:
        try:
            client.admin.command('ping') # Use a lightweight command to check
            db_status = "ok"
        except Exception:
            db_status = "error"

    return {"status": "ok", "database": db_status}


@api_router.post("/chat", status_code=200)
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint to receive user chat input and initiate agent processing via LangGraph.
    Now correctly retrieves the final outcome from the state.
    """
    user_id = request.user_id
    message = request.message
    logger.info(f"Received chat message for user '{user_id}': '{message}'")

    # --- Create Initial LangGraph State ---
    initial_state = AgentState(
        user_id=user_id,
        user_input=message,
        current_config_prompt="",
        parsed_intent="",
        llm_response="",
        messages=[]
    )
    logger.info("Created initial AgentState.")

    # --- Invoke LangGraph ---
    try:
        logger.info("Invoking LangGraph agent...")
        # Use ainvoke for async execution with FastAPI
        final_state = await app.state.agent_graph.ainvoke(initial_state)
        logger.info("✅ LangGraph invocation complete.")
        logger.debug(f"Final State: {final_state}") # Log the full final state for debugging

        # --- Retrieve Final Outcome from State ---
        # Read the specific key set by the report_outcome_node
        final_outcome = final_state.get("final_outcome", "processing_unknown") # Default if key missing

        return {"status": "success", "message": "Agent processed input.", "final_state_preview": final_outcome} # Return the explicit outcome

    except Exception as e:
        logger.error(f"Error during LangGraph invocation for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent processing failed: {e}")


# Include the defined routes in the main application
app.include_router(api_router)
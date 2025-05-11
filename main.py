# main.py
from fastapi import FastAPI, APIRouter
from pydantic import BaseModel # Needed to define expected request body structure
import logging
from contextlib import asynccontextmanager # Needed for lifespan management in FastAPI
# Import the new LangGraph State and Graph builder
from agent.state import AgentState
from agent.graph import build_agent_graph
# Import DB client management functions for startup/shutdown
from db.mongo import get_mongo_client, close_mongo_client


# Configure basic logging for the FastAPI app
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Application Lifespan Management ---
# Use asynccontextmanager for newer FastAPI versions for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager for application startup and shutdown events.
    Handles MongoDB client connection/disconnection.
    """
    logger.info("Application startup initiated.")
    # Connect MongoDB client when the application starts
    mongo_client = get_mongo_client()
    if mongo_client is None:
        logger.error("Failed to connect to MongoDB on startup!")
        # Depending on how critical the DB is, you might want to raise an error here
        # raise Exception("Database connection failed")

    # --- LangGraph Setup ---
    # Build the LangGraph graph when the application starts
    # Store it in app.state for access in endpoints
    logger.info("Building LangGraph graph...")
    app.state.agent_graph = build_agent_graph()
    logger.info("✅ LangGraph graph available.")

    yield  # Application is ready to receive requests

    logger.info("Application shutdown initiated.")
    # Close MongoDB client when the application shuts down
    close_mongo_client()
    logger.info("✅ Application shutdown complete.")


# Create FastAPI application instance, integrating lifespan
app = FastAPI(
    title="Memory Recall Agent API",
    description="API for interacting with the Memory Recall Agent.",
    version="0.1.0",
    lifespan=lifespan # Connect lifespan context manager
)

# Define a simple data model for the incoming chat request body
# We will reuse this structure
class ChatRequest(BaseModel):
    user_id: str
    message: str

# Define an API router (useful for organizing endpoints as the app grows)
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
    Health check endpoint. Returns server status.
    Also checks DB connection health.
    """
    logger.info("Health check endpoint called.")
    # Add a check for DB health
    client = get_mongo_client() # Get the shared client
    if client:
        try:
            client.admin.command('ping') # Use a lightweight command to check
            db_status = "ok"
        except Exception:
            db_status = "error"
    else:
        db_status = "disconnected"

    return {"status": "ok", "database": db_status}


@api_router.post("/chat", status_code=200)
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint to receive user chat input and initiate agent processing.
    Now creates the initial LangGraph state.
    """
    user_id = request.user_id
    message = request.message
    logger.info(f"Received chat message for user '{user_id}': '{message}'")

    # --- Create Initial LangGraph State ---
    # This is where the data for this interaction starts its journey through the graph.
    initial_state = AgentState(
        user_id=user_id,
        user_input=message,
        current_config_prompt="", # Will be fetched by a node later
        parsed_intent="",
        llm_response="",
        messages=[] # Start with empty messages for now
    )
    logger.info("Created initial AgentState.")
    # logger.debug(f"Initial State: {initial_state}") # Uncomment for state detail

    # --- Placeholder for LangGraph Invocation ---
    # This is where we WILL invoke the graph with the initial state.
    # The graph logic is not yet built beyond a simple entry/exit.
    # In Step 2.4, this will become:
    # final_state = await app.state.agent_graph.ainvoke(initial_state)
    # logger.info("LangGraph invocation placeholder executed.")
    # logger.debug(f"Final State (placeholder): {final_state}") # Example logging


    return {"status": "success", "message": "Input received, initial state created (LangGraph invocation placeholder)."}

# Include the defined routes in the main application
app.include_router(api_router)

# Note: You will run this with uvicorn from your terminal:
# uvicorn main:app --reload
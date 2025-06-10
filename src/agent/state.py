# src/agent/state.py
from typing import TypedDict, Annotated, List
from typing_extensions import NotRequired
import operator
from src.models.message import Message
from src.db.mongo import save_message, get_recent_messages, prune_old_messages

# Define the AgentState using TypedDict
# This is the central state object that LangGraph nodes will read from and write to.
class AgentState(TypedDict):
    """Represents the state of the agent's workflow for a single interaction."""

    user_id: str # The ID of the user initiating the interaction
    user_input: str # The raw input message from the user

    # --- Agent Memory/Context ---
    # Add fields here to track context across nodes
    # e.g., current configuration, conversation history, parsed intent, etc.
    current_config_prompt: str # The user's current full instruction prompt
    parsed_intent: str # What the agent thinks the user wants to do (e.g., "tweak_config", "ask_question", "schedule")
    llm_response: str # General field to store LLM generated text if needed
    messages: Annotated[List[Message], operator.add] # Chat history with proper Message objects
    context_window: NotRequired[int] # Number of messages to use for context (defaults in handlers)

    # --- Workflow Control Fields ---
    # Fields to control the flow of the graph
    next_action: str # What the graph should do next (e.g., "run_tweak_agent", "parse_input")
    final_outcome: NotRequired[str] # Result of the interaction

# --- Message Management Functions ---
async def load_message_history(user_id: str, limit: int = 7) -> List[Message]:
    """Load recent message history for a user with optimized retrieval."""
    return await get_recent_messages(user_id, limit)

async def append_messages(user_id: str, new_messages: List[Message]) -> bool:
    """
    Append new messages to the user's history with proper persistence.
    Returns True if all messages were saved successfully.
    """
    success = True
    for message in new_messages:
        if not await save_message(user_id, message):
            success = False
    
    # Prune old messages in background
    await prune_old_messages(user_id)
    return success

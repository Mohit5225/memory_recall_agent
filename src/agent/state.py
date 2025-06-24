# src/agent/state.py
from typing import TypedDict, Annotated, List
from typing_extensions import NotRequired
import operator
from src.models.message import Message, ProcessingStatus
from datetime import datetime, timezone
import asyncio
import logging
from typing import List

from src.db.mongo import (
    save_message, 
    get_recent_messages, 
    DatabaseError, 
    _mongo_client, 
    get_messages_collection
)
from src.config.constants import DEFAULT_CONTEXT_WINDOW

logger = logging.getLogger(__name__)

# Define the AgentState using TypedDict
# This is the central state object that LangGraph nodes will read from and write to.
# Annotated allows combining a type with metadata (like an operator for combining lists)
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

    # --- Processing Status Tracking ---
    processing_status: NotRequired[ProcessingStatus] # Current overall processing status
    processing_attempts: NotRequired[int] # Number of processing attempts for this interaction
    error_details: NotRequired[str] # Error details if processing fails
    started_at: NotRequired[datetime] # When processing started
    completed_at: NotRequired[datetime] # When processing completed (success or failure)

    # --- Workflow Control Fields ---
    # Fields to control the flow of the graph
    next_action: str # What the graph should do next (e.g., "run_tweak_agent", "parse_input")
    final_outcome: NotRequired[str] # Result of the interaction

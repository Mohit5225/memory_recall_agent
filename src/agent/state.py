# src/agent/state.py
from typing import TypedDict, Annotated, List
from typing_extensions import NotRequired
import operator
from src.models.message import Message
from datetime import datetime, timezone
import asyncio
import logging
from typing import List

from src.db.mongo import save_message, get_messages, DatabaseError
from src.agent.graph import DEFAULT_CONTEXT_WINDOW

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

    # --- Workflow Control Fields ---
    # Fields to control the flow of the graph
    next_action: str # What the graph should do next (e.g., "run_tweak_agent", "parse_input")
    final_outcome: NotRequired[str] # Result of the interaction

    # --- Message Handling ---
    # Fields and methods to manage message caching and context windows
    _message_cache: List[dict] # Internal cache for storing messages
    _context_window: int # Current size of the context window

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.current_task = None
        self.last_update = datetime.now(timezone.utc)
        self._message_cache = []
        self._context_window = DEFAULT_CONTEXT_WINDOW

    async def load_messages(self) -> None:
        """Load messages from database into local cache."""
        try:
            messages = await get_messages(self.user_id, self._context_window)
            self._message_cache = messages
        except DatabaseError as e:
            logger.error(f"Failed to load messages for user {self.user_id}: {e}")
            self._message_cache = []

    async def add_message(self, content: str, role: str, context: dict = None) -> bool:
        """
        Add a new message to both database and local cache.
        Returns True if successful, False otherwise.
        """
        try:
            # Save to database first
            success = await save_message(self.user_id, content, role, context)
            if not success:
                return False

            # Update local cache
            new_message = {
                "content": content,
                "role": role,
                "timestamp": datetime.now(timezone.utc),
                "context": context or {}
            }
            self._message_cache.append(new_message)
            
            # Maintain context window size
            if len(self._message_cache) > self._context_window:
                self._message_cache = self._message_cache[-self._context_window:]
            
            return True

        except DatabaseError as e:
            logger.error(f"Failed to add message for user {self.user_id}: {e}")
            return False

    def get_context_messages(self, window: int = None) -> List[dict]:
        """Get messages from local cache respecting context window."""
        window = window or self._context_window
        return self._message_cache[-window:] if self._message_cache else []

    def update_context_window(self, size: int) -> None:
        """Update the context window size and refresh local cache."""
        if size != self._context_window:
            self._context_window = size
            asyncio.create_task(self.load_messages())  # Refresh cache with new window size

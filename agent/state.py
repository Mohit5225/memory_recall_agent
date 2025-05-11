# src/agent/state.py
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph
import operator

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
    # Adding chat history for context (LangGraph often works with messages)
    # operator.add means if multiple nodes write to messages, they are concatenated
    messages: Annotated[list, operator.add]

    # --- Workflow Control Fields ---
    # Fields to control the flow of the graph
    next_action: str # What the graph should do next (e.g., "run_tweak_agent", "parse_input")
    # ... other state fields will be added as we build out features
    # scheduled_task_id: Optional[str] # ID of a created Celery task
    # reminder_text: Optional[str] # The generated reminder content
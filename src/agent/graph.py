# src/agent/graph.py
from langgraph.graph import StateGraph, END
from .state import AgentState
from src.core.tweak_agent import process_user_instruction
from src.core.intent_parser import parse_user_intent
from src.core.schedular import schedule_reminder_task, DatabaseError
import logging
import asyncio

logger = logging.getLogger(__name__)

# --- Node Definitions ---

async def entry_node(state: AgentState) -> AgentState:
    """Initial entry point of the graph. Logs entry."""
    logger.info(f"--- Entering graph for user: {state['user_id']} ---")
    return {}  # No state update needed here, just proceed

async def call_intent_parser(state: AgentState) -> AgentState:
    """
    LangGraph dispatch controller node that parses intent and routes to appropriate handlers.
    This is the CORE ROUTING ORCHESTRATION LOGIC - it determines which business logic
    to execute based on parsed intent and returns the appropriate state for routing.
    """
    logger.info(f"--- Executing Intent Parsing Node for user: {state['user_id']} ---")
    user_input = state['user_input']

    # Parse the intent first
    parsed_intent = await parse_user_intent(user_input, state) or "other"
    logger.info(f"Intent Parsing Node identified intent: '{parsed_intent}'")

    # Route to appropriate business logic based on parsed intent
    if parsed_intent == "schedule_request":
        # Execute scheduling logic and return its state for routing
        result_state = await call_scheduling_logic(state)
        # Add parsed_intent to result_state for proper routing
        result_state["parsed_intent"] = parsed_intent
        return result_state
        
    elif parsed_intent == "general_query":
        result_state = await handle_general_query(state)
        result_state["parsed_intent"] = parsed_intent
        return result_state
        
    elif parsed_intent == "config_update":
        result_state = await call_tweak_agent(state)
        result_state["parsed_intent"] = parsed_intent
        return result_state
        
    elif parsed_intent == "acknowledge":
        result_state = await handle_acknowledge(state)
        result_state["parsed_intent"] = parsed_intent
        return result_state
        
    else:  # For "other" intent
        result_state = await handle_other_intent(state)
        result_state["parsed_intent"] = parsed_intent
        return result_state

async def handle_general_query(state: AgentState) -> AgentState:
    """
    Handles general queries by generating an appropriate response.
    """
    logger.info(f"--- Handling General Query for user: {state['user_id']} ---")
    return {
        "llm_response": "Let me help you with that. Could you provide more details?",
        "final_outcome": "General query processed - awaiting more details.",
        "next": "general_complete"
    }

async def handle_acknowledge(state: AgentState) -> AgentState:
    """
    Handles acknowledgment intents by providing a simple response.
    """
    logger.info(f"--- Handling Acknowledge Intent for user: {state['user_id']} ---")
    return {
        "llm_response": "You're welcome! Let me know if there's anything else I can help with.",
        "final_outcome": "Acknowledgment processed successfully.",
        "next": "acknowledge_complete"
    }

async def handle_other_intent(state: AgentState) -> AgentState:
    """
    Handles unclassified or unclear intents by asking for clarification.
    """
    logger.info(f"--- Handling Other Intent for user: {state['user_id']} ---")
    return {
        "llm_response": "I'm not sure I understand. Could you clarify what you need?",
        "final_outcome": "Clarification requested for unclear intent.",
        "next": "other_complete"
    }

async def call_tweak_agent(state: AgentState) -> AgentState:
    """
    LangGraph node to call the core process_user_instruction function.
    Handles outcomes and exceptions. Returns outcome for transition and final result.
    """
    logger.info(f"--- Executing Tweak Config Node for user: {state['user_id']} ---")
    user_id = state['user_id']
    user_input = state['user_input']

    outcome_key = "tweak_failure"
    final_outcome = "config_update_failed"

    try:
        success = await process_user_instruction(user_id, user_input)
        if success is True:
            logger.info("Tweak agent reported success.")
            outcome_key = "tweak_success"
            final_outcome = "Configuration updated successfully."
        elif success is False:
            logger.error("Tweak agent reported operational failure.")
            outcome_key = "tweak_failure"
            final_outcome = "Failed to update configuration."
        elif success is None:
            logger.error("Tweak agent reported critical error.")
            outcome_key = "tweak_critical_failure"
            final_outcome = "An internal error occurred during configuration update."
    except Exception as e:
        logger.error(f"Unhandled exception in tweak agent node for user {user_id}: {e}", exc_info=True)
        outcome_key = "tweak_exception"
        final_outcome = f"An unexpected system error occurred during configuration update."

    logger.info(f"Tweak Config Node returning outcome: '{outcome_key}' and final outcome: '{final_outcome}'")
    return {
        "next": outcome_key,
        "final_outcome": final_outcome,
        "llm_response": final_outcome
    }

async def call_scheduling_logic(state: AgentState) -> AgentState:
    """
    LangGraph node to call the core scheduling logic function.
    Reads state, calls scheduler (parses/validates/saves), updates state with outcome.
    Handles potential DatabaseError and other exceptions.
    """
    logger.info(f"--- Executing Scheduling Logic Node for user: {state['user_id']} ---")
    user_id = state['user_id']
    user_input = state['user_input']

    try:
        outcome_dict = await schedule_reminder_task(user_id, user_input)
        logger.info(f"Scheduling logic returned: {outcome_dict}")
        return outcome_dict
    except DatabaseError as e:
        logger.error(f"Database error caught in scheduling node for user {user_id}: {e}", exc_info=True)
        return {
            "next": "schedule_db_error",
            "final_outcome": f"A database error prevented saving your schedule. Please try again.",
            "llm_response": "A database error prevented saving your schedule. Please try again."
        }
    except Exception as e:
        logger.error(f"Unhandled exception in scheduling node for user {user_id}: {e}", exc_info=True)
        return {
            "next": "schedule_exception",
            "final_outcome": f"An unexpected error occurred while processing your schedule request.",
            "llm_response": "An unexpected error occurred while processing your schedule request."
        }

async def report_outcome_node(state: AgentState) -> AgentState:
    """
    Final node in the graph that ensures the final_outcome is correctly placed in state.
    """
    logger.info(f"--- Executing Report Outcome Node for user: {state['user_id']} ---")
    final_outcome = state.get('final_outcome', "Operation completed.")
    llm_response = state.get('llm_response', final_outcome)
    logger.info(f"Final outcome: {final_outcome}")
    return {
        "final_outcome": final_outcome,
        "llm_response": llm_response
    }

# --- Graph Builder ---
def build_agent_graph():
    """
    Builds and returns the compiled LangGraph workflow for the agent.
    """
    # Create a new graph
    workflow = StateGraph(AgentState)

    # Add nodes to the graph
    workflow.add_node("entry", entry_node)
    workflow.add_node("parse_intent", call_intent_parser)
    workflow.add_node("report_outcome", report_outcome_node)

    # Connect entry to intent parsing
    workflow.set_entry_point("entry")
    workflow.add_edge("entry", "parse_intent")

    # The KEY FIX: Route based on the 'next' field that comes from the business logic
    # since call_intent_parser executes the business logic and returns its routing state
    def route_by_next_action(state):
        """
        Routes based on the 'next' field returned by the business logic functions.
        This handles all the different routing outcomes from scheduling, tweaking, etc.
        """
        next_action = state.get("next", "")
        parsed_intent = state.get("parsed_intent", "")
        
        logger.info(f"Routing with next_action: '{next_action}', parsed_intent: '{parsed_intent}'")
        
        # If next_action exists, use it for routing
        if next_action:
            return next_action
        
        # Fallback to parsed_intent if no next_action
        if parsed_intent:
            return parsed_intent
            
        # Ultimate fallback
        logger.warning("No routing information found, defaulting to 'other_complete'")
        return "other_complete"

    # Single conditional edge that handles ALL routing outcomes
    workflow.add_conditional_edges(
        "parse_intent",
        route_by_next_action,
        {
            # Scheduling outcomes
            "schedule_success": "report_outcome",
            "schedule_failure": "report_outcome", 
            "schedule_clarification": "report_outcome",
            "schedule_db_error": "report_outcome",
            "schedule_exception": "report_outcome",
            
            # Tweak agent outcomes  
            "tweak_success": "report_outcome",
            "tweak_failure": "report_outcome",
            "tweak_critical_failure": "report_outcome",
            "tweak_exception": "report_outcome",
            
            # Simple intent outcomes
            "general_complete": "report_outcome",
            "acknowledge_complete": "report_outcome", 
            "other_complete": "report_outcome",
            
            # Fallback for any parsed intents without next_action
            "general_query": "report_outcome",
            "acknowledge": "report_outcome",
            "other": "report_outcome"
        }
    )

    # Mark report_outcome as the end of all paths
    workflow.add_edge("report_outcome", END)

    # Compile the graph into a runnable workflow
    compiled_workflow = workflow.compile()
    logger.info("✅ LangGraph workflow compiled successfully.")
    return compiled_workflow

# Example usage (for testing this file if needed)
if __name__ == "__main__":
    print("--- LangGraph graph definition test ---")
    logger.warning("Direct graph invocation requires careful setup of DB client, LLM, and Celery/Redis context.")
    logger.info("Recommend testing via `uvicorn main:app --reload`.")
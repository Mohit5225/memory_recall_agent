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
    return {} # No state update needed here, just proceed


# Node to Call the Intent Parsing Logic
async def call_intent_parser(state: AgentState) -> AgentState:
    """
    LangGraph node to call the core parse_user_intent function.
    Reads user_input from state, calls parser, updates state with parsed_intent.
    """
    logger.info(f"--- Executing Intent Parsing Node for user: {state['user_id']} ---")
    user_input = state['user_input']
    parsed_intent = await parse_user_intent(user_input)
    logger.info(f"Intent Parsing Node identified intent: '{parsed_intent}'")
    return {"parsed_intent": parsed_intent}


# Node to Call the Core Tweak Agent Logic
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
        "final_outcome": final_outcome
    }

# Node to Call the Scheduling Logic
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
        return outcome_dict

    except DatabaseError as e:
        logger.error(f"Database error caught in scheduling node for user {user_id}: {e}", exc_info=True)
        return {
            "next": "schedule_db_error",
            "final_outcome": f"A database error prevented saving your schedule. Please try again."
        }
    except Exception as e:
        logger.error(f"Unhandled exception in scheduling node for user {user_id}: {e}", exc_info=True)
        return {
            "next": "schedule_exception",
            "final_outcome": f"An unexpected error occurred while processing your schedule request."
        }


# Final Outcome Node (Revised to just set the final outcome from state)
# This node now primarily ensures the final_outcome is correctly placed in the state
# before ending, using the value already set by previous nodes.
async def report_outcome_node(state: AgentState) -> AgentState:
    """
    Final node in the graph that ensures the final_outcome is correctly placed in state.
    """
    logger.info(f"--- Executing Report Outcome Node for user: {state['user_id']} ---")
    # The final_outcome should already be set by previous nodes
    final_outcome = state.get('final_outcome', "Operation completed.")
    logger.info(f"Final outcome: {final_outcome}")
    return {"final_outcome": final_outcome}


# --- Graph Builder ---
def build_agent_graph() -> StateGraph:
    """
    Builds and returns the LangGraph workflow for the agent.
    """
    # Create a new graph
    workflow = StateGraph(AgentState)

    # Add nodes to the graph
    workflow.add_node("entry", entry_node)
    workflow.add_node("parse_intent", call_intent_parser)
    workflow.add_node("tweak_config", call_tweak_agent)
    workflow.add_node("schedule", call_scheduling_logic)
    workflow.add_node("report_outcome", report_outcome_node)

    # Connect entry to intent parsing
    workflow.set_entry_point("entry")
    workflow.add_edge("entry", "parse_intent")

    # Branch based on parsed intent
    workflow.add_conditional_edges(  # type: ignore
        "parse_intent",
        lambda x: x["parsed_intent"],
        {
            "config_update": "tweak_config",
            "schedule_request": "schedule",
            "general_query": "report_outcome",  # For now, just acknowledge
            "acknowledge": "report_outcome",     # Simple acknowledgment
            "other": "report_outcome"           # Fallback path
        }
    )

    # Connect tweak_config outcomes
    workflow.add_conditional_edges(
        "tweak_config",
        lambda x: x["next"],
        {
            "tweak_success": "report_outcome",
            "tweak_failure": "report_outcome",
            "tweak_critical_failure": "report_outcome",
            "tweak_exception": "report_outcome"
        }
    )

    # Connect schedule outcomes
    workflow.add_conditional_edges(
        "schedule",
        lambda x: x["next"],
        {
            "schedule_success": "report_outcome",
            "schedule_failure": "report_outcome",
            "schedule_clarification": "report_outcome",
            "schedule_db_error": "report_outcome",
            "schedule_exception": "report_outcome"
        }
    )

    # Mark report_outcome as the end of all paths
    workflow.add_edge("report_outcome", END)

    logger.info("✅ LangGraph workflow built successfully.")
    return workflow

# Example usage (for testing this file if needed)
if __name__ == "__main__":
    print("--- LangGraph graph definition test ---")
    logger.warning("Direct graph invocation requires careful setup of DB client, LLM, and Celery/Redis context.")
    logger.info("Recommend testing via `uvicorn main:app --reload`.")
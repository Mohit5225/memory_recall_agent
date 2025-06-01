# src/agent/graph.py
from langgraph.graph import StateGraph, END
from .state import AgentState
from  src.core.tweak_agent import process_user_instruction
from  src.core.intent_parser import parse_user_intent
# Import the scheduling logic function and DatabaseError
from src.core.schedular import schedule_reminder_task, DatabaseError



import logging
logger = logging.getLogger(__name__)

# --- Node Definitions ---

def entry_node(state: AgentState) -> AgentState:
    """Initial entry point of the graph. Logs entry."""
    logger.info(f"--- Entering graph for user: {state['user_id']} ---")
    return {} # No state update needed here, just proceed


# Node to Call the Intent Parsing Logic (No internal change needed)
def call_intent_parser(state: AgentState) -> AgentState:
    """
    LangGraph node to call the core parse_user_intent function.
    Reads user_input from state, calls parser, updates state with parsed_intent.
    """
    logger.info(f"--- Executing Intent Parsing Node for user: {state['user_id']} ---")
    user_input = state['user_input']
    parsed_intent = parse_user_intent(user_input)
    logger.info(f"Intent Parsing Node identified intent: '{parsed_intent}'")
    # Return the parsed intent for state merging
    return {"parsed_intent": parsed_intent}


# Node to Call the Core Tweak Agent Logic (No internal change needed)
def call_tweak_agent(state: AgentState) -> AgentState:
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
        success = process_user_instruction(user_id, user_input)

        if success is True:
            logger.info("Tweak agent reported success.")
            outcome_key = "tweak_success"
            final_outcome = "Configuration updated successfully." # User-friendly message
        elif success is False:
            logger.error("Tweak agent reported operational failure.")
            outcome_key = "tweak_failure"
            final_outcome = "Failed to update configuration." # User-friendly message
        elif success is None:
             logger.error("Tweak agent reported critical error.")
             outcome_key = "tweak_critical_failure"
             final_outcome = "An internal error occurred during configuration update." # User-friendly message

    except Exception as e:
        logger.error(f"Unhandled exception in tweak agent node for user {user_id}: {e}", exc_info=True)
        outcome_key = "tweak_exception"
        final_outcome = f"An unexpected system error occurred during configuration update." # User-friendly message

    logger.info(f"Tweak Config Node returning outcome: '{outcome_key}' and final outcome: '{final_outcome}'")
    return {
        "next": outcome_key, # This is used by the conditional edge FROM tweak_config
        "final_outcome": final_outcome # This is read by report_outcome_node and main.py
    }

# --- Node to Call the Scheduling Logic (Revised for validation outcome and DB errors) ---
# This node is triggered by the "schedule_request" intent.
def call_scheduling_logic(state: AgentState) -> AgentState:
    """
    LangGraph node to call the core scheduling logic function.
    Reads state, calls scheduler (parses/validates/saves), updates state with outcome.
    Handles potential DatabaseError and other exceptions.
    """
    logger.info(f"--- Executing Scheduling Logic Node for user: {state['user_id']} ---")
    user_id = state['user_id']
    user_input = state['user_input']

    # schedule_reminder_task now returns a dictionary with {'next': ..., 'final_outcome': ...}
    # It also raises DatabaseError on critical DB failure.
    try:
        outcome_dict = schedule_reminder_task(user_id, user_input)
        # schedule_reminder_task handles parsing failures internally and returns a specific outcome dict
        return outcome_dict

    except DatabaseError as e:
        # Catch specific DatabaseErrors raised by scheduler_task
        logger.error(f"Database error caught in scheduling node for user {user_id}: {e}", exc_info=True)
        # Set specific outcome for database failure
        return {"next": "schedule_db_error", "final_outcome": f"A database error prevented saving your schedule. Please try again."} # User-friendly message
    except Exception as e:
        # Catch any other unexpected exceptions in this node or from scheduler_task
        logger.error(f"Unexpected error in scheduling node for user {user_id}: {e}", exc_info=True)
        # Set outcome for unexpected error
        return {"next": "schedule_exception", "final_outcome": f"An internal system error occurred while processing your scheduling request."} # User-friendly message


# Final Outcome Node (Revised to just set the final outcome from state)
# This node now primarily ensures the final_outcome is correctly placed in the state
# before ending, using the value already set by previous nodes.
def report_outcome_node(state: AgentState) -> AgentState:
    """
    Node to structure the final outcome before ending the graph.
    Reads the 'final_outcome' key from the state and ensures it's returned.
    """
    logger.info(f"--- Executing Report Outcome Node for user: {state['user_id']} ---")
    logger.debug(f"Report Outcome Node received state: {state}")

    final_outcome = state.get("final_outcome", "An unknown process outcome occurred.") # Default message if not set

    logger.info(f"Final outcome: '{final_outcome}'")
    # Return the final_outcome to ensure it's in the state returned by invoke
    return {"final_outcome": final_outcome}


# --- Graph Builder ---
def build_agent_graph():
    """
    Builds and compiles the LangGraph agent workflow graph.
    Adds nodes and defines conditional edges.
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("entry", entry_node)
    workflow.add_node("parse_intent", call_intent_parser)
    workflow.add_node("tweak_config", call_tweak_agent)
    workflow.add_node("schedule_request", call_scheduling_logic) # The scheduling node
    workflow.add_node("report_outcome", report_outcome_node)

    # Define entry point
    workflow.set_entry_point("entry")

    # --- Define Edges ---

    # entry -> parse_intent (Unconditional)
    workflow.add_edge("entry", "parse_intent")

    # Conditional edges from parse_intent
    # Routes based on the 'parsed_intent' key
    workflow.add_conditional_edges(
        "parse_intent",
        lambda state: state.get('parsed_intent', 'other'),
        {
            "config_update": "tweak_config",         # Config intent goes to tweak node
            "schedule_request": "schedule_request",  # Schedule intent goes to scheduling node
            # Other intents still go to report_outcome for now
            "general_query": "report_outcome",
            "acknowledge": "report_outcome",
            "other": "report_outcome",
        }
    )

    # Conditional edges from tweak_config (based on 'next' key set by the node)
    # Outcomes from tweak_config route to report_outcome
    workflow.add_conditional_edges(
        "tweak_config",
        lambda state: state.get('next', 'tweak_failure'),
        {
            "tweak_success": "report_outcome",
            "tweak_failure": "report_outcome",
            "tweak_critical_failure": "report_outcome",
            "tweak_exception": "report_outcome"
        }
    )

    # --- Conditional edges from the schedule_request node (Revised for all outcomes) ---
    # Outcomes from scheduling logic route to report_outcome.
    # Handles success, failure (parsing, DB, exception).
    workflow.add_conditional_edges(
        "schedule_request", # Node whose state updates determine next step
        lambda state: state.get('next', 'schedule_failure'), # Read the 'next' key set by scheduling node
        { # Mapping of 'next' value to next node
            "schedule_success": "report_outcome",          # Successful save goes to report node
            "schedule_failure": "report_outcome",          # Save failure (e.g. non-critical DB) goes to report node
            "schedule_parsing_failed": "report_outcome",   # Parsing/Validation failure goes to report node
            "schedule_db_error": "report_outcome",         # Critical Database error caught goes to report node
            "schedule_exception": "report_outcome",        # Unexpected exception caught goes to report node
        }
    )


    # Edge from report_outcome_node to END
    workflow.add_edge("report_outcome", END)


    # Compile the graph
    graph = workflow.compile()
    logger.info("✅ LangGraph compiled successfully with refined scheduling logic outcomes.")

    return graph

# Example usage (for testing this file if needed)
if __name__ == "__main__":
    print("--- LangGraph graph definition test ---")
    logger.warning("Direct graph invocation requires careful setup of DB client, LLM, and Celery/Redis context.")
    logger.info("Recommend testing via `uvicorn main:app --reload`.")